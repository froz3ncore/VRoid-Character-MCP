"""F00 integration matrix: three height targets by two owned native Tops presets.

Uses a prepared, exclusive lab and never calls prepare_lab over existing work.
Each case creates a new model/process, uses unique save names, cold reopens and
exports VRM. Inputs and previous case evidence remain intact. This is a bounded
height/top matrix, not arbitrary anatomy or external garment fit coverage.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import uuid

import e2e_clean_lab as e2e
from vroid_mcp import closet_guard, lab_lock
from vroid_mcp.supported_builds import validate_assembly


async def tops_catalog(call):
    tops, offset = [], 0
    while True:
        page = await call('list_clothing_presets', {'offset': offset, 'limit': 200})
        tops.extend(p for p in page['presets'] if p['category'] == 'Tops')
        if len(tops) >= 2 or page.get('next_offset') is None:
            break
        offset = page['next_offset']
    if len(tops) < 2:
        raise RuntimeError('Two owned native Tops presets are required')
    return tops[:2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('lab', 'xwear', 'out'):
        parser.add_argument('--' + key, required=True, type=Path)
    args = parser.parse_args()
    lab, asset, out = args.lab.resolve(), args.xwear.resolve(), args.out.resolve()
    if not (lab / 'app/VRoidStudio.exe').is_file() or not asset.is_file() or out.exists():
        parser.error('Use a prepared lab, existing XWear and new output directory')
    if out.is_relative_to(lab) or lab.is_relative_to(out):
        parser.error('Output and lab must be separate')
    before = e2e.sha256(asset)
    destination = lab / 'saves' / asset.name
    if destination.resolve() != destination:
        parser.error('Lab saves/ must be a physical directory')
    if destination.exists():
        if e2e.sha256(destination) != before:
            parser.error('An existing different XWear has the same name; nothing was replaced')
    try:
        validate_assembly(lab / 'app/GameAssembly.dll')
        if closet_guard.present():
            raise RuntimeError('Known crash registry key exists; follow RECOVERY.md')
        handle = lab_lock.acquire(lab)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                with asset.open('rb') as source, destination.open('xb') as target:
                    shutil.copyfileobj(source, target)
            if e2e.sha256(destination) != before:
                raise RuntimeError('Copied XWear does not match the input')
        finally:
            lab_lock.release(handle)
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {'schema': 'vroid-f00-height-tops-matrix-v1', 'lab': str(lab),
              'xwear_sha256': before, 'cases': [], 'ok': False,
              'scope': 'F00, 3 height targets x 2 native Tops. Each case runs native edit/save/'
                       'cold reopen/import/sample accessory/assembly save/VRM parse and renders. '
                       'Not M00, arbitrary body topology, complex XWear fit or art adoption.'}
    try:
        catalog = asyncio.run(e2e.session(lab, None, tops_catalog))
        report['clothing_presets'] = catalog
        run_id = uuid.uuid4().hex[:8]
        for height, delta in [('short', -8.0), ('medium', -2.0), ('tall', 6.0)]:
            for number, top in enumerate(catalog):
                case_id = f'{height}-top{number + 1}'
                print('MATRIX_CASE ' + case_id, flush=True)
                steps = e2e.Steps()
                case = {'case_id': case_id, 'height_delta_cm': delta,
                        'clothing_preset_id': top['id'], 'steps': []}
                report['cases'].append(case)
                scenario = {**case, 'filename_prefix': f'matrix-{run_id}-{case_id}'}
                facts = asyncio.run(e2e.session(lab, None,
                    lambda call: e2e.phase_edit(call, lab, steps, True, scenario)))
                facts['xwear_name'] = asset.name
                asyncio.run(e2e.session(lab, Path(facts['base_model']),
                    lambda call: e2e.phase_reopen(call, lab, facts, steps, True)))
                asyncio.run(e2e.session(lab, None,
                    lambda call: e2e.phase_wear(call, lab, facts, steps, True)))
                inspected = e2e.vrm_inspect.inspect(Path(facts['vrm']))
                if not inspected['ok']:
                    raise RuntimeError('Independent VRM findings: ' + str(inspected['findings']))
                case.update(ok=True, facts=facts, vrm_inspection=inspected, steps=steps.rows)
                (out / (case_id + '.json')).write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding='utf8')
                print('MATRIX_PASS ' + case_id, flush=True)
        report['source_xwear_unchanged'] = e2e.sha256(asset) == before
        if not report['source_xwear_unchanged']:
            raise AssertionError('The input XWear changed')
        report['ok'] = True
    except Exception as error:
        report['error'] = e2e.describe(error)
        if report['cases']:
            report['cases'][-1].update(ok=False, error=str(error), steps=steps.rows)
    finally:
        report['seconds'] = round(time.monotonic() - started, 1)
        (out / 'matrix.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print('MATRIX_REPORT ' + str(out / 'matrix.json'), flush=True)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
