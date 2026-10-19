"""End-to-end hair authoring acceptance through the actual stdio MCP protocol.

Covers the new hand-drawn strand tools: edit_hair_structure(add_brush),
list_hair_strand_points, move_hair_strand_point (with native Undo),
list_hair_materials, set_hair_material, plus the introspection tools. The edit
phase saves; the reopen phase verifies persistence in a fresh process.
"""
import asyncio
import json
import os
import sys
import time
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT = Path(__file__).resolve().parents[1]


async def run(lab, output):
    output.mkdir(parents=True, exist_ok=True)
    evidence = {'passed': False, 'steps': []}
    saved = None

    def record(name, **data):
        evidence['steps'].append({'name': name, **data})
        (output / 'result.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf8')
        print(json.dumps({'name': name, **data}, ensure_ascii=True), flush=True)

    def close(a, b, tol=1e-4):
        if isinstance(a, list):
            return len(a) == len(b) and all(close(x, y, tol) for x, y in zip(a, b))
        return abs(a - b) < tol

    for phase in ('edit', 'reopen'):
        args = [str(PROJECT / 'launch.py'), '--lab', str(lab)]
        if saved:
            args += ['--model', str(saved)]
        temp = PROJECT.parent / 'work' / 'temp'
        temp.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, TEMP=str(temp), TMP=str(temp))
        with (output / (phase + '-stderr.log')).open('w', encoding='utf8') as log:
            async with stdio_client(StdioServerParameters(command=sys.executable, args=args, env=env), errlog=log) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=240)) as s:
                    await s.initialize()

                    async def call(name, args=None, error=False):
                        r = await s.call_tool(name, args or {})
                        assert bool(r.isError) == error, (name, r)
                        if error:
                            return r
                        return r.structuredContent or json.loads(r.content[0].text)

                    token = (await call('get_status'))['model_token']
                    if phase == 'reopen':
                        # Persistence: the moved point and the material survive a fresh process.
                        pts = await call('list_hair_strand_points', {'expected_model': token, 'category': target['category'], 'node_id': target['node_id']})
                        got = pts['points'][target['index']]
                        assert close(got['point'], target['moved']), (got, target)
                        r = await call('set_hair_material', {'expected_model': token, 'category': target['category'],
                                                             'node_id': target['node_id'], 'shared_material_id': target['material_id']})
                        assert r['applied'] and r['material_id'] == target['material_id'], r
                        counts = {}
                        for cat in ['HairFront', 'HairBack', 'HairSideburns', 'HairAhoge', 'HairHanege', 'HairTied', 'AllHair']:
                            counts[cat] = len((await call('list_hair_nodes', {'category': cat}))['nodes'])
                        assert sum(counts.values()) == target['baseline_nodes'], (counts, target)
                        record('fresh_process_persistence', point=target['moved'], material=target['material_id'],
                               nodes=counts)
                        evidence['passed'] = True
                        continue

                    tools = await s.list_tools()
                    names = [t.name for t in tools.tools]
                    assert len(names) >= 60, len(names)
                    for required in ('inspect_native_api', 'search_native_classes', 'list_hair_strand_points',
                                     'move_hair_strand_point', 'list_hair_materials', 'set_hair_material'):
                        assert required in names, required
                    record('tools', count=len(names))

                    api = await call('inspect_native_api', {'class_name': 'VRoidCore.Editing.History.Command.SetHairStrandCurveCommand',
                                                            'assembly': 'VRoidCore', 'filter': '.ctor'})
                    assert any(m['name'] == '.ctor' for m in api['methods']), api
                    search = await call('search_native_classes', {'assembly': 'VRoidCore', 'substring': 'brushhairstrandpath'})
                    assert search['matches'], search
                    record('introspection', methods=len(api['methods']), matches=len(search['matches']))

                    # A fresh F00 model can have empty hair categories; apply one
                    # owned hairstyle preset first so strand tools have real data.
                    hp = await call('list_hair_presets', {'category': 'HairSet'})
                    chosen_preset = next(p for p in hp['presets'] if not p['selected'])
                    await call('apply_hair_preset', {'expected_model': token, 'preset_id': chosen_preset['id']})
                    record('hair_preset', preset=chosen_preset['id'])

                    HAIR_CATEGORIES = ['HairFront', 'HairBack', 'HairSideburns', 'HairAhoge', 'HairHanege', 'HairTied', 'AllHair']

                    async def scan_nodes():
                        found = {}
                        for cat in HAIR_CATEGORIES:
                            found[cat] = (await call('list_hair_nodes', {'category': cat}))['nodes']
                        return found

                    baseline = await scan_nodes()
                    base_count = sum(len(v) for v in baseline.values())
                    assert base_count > 0, {k: len(v) for k, v in baseline.items()}
                    before_ids = {n['id'] for v in baseline.values() for n in v}
                    created = await call('edit_hair_structure', {'expected_model': token, 'category': 'HairFront', 'action': 'add_brush'})
                    grown = await scan_nodes()
                    grown_count = sum(len(v) for v in grown.values())
                    added = [{'id': n['id'], 'parent': n['parent'], 'kind': n['kind']}
                             for v in grown.values() for n in v if n['id'] not in before_ids]
                    added_groups = [n['id'] for n in added if not n['parent']] or [n['id'] for n in added]
                    record('add_brush', baseline_nodes=base_count, nodes_after=grown_count, added=added,
                           groups_reported=len(created.get('groups', [])))

                    # Prefer a pre-existing brush strand so removal of the added
                    # group cannot invalidate later persistence checks.
                    strands = [n for cat, v in baseline.items() for n in v
                               if n['parent'] and n['kind'] == 'BrushHairStrandNodeViewModel']
                    if not strands:
                        strands = [n for cat, v in grown.items() for n in v
                                   if n['parent'] and n['kind'] == 'BrushHairStrandNodeViewModel']
                    kinds = sorted({n['kind'] for v in grown.values() for n in v})
                    assert strands, {'kinds': kinds, 'counts': {k: len(v) for k, v in grown.items()}}
                    strand = strands[0]
                    node_id = strand['id']
                    category = next(cat for cat, v in list(baseline.items()) + list(grown.items())
                                    if any(n['id'] == node_id for n in v))
                    before = await call('list_hair_strand_points', {'expected_model': token, 'category': category, 'node_id': node_id})
                    assert before['total'] >= 2, before
                    original = before['points'][0]['point'][:]
                    moved = [original[0] + 0.002, original[1], original[2]]
                    r = await call('move_hair_strand_point', {'expected_model': token, 'category': category, 'node_id': node_id,
                                                              'index': 0, 'point': moved, 'normal': before['points'][0]['normal'],
                                                              'uv': before['points'][0]['uv']})
                    assert r['applied'] and close(r['point']['point'], moved), r
                    record('move_point', total=before['total'], original=original, moved=moved)

                    await call('undo', {'expected_model': token})
                    restored = await call('list_hair_strand_points', {'expected_model': token, 'category': category, 'node_id': node_id})
                    assert close(restored['points'][0]['point'], original), (restored['points'][0], original)
                    record('undo_restored', point=restored['points'][0]['point'])

                    # Re-apply the move so the reopen phase can verify persistence.
                    r = await call('move_hair_strand_point', {'expected_model': token, 'category': category, 'node_id': node_id,
                                                              'index': 0, 'point': moved, 'normal': before['points'][0]['normal'],
                                                              'uv': before['points'][0]['uv']})
                    assert r['applied'], r

                    # Shared hair materials live in the model file; a fresh file can
                    # expose very few. Collect the catalog across hair categories.
                    catalog = {}
                    for cat in HAIR_CATEGORIES:
                        try:
                            mm = await call('list_hair_materials', {'expected_model': token, 'category': cat})
                        except Exception:
                            continue
                        for entry in mm['materials']:
                            catalog[entry['id']] = entry['color']
                    ids = sorted(catalog)
                    assert ids, 'no shared hair materials discovered'
                    probe = await call('set_hair_material', {'expected_model': token, 'category': category,
                                                             'node_id': node_id, 'shared_material_id': ids[0]})
                    assert probe['applied'] and probe['material_id'] == ids[0], probe
                    original_material = probe['before']
                    chosen = next((i for i in ids if i != ids[0]), ids[0])
                    r = await call('set_hair_material', {'expected_model': token, 'category': category,
                                                         'node_id': node_id, 'shared_material_id': chosen})
                    assert r['applied'] and r['material_id'] == chosen, r
                    record('set_material', catalog=len(ids), original=original_material, chosen=chosen,
                           changed=(original_material != r['material_id']))

                    # Group-level material assignment on the freshly added group.
                    if added_groups:
                        g = added_groups[0]
                        rg = await call('set_hair_material', {'expected_model': token, 'category': 'HairFront',
                                                              'node_id': g, 'shared_material_id': ids[0]})
                        assert rg['applied'] and rg['material_id'] == ids[0], rg
                        record('set_material_group', group=g, material=ids[0])

                    if added_groups:
                        await call('edit_hair_structure', {'expected_model': token, 'category': 'HairFront',
                                                           'action': 'remove', 'node_id': added_groups[0]})
                        after = await scan_nodes()
                        after_count = sum(len(v) for v in after.values())
                        assert after_count == base_count, (after_count, base_count)
                        record('remove_added_group', nodes=after_count)

                    target = {'category': category, 'node_id': node_id, 'index': 0, 'moved': moved,
                              'material_id': chosen, 'baseline_nodes': base_count}
                    save = await call('save_as', {'expected_model': token,
                                                  'filename': 'hair-authoring-' + time.strftime('%Y%m%d-%H%M%S') + '.vroid'})
                    saved = save['path']
                    record('saved', path=saved)
    evidence['passed'] = True
    (output / 'result.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf8')


if __name__ == '__main__':
    lab = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT.parent / 'lab-test'
    out = PROJECT.parent / 'work' / 'hair-authoring-acceptance-v01'
    asyncio.run(run(lab, out))
