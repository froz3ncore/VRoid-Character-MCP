"""End-to-end proof on a brand-new lab, with no manual file edits and no code changes.

Sequence: prepare a clean lab -> start the server -> load the base model ->
parameters -> makeup layer -> hair preset -> final live-height calibration ->
save -> reopen in a new process for verification -> another process for Dress-up ->
import the supplied outfit -> save the assembly -> export VRM ->
parse that VRM independently.

Each step records what the server actually returned. A failure stops the run
with the step name, because a later step would then be measuring a different
state. Inputs (the VRoid install and the .xwear) are copied in; nothing is
written into the repository.

    python tools/e2e_clean_lab.py --source <VRoid install> --lab <new lab> --xwear <outfit.xwear>

Exit codes: 0 all steps passed, 1 a step failed, 2 the run could not start
(lab exists, crash key present, lab owned by another server, missing input).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import timedelta

PROJECT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / 'tools'))

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

from vroid_mcp import closet_guard, lab_lock  # noqa: E402
from vroid_mcp.bounded_paint import decode_rgba_png  # noqa: E402
import vrm_inspect  # noqa: E402

MAKEUP_LAYER = 'MCP e2e cheek blush'
BASE_FILENAME = 'e2e-clean-lab.vroid'
ASSEMBLY_FILENAME = 'e2e-clean-lab.xroid'
VRM_FILENAME = 'e2e-clean-lab.vrm'


def status_text(result) -> dict:
    if result.isError:
        raise RuntimeError(str(result.content[0].text if result.content else result))
    structured = result.structuredContent
    # FastMCP may wrap a list[TextContent | ImageContent] in {"result": [...]}.
    # Capture summaries are the first JSON text block, not the wrapper or PNGs.
    blocks = structured.get('result') if isinstance(structured, dict) else None
    if isinstance(blocks, list) and blocks and isinstance(blocks[0], dict) and blocks[0].get('type') == 'text':
        return json.loads(blocks[0]['text'])
    return structured or json.loads(result.content[0].text)


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mask_interior_point(png_path: pathlib.Path) -> tuple[float, float, int]:
    """Pick a point deep inside the widest masked blob.

    The Cheek mask covers both cheeks, so the alpha centroid lands between them
    and a stamp there misses the mask. This scores every candidate by how much
    of its neighbourhood is masked and keeps the best one, which sits inside the
    largest blob instead of in the gap between two.
    """
    width, height, rgba = decode_rgba_png(png_path.read_bytes())
    alpha = rgba[3::4]
    total = sum(alpha)
    if not total:
        raise RuntimeError('the exported makeup mask is empty')
    stride = width + 1
    integral = [0] * ((width + 1) * (height + 1))
    for y in range(height):
        row_sum = 0
        for x in range(width):
            row_sum += 1 if alpha[y * width + x] else 0
            integral[(y + 1) * stride + x + 1] = integral[y * stride + x + 1] + row_sum
    half = max(2, min(width, height) // 64)
    best = (-1, 0, 0)
    for y in range(half, height - half, 2):
        for x in range(half, width - half, 2):
            if not alpha[y * width + x]:
                continue
            score = (integral[(y + half + 1) * stride + x + half + 1]
                     - integral[(y - half) * stride + x + half + 1]
                     - integral[(y + half + 1) * stride + x - half]
                     + integral[(y - half) * stride + x - half])
            if score > best[0]:
                best = (score, x, y)
    if best[0] < 0:
        raise RuntimeError('the exported makeup mask has no usable interior pixel')
    _, x, y = best
    return (x + 0.5) / width, (y + 0.5) / height, total


def describe(error: BaseException) -> str:
    # Python 3.10 has exception groups only through the backport package.
    try:
        group = BaseExceptionGroup  # type: ignore[name-defined]
    except NameError:  # pragma: no cover - 3.10 path
        from exceptiongroup import BaseExceptionGroup as group
    if isinstance(error, group):
        return '; '.join(describe(inner) for inner in error.exceptions)
    return f'{type(error).__name__}: {error}'


class Steps:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.current = 'preflight'

    def record(self, name: str, detail: dict, status: str = 'pass') -> None:
        self.rows.append({'step': name, 'status': status, 'seconds': None, 'detail': detail})
        print(f'[{status:>7}] {name}: {json.dumps(detail, ensure_ascii=False)[:240]}')

    def fail(self, error: BaseException) -> int:
        self.record(self.current, {'error': describe(error)}, 'fail')
        return 1

    def timed(self, name: str, detail: dict) -> None:
        self.record(name, detail)


async def wait_for_readiness(call, steps: Steps, attempts: int = 40) -> dict:
    """Poll get_status until the native profile has finished loading.

    Opening a saved .vroid keeps the Unity main thread busy for a while after
    the server reports ready; a read-only status call may time out. Retrying a
    read is safe, unlike retrying a write.
    """
    last = None
    for _ in range(attempts):
        try:
            status = await call('get_status')
            if status.get('model_ready') and not status.get('command_busy'):
                return status
            last = status
        except Exception as error:  # transient MAIN_THREAD_TIMEOUT / NOT_READY
            text = describe(error)
            if 'MAIN_THREAD_TIMEOUT' not in text and 'NOT_READY' not in text:
                raise
            last = text
        await asyncio.sleep(1.5)
    raise RuntimeError(f'native profile never became ready: {last}')


def configure_scratch(lab: pathlib.Path) -> pathlib.Path:
    # Both the parent transport and the child server need writable temporary
    # files. Setting only the child's environment leaves stdio_client using a
    # broken host TEMP, and assuming a writable sibling work/ breaks clones.
    scratch = lab / 'e2e-temp'
    scratch.mkdir(parents=True, exist_ok=True)
    os.environ.update(TEMP=str(scratch), TMP=str(scratch))
    tempfile.tempdir = None
    return scratch


async def session(lab: pathlib.Path, model: pathlib.Path | None, body):
    configure_scratch(lab)
    env = dict(os.environ)
    args = ['-m', 'vroid_mcp.server', '--lab', str(lab)]
    if model is not None:
        args += ['--model', str(model)]
    params = StdioServerParameters(command=sys.executable, args=args, cwd=str(PROJECT), env=env)
    log_path = lab / 'e2e-server.log'
    with log_path.open('a', encoding='utf-8') as log:
        async with stdio_client(params, errlog=log) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=900)) as client:
                await client.initialize()

                async def call(name: str, arguments: dict | None = None) -> dict:
                    return status_text(await client.call_tool(name, arguments or {}))

                return await body(call)


async def height_checkpoint(call) -> dict:
    height = await call('get_height')
    body = await call('list_body_params')
    scale = next(p['value'] for p in body['parameters'] if p['id'] == 'body/WholeBody/002')
    return {'live_cm': float(height['live_centimeters']),
            'ui_cm': float(height['centimeters']), 'scale': float(scale)}


def verify_height(reading: dict, *, expected: dict | None = None,
                  target_cm: float | None = None, tolerance_cm: float = .05) -> None:
    if not all(math.isfinite(reading[key]) for key in ('live_cm', 'ui_cm', 'scale')):
        raise RuntimeError('Height checkpoint contains a non-finite value')
    if target_cm is not None and abs(reading['live_cm'] - target_cm) > tolerance_cm:
        raise RuntimeError(f"Live height {reading['live_cm']} missed target {target_cm} cm")
    if expected is not None:
        if abs(reading['live_cm'] - expected['live_cm']) > tolerance_cm:
            raise RuntimeError('Live height changed across save/reopen')
        if abs(reading['scale'] - expected['scale']) > 1e-6:
            raise RuntimeError('Whole-body scale changed across save/reopen')


def verify_body_proportions(parameters: list[dict], expected: list[dict]) -> None:
    actual = {p['id']: p['value'] for p in parameters}
    for change in expected:
        value = actual.get(change['id'])
        if (not isinstance(value, (int, float)) or not math.isfinite(value)
                or abs(value - change['value']) > 1e-6):
            raise RuntimeError('Body proportion did not persist: ' + change['id'])


async def phase_edit(call, lab: pathlib.Path, steps: Steps, capture_reviews: bool = False,
                     scenario: dict | None = None) -> dict:
    scenario = scenario or {}
    prefix = scenario.get('filename_prefix')
    if prefix is not None and (not isinstance(prefix, str) or not prefix
            or len(prefix) > 48 or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in prefix)):
        raise ValueError('Invalid scenario filename prefix')
    facts: dict = {'base_filename': f'{prefix}-base.vroid' if prefix else BASE_FILENAME,
                   'assembly_filename': f'{prefix}-assembly.xroid' if prefix else ASSEMBLY_FILENAME,
                   'vrm_filename': f'{prefix}-avatar.vrm' if prefix else VRM_FILENAME}
    started = time.monotonic()
    steps.current = 'start server and load base model'
    status = await wait_for_readiness(call, steps)
    facts['tool_count'] = status.get('tool_count')
    facts['toolset_hash'] = status.get('toolset_hash')
    facts['crash_guard'] = status.get('crash_guard')
    token = status['model_token']
    facts['model_token'] = token
    steps.record('start server and load base model', {
        'model_ready': status.get('model_ready'), 'tool_count': status.get('tool_count'),
        'toolset_hash': status.get('toolset_hash'), 'crash_guard': status.get('crash_guard')})

    steps.current = 'list parameters'
    face = await call('list_face_params')
    body = await call('list_body_params')
    steps.record('list parameters', {'face_parameters': len(face.get('parameters') or face.get('entries') or []),
                                     'body_parameters': len(body.get('parameters') or [])})
    if scenario.get('clothing_preset_id'):
        steps.current = 'apply scenario clothing preset'
        selected = await call('apply_clothing_preset', {'expected_model': token,
                                  'preset_id': scenario['clothing_preset_id']})
        facts['clothing_preset_id'] = scenario['clothing_preset_id']
        steps.record('apply scenario clothing preset', {'preset_id': scenario['clothing_preset_id'],
                                                       'changed': selected.get('changed')})

    # The texture editor is opened before any body parameter changes: in this
    # build, entering it right after a height change makes the native texture
    # editor touch an empty Body overlay mesh and the process dies, which would
    # be a harness failure rather than a tool-layer failure. The order is
    # recorded in the report so the deviation is explicit.
    steps.current = 'makeup layer'
    regions = (await call('list_texture_regions', {'expected_model': token}))['regions']
    cheek = next((r for r in regions if r['part'] == 'Cheek'), None)
    if not cheek:
        raise RuntimeError('no Cheek region in the texture region list')
    await call('open_texture_editor', {'expected_model': token, 'region_id': cheek['region_id'], 'bake_colors': True})
    layers_before = (await call('list_texture_layers', {'expected_model': token, 'region_id': cheek['region_id']}))['layers']
    mask = await call('export_makeup_region_mask', {'expected_model': token, 'region_id': cheek['region_id'],
                                                   'layer_id': layers_before[0]['layer_id']})
    cx, cy, weight = mask_interior_point(pathlib.Path(mask['mask_path']))
    mark = {'kind': 'stamp', 'points': [[round(cx, 4), round(cy, 4)]], 'radius': 0.03, 'hardness': 0.2,
            'color': [0.95, 0.45, 0.5, 0.45], 'mirror_x': True}
    preview = await call('preview_makeup_marks', {'expected_model': token, 'mask_id': mask['mask_id'],
                                                 'expected_mask_sha256': mask['manifest_sha256'], 'marks': [mark]})
    painted = await call('paint_makeup_marks', {'expected_model': token, 'mask_id': mask['mask_id'],
                                                'expected_mask_sha256': mask['manifest_sha256'], 'marks': [mark],
                                                'layer_name': MAKEUP_LAYER, 'opacity': 0.8})
    layers_after = (await call('list_texture_layers', {'expected_model': token, 'region_id': cheek['region_id']}))['layers']
    names = [str(layer.get('Name') or layer.get('name')) for layer in layers_after]
    if MAKEUP_LAYER not in names:
        raise RuntimeError('the makeup layer is not in the native layer list after painting: ' + ', '.join(names))
    authored = next(layer for layer in layers_after
                    if str(layer.get('Name') or layer.get('name')) == MAKEUP_LAYER)
    exported_layer = await call('export_texture_layer', {'expected_model': token,
                                'region_id': cheek['region_id'], 'layer_id': authored['layer_id']})
    facts['makeup_png_sha256'] = exported_layer['sha256']
    await call('close_texture_editor', {'expected_model': token})
    facts['cheek_layers_before'] = len(layers_before)
    facts['cheek_layers_after'] = len(layers_after)
    facts['mask_alpha_sum'] = weight
    steps.record('makeup layer', {'mask_sha256': mask['mask_png_sha256'][:16] + '...',
                                  'preview_sha256': preview['png_sha256'][:16] + '...',
                                  'native_history_commands': (painted.get('native_import') or {}).get('history_command_count'),
                                  'layers_before': len(layers_before), 'layers_after': len(layers_after),
                                  'layer_names': names})

    # Check an independent face parameter as well as the height scale.
    steps.current = 'set face parameter'
    face_now = await call('list_face_params')
    candidate = next(
        (p for p in face_now.get('parameters') or []
         if p.get('editable') and isinstance(p.get('value'), (int, float))
         and isinstance(p.get('min'), (int, float)) and isinstance(p.get('max'), (int, float))
         and p['max'] > p['min'] and '|' not in str(p.get('semantic_key') or '')
         and not str(p.get('id', '')).startswith(('photo/', 'general/'))),
        None)
    if candidate is None:
        raise RuntimeError('no plain float face parameter to use as a persistence witness')
    face_target = round((float(candidate['min']) + float(candidate['max'])) / 2, 4)
    await call('set_face_params', {'expected_model': token,
                                   'changes': [{'id': candidate['id'], 'value': face_target}]})
    face_after = await call('list_face_params')
    actual = next(p['value'] for p in face_after['parameters'] if p['id'] == candidate['id'])
    if abs(float(actual) - face_target) > 1e-3:
        raise RuntimeError(f'face parameter {candidate["id"]} read back {actual}, wanted {face_target}')
    facts['face_parameter'] = {'id': candidate['id'], 'value': actual, 'before': candidate['value'],
                               'label': candidate.get('label')}
    steps.record('set face parameter', {'id': candidate['id'], 'label': candidate.get('label'),
                                        'before': candidate['value'], 'target': face_target, 'after': actual})

    # Keep the scenario target relative to the original model, but finish hair
    # before calibration: hair changes the native height measurement itself.
    height_before = await call('get_height')
    target = round(float(height_before['live_centimeters']) + scenario.get('height_delta_cm', -2.0), 1)
    body_changes = scenario.get('body_changes', [])
    if body_changes:
        steps.current = 'set body proportions'
        if any(c['id'] == 'body/WholeBody/002' for c in body_changes):
            raise ValueError('Body profile must not replace the final height solver scale')
        changed = await call('set_body_params', {'expected_model': token, 'changes': body_changes})
        if not changed.get('ok'):
            raise RuntimeError('Body proportion write failed: ' + str(changed))
        body_after = (await call('list_body_params'))['parameters']
        verify_body_proportions(body_after, body_changes)
        facts['body_proportions'] = body_changes
        steps.record('set body proportions', {'profile': scenario.get('body_profile'),
                                              'changes': body_changes})

    steps.current = 'hair preset'
    presets = (await call('list_hair_presets', {'limit': 80}))['presets']
    hairstyle = next(p for p in presets if p['category'] == 'HairSet')
    applied = await call('apply_hair_preset', {'expected_model': token, 'preset_id': hairstyle['id']})
    nodes = await call('list_hair_nodes', {'category': 'HairFront'})
    node_count = len(nodes.get('nodes') or [])
    if not applied.get('changed') or node_count == 0:
        raise RuntimeError('hair preset did not create hair nodes')
    facts['hair_preset'] = hairstyle.get('name') or hairstyle['id']
    facts['hair_nodes'] = node_count
    steps.record('hair preset', {'preset': hairstyle.get('name'), 'changed': applied.get('changed'),
                                 'front_nodes': node_count})

    steps.current = 'set height after styling'
    calibrated = await call('set_height', {'expected_model': token, 'centimeters': target})
    facts['height_before_cm'] = height_before['live_centimeters']
    facts['height_target_cm'] = target
    facts['height_before_save'] = await height_checkpoint(call)
    verify_height(facts['height_before_save'], target_cm=target)
    facts['height_cm'] = facts['height_before_save']['live_cm']
    steps.record('set height after styling', {'before_cm': facts['height_before_cm'],
                 'target_cm': target, 'after_cm': facts['height_cm'],
                 'before_save': facts['height_before_save'], 'solver': calibrated})

    steps.current = 'save base model'
    saved = await call('save_as', {'expected_model': token, 'filename': facts['base_filename']})
    facts['height_after_save'] = await height_checkpoint(call)
    verify_height(facts['height_after_save'], expected=facts['height_before_save'], target_cm=target)
    base_path = lab / 'saves' / facts['base_filename']
    if not base_path.is_file():
        raise RuntimeError('save_as reported success but the file is missing')
    facts['base_model'] = str(base_path)
    facts['base_sha256'] = sha256(base_path)
    facts['edit_seconds'] = round(time.monotonic() - started, 1)
    steps.record('save base model', {'path': str(base_path), 'sha256': facts['base_sha256'],
                                     'height_after_save': facts['height_after_save'],
                                     'detail': {k: saved.get(k) for k in ('hash', 'bytes', 'saved') if k in saved}})
    if capture_reviews:
        facts['edit_review'] = await call('capture_review', {'expected_model': token,
                                    'views': ['body_front', 'body_back', 'face_front'], 'size': 512})
    return facts


async def phase_reopen(call, lab: pathlib.Path, facts: dict, steps: Steps,
                       capture_reviews: bool = False) -> None:
    started = time.monotonic()
    steps.current = 'reopen in a new process'
    status = await wait_for_readiness(call, steps)
    token = status['model_token']
    height = await height_checkpoint(call)
    verify_height(height, expected=facts['height_after_save'], target_cm=facts['height_target_cm'])
    verify_body_proportions((await call('list_body_params'))['parameters'], facts.get('body_proportions', []))
    facts['height_cold_reopen'] = height
    height_drift = height['live_cm'] - facts['height_after_save']['live_cm']
    face_now = await call('list_face_params')
    face_id = facts['face_parameter']['id']
    face_value = next(p['value'] for p in face_now['parameters'] if p['id'] == face_id)
    if abs(float(face_value) - float(facts['face_parameter']['value'])) > 1e-3:
        raise RuntimeError(f'face parameter {face_id} did not survive save/reopen: '
                           f"{face_value} vs {facts['face_parameter']['value']}")
    regions = (await call('list_texture_regions', {'expected_model': token}))['regions']
    cheek = next(r for r in regions if r['part'] == 'Cheek')
    await call('open_texture_editor', {'expected_model': token, 'region_id': cheek['region_id']})
    layers = (await call('list_texture_layers', {'expected_model': token, 'region_id': cheek['region_id']}))['layers']
    names = [str(layer.get('Name') or layer.get('name')) for layer in layers]
    if MAKEUP_LAYER not in names:
        raise RuntimeError('the makeup layer did not survive save/reopen: ' + ', '.join(names))
    authored = next(layer for layer in layers
                    if str(layer.get('Name') or layer.get('name')) == MAKEUP_LAYER)
    exported_layer = await call('export_texture_layer', {'expected_model': token,
                                'region_id': cheek['region_id'], 'layer_id': authored['layer_id']})
    if exported_layer['sha256'] != facts['makeup_png_sha256']:
        raise RuntimeError('makeup PNG pixels changed across cold reopen')
    await call('close_texture_editor', {'expected_model': token})
    nodes = await call('list_hair_nodes', {'category': 'HairFront'})
    node_count = len(nodes.get('nodes') or [])
    if node_count != facts['hair_nodes']:
        raise RuntimeError(f"hair node count changed across reopen: {node_count} vs {facts['hair_nodes']}")
    steps.record('reopen in a new process', {'face_parameter_kept': face_value,
                                             'face_parameter_id': face_id,
                                             'height_cm': height['live_cm'],
                                             'height_ui_cm': height['ui_cm'],
                                             'height_scale': height['scale'],
                                             'height_drift_cm': height_drift,
                                             'makeup_layer_present': True,
                                             'makeup_png_sha256_equal': True,
                                             'cheek_layers': len(layers),
                                             'hair_nodes': node_count,
                                             'seconds': round(time.monotonic() - started, 1)})

    if capture_reviews:
        facts['cold_review'] = await call('capture_review', {'expected_model': token,
                                    'views': ['body_front', 'body_back', 'face_front'], 'size': 512})


async def phase_wear(call, lab: pathlib.Path, facts: dict, steps: Steps,
                     capture_reviews: bool = False) -> None:
    # The texture-verification process has exited. Never carry its native
    # editor state into Dress-up or silently discard an edited in-memory model.
    source = pathlib.Path(facts['base_model'])
    if source != lab / 'saves' / facts['base_filename'] or sha256(source) != facts['base_sha256']:
        raise RuntimeError('Saved base changed before the separate Dress-up process')
    status = await wait_for_readiness(call, steps)
    if status.get('wear_transition_guard', {}).get('requires_new_process'):
        raise RuntimeError('Dress-up phase requires a fresh process without texture-editor entry')
    facts['wear_process_isolated'] = True
    steps.current = 'open the saved base model in Dress-up'
    wear = await call('get_wear_status')
    assembled = await call('open_wear_project', {'filename': facts.get('base_filename', BASE_FILENAME),
                                                 'expected_wear': wear['wear_token'],
                                                 'discard_unsaved': True})
    wear_token = assembled['wear_token']
    steps.current = 'import supplied XWear in Dress-up'
    imported = await call('import_xwear', {'filename': facts['xwear_name'], 'expected_wear': wear_token})
    wear_token = imported.get('wear_token', wear_token)
    items = imported.get('items') or []
    added = imported.get('added_item_ids') or []
    if not items or not added:
        raise RuntimeError('the imported outfit produced no Dress-up items')
    facts['wear_items'] = len(items)
    facts['wear_added'] = len(added)
    steps.record('import supplied XWear in Dress-up', {'items': len(items), 'added_items': len(added),
                                                   'mesh_names': [i.get('mesh') or i.get('name') for i in items][:6]})
    if capture_reviews:
        facts['wear_review'] = await call('capture_wear_review', {'expected_wear': wear_token,
                                          'views': ['body_front', 'body_back'], 'size': 512})

    steps.current = 'save assembly'
    assembly_name = facts.get('assembly_filename', ASSEMBLY_FILENAME)
    assembly = await call('save_wear_project', {'filename': assembly_name, 'expected_wear': wear_token})
    assembly_path = lab / 'saves' / assembly_name
    if not assembly_path.is_file():
        raise RuntimeError('save_wear_project reported success but the archive is missing')
    facts['assembly'] = str(assembly_path)
    facts['assembly_sha256'] = sha256(assembly_path)
    steps.record('save assembly', {'path': str(assembly_path), 'sha256': facts['assembly_sha256'],
                                   'detail': {k: assembly.get(k) for k in ('bytes', 'saved') if k in assembly}})

    steps.current = 'export VRM'
    vrm_name = facts.get('vrm_filename', VRM_FILENAME)
    exported = await call('export_wear_vrm', {'filename': vrm_name, 'expected_wear': wear_token,
                                              'title': 'VRoid-MCP clean-lab E2E', 'author': 'VRoid-MCP',
                                              'version': '1.0'})
    vrm_path = lab / 'saves' / vrm_name
    if not vrm_path.is_file():
        raise RuntimeError('export_wear_vrm reported success but the VRM is missing')
    facts['vrm'] = str(vrm_path)
    facts['vrm_sha256'] = sha256(vrm_path)
    steps.record('export VRM', {'path': str(vrm_path), 'sha256': facts['vrm_sha256'],
                                'detail': {k: exported.get(k) for k in ('filename', 'size', 'materials') if k in exported}})


def main() -> int:
    parser = argparse.ArgumentParser(description='Clean-lab end-to-end run')
    parser.add_argument('--source', required=True, help='VRoid Studio install directory to copy')
    parser.add_argument('--lab', required=True, help='new lab directory (must not exist)')
    parser.add_argument('--xwear', required=True, help='outfit .xwear to import')
    parser.add_argument('--json', dest='json_out', default='', help='write the step report here')
    parser.add_argument('--keep-lab-on-failure', action='store_true')
    parser.add_argument('--capture-reviews', action='store_true', help='retain native before/cold/assembly renders')
    args = parser.parse_args()

    source = pathlib.Path(args.source).resolve()
    lab = pathlib.Path(args.lab).resolve()
    xwear = pathlib.Path(args.xwear).resolve()
    steps = Steps()
    started = time.time()
    report = {'schema': 'vroid-clean-lab-e2e-v1', 'started': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
              'source': str(source), 'lab': str(lab), 'xwear': str(xwear), 'manual_file_edits': False,
              'code_changes_during_run': False,
              'sequence_note': 'The makeup layer is created before the height change: entering the native '
                               'texture editor immediately after a body height change makes this VRoid build '
                               'touch an empty Body overlay mesh and the process dies. Hair precedes final '
                               'live-height calibration. Cold texture verification and Dress-up use separate '
                               'processes to avoid an unresolved native transition crash; no in-memory edits '
                               'are silently discarded.'}

    def finish(code: int) -> int:
        report['steps'] = steps.rows
        report['finished'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
        report['seconds'] = round(time.time() - started, 1)
        report['ok'] = code == 0
        report['exit_code'] = code
        if args.json_out:
            target = pathlib.Path(args.json_out)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(report, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
        print(json.dumps({'ok': report['ok'], 'exit_code': code, 'seconds': report['seconds'],
                          'lab': str(lab), 'vrm': report.get('vrm')}, ensure_ascii=False))
        return code

    if closet_guard.present():
        report['reason'] = 'VROID_CLOSET_CRASH_KEY present; remove it before an end-to-end run'
        steps.record('preflight', {'reason': report['reason']}, 'fail')
        return finish(2)
    if lab.exists():
        report['reason'] = f'lab already exists: {lab}'
        steps.record('preflight', {'reason': report['reason']}, 'fail')
        return finish(2)
    if not (source / 'VRoidStudio.exe').is_file() or not xwear.is_file():
        report['reason'] = 'source install or .xwear is missing'
        steps.record('preflight', {'reason': report['reason']}, 'fail')
        return finish(2)

    started_lab = time.monotonic()
    copied = subprocess.run([sys.executable, str(PROJECT / 'prepare_lab.py'), '--source', str(source),
                             '--lab', str(lab)], capture_output=True, text=True)
    if copied.returncode != 0:
        report['reason'] = 'prepare_lab failed: ' + (copied.stderr or copied.stdout).strip()
        steps.record('prepare clean lab', {'reason': report['reason']}, 'fail')
        return finish(2)
    (lab / 'saves').mkdir(parents=True, exist_ok=True)
    (lab / 'reviews').mkdir(parents=True, exist_ok=True)
    xwear_name = xwear.name
    shutil.copy2(xwear, lab / 'saves' / xwear_name)
    report['lab_app_files'] = len(list((lab / 'app').rglob('*')))
    report['xwear_name'] = xwear_name
    steps.record('prepare clean lab', {'seconds': round(time.monotonic() - started_lab, 1),
                                       'app_files': report['lab_app_files'],
                                       'copied_xwear': xwear_name,
                                       'install_manifest': str(lab / 'source-manifest.json')})

    facts: dict = {'xwear_name': xwear_name}
    try:
        facts.update(asyncio.run(session(lab, None, lambda call: phase_edit(call, lab, steps, args.capture_reviews))))
        report['base_model'] = facts.get('base_model')
        report['base_sha256'] = facts.get('base_sha256')
        asyncio.run(session(lab, pathlib.Path(facts['base_model']),
                            lambda call: phase_reopen(call, lab, facts, steps, args.capture_reviews)))
        asyncio.run(session(lab, None,
                            lambda call: phase_wear(call, lab, facts, steps, args.capture_reviews)))
        report['wear_process_isolated'] = facts['wear_process_isolated']
        report['height_checkpoints'] = {name: facts[name] for name in
                                       ('height_before_save', 'height_after_save', 'height_cold_reopen')}
        if args.capture_reviews:
            report['reviews'] = {name: facts[name] for name in ('edit_review', 'cold_review', 'wear_review')}
        report.update({k: facts.get(k) for k in ('assembly', 'assembly_sha256', 'vrm', 'vrm_sha256', 'wear_items')})
        inspection = vrm_inspect.inspect(pathlib.Path(facts['vrm']))
        report['vrm_inspection'] = inspection
        if not inspection['ok']:
            raise RuntimeError('independent VRM parse failed: ' + '; '.join(inspection['findings']))
        steps.record('independent VRM parse', {'vrm_version': inspection['vrm_version'],
                                               'humanoid_bones': inspection['humanoid']['count'],
                                               'expressions': len(inspection['expressions']['preset']),
                                               'spring_chains': inspection['spring_bone']['chains'],
                                               'spring_joints': inspection['spring_bone']['joints'],
                                               'colliders': inspection['spring_bone']['colliders'],
                                               'meshes': inspection['meshes'], 'materials': inspection['materials'],
                                               'images': inspection['images'], 'findings': inspection['findings']})
    except Exception as error:  # report the exact step, then stop
        code = steps.fail(error)
        report['error'] = describe(error)
        report['lab_kept'] = True
        report['note'] = 'the lab is kept for inspection; delete it by hand when finished'
        return finish(code)
    return finish(0)


if __name__ == '__main__':
    raise SystemExit(main())
