"""Compare height/hair order and cold persistence in an exclusive prepared lab.

Creates four new F00 models with unique save names; never edits existing models.
The old-order control records the hair-induced change before saving. Three
hair-first cases must reach their targets, preserve live height and body scale
across a new process, and leave the saved source bytes unchanged.
"""
import argparse
import asyncio
import json
from pathlib import Path
import time
import uuid

import e2e_clean_lab as e2e


async def edited(call, lab, case, filename, steps):
    status = await e2e.wait_for_readiness(call, steps)
    token = status['model_token']
    presets = (await call('list_hair_presets', {'limit': 80}))['presets']
    hair = next(p for p in presets if p['category'] == 'HairSet')
    case['hair_preset'] = hair['id']
    case['initial'] = await e2e.height_checkpoint(call)
    if case['hair_first']:
        await call('apply_hair_preset', {'expected_model': token, 'preset_id': hair['id']})
        case['after_hair'] = await e2e.height_checkpoint(call)
    case['solver'] = await call('set_height', {'expected_model': token, 'centimeters': case['target_cm']})
    case['after_height'] = await e2e.height_checkpoint(call)
    e2e.verify_height(case['after_height'], target_cm=case['target_cm'])
    if not case['hair_first']:
        await call('apply_hair_preset', {'expected_model': token, 'preset_id': hair['id']})
        case['after_hair'] = await e2e.height_checkpoint(call)
    case['before_save'] = await e2e.height_checkpoint(call)
    if case['hair_first']:
        e2e.verify_height(case['before_save'], target_cm=case['target_cm'])
    case['saved'] = await call('save_as', {'expected_model': token, 'filename': filename})
    case['after_save'] = await e2e.height_checkpoint(call)
    e2e.verify_height(case['after_save'], expected=case['before_save'])
    case['path'] = str(lab / 'saves' / filename)
    case['sha256'] = e2e.sha256(Path(case['path']))


async def reopened(call, case, steps):
    await e2e.wait_for_readiness(call, steps)
    case['cold_reopen'] = await e2e.height_checkpoint(call)
    e2e.verify_height(case['cold_reopen'], expected=case['after_save'],
                      target_cm=case['target_cm'] if case['hair_first'] else None)
    case['cold_delta_cm'] = case['cold_reopen']['live_cm'] - case['after_save']['live_cm']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lab', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    lab, out = args.lab.resolve(), args.out.resolve()
    if not (lab / 'app/VRoidStudio.exe').is_file() or out.exists():
        parser.error('Use an idle prepared disposable lab and a new output directory')
    if out.is_relative_to(lab) or lab.is_relative_to(out):
        parser.error('Lab and output must be separate')
    out.mkdir(parents=True, exist_ok=False)
    report = {'schema': 'vroid-height-order-persistence-v1', 'lab': str(lab), 'cases': [], 'ok': False}
    started, run_id = time.monotonic(), uuid.uuid4().hex[:8]
    steps = e2e.Steps()
    try:
        for name, target, first in [('old-order', 157.8, False), ('hair-first-short', 151.8, True),
                                    ('hair-first-medium', 157.8, True), ('hair-first-tall', 165.8, True)]:
            case = {'case': name, 'target_cm': target, 'hair_first': first}
            report['cases'].append(case)
            print('HEIGHT_CASE ' + name, flush=True)
            filename = f'height-{run_id}-{name}.vroid'
            asyncio.run(e2e.session(lab, None, lambda call: edited(call, lab, case, filename, steps)))
            asyncio.run(e2e.session(lab, Path(case['path']), lambda call: reopened(call, case, steps)))
            case['source_unchanged'] = e2e.sha256(Path(case['path'])) == case['sha256']
            if not case['source_unchanged']:
                raise AssertionError('Cold reopen changed saved source bytes')
            case['ok'] = True
            (out / (name + '.json')).write_text(json.dumps(case, indent=2), encoding='utf8')
            print('HEIGHT_PASS ' + json.dumps(case['cold_reopen']), flush=True)
        report['ok'] = True
    except Exception as error:
        report['error'] = e2e.describe(error)
    finally:
        report['seconds'] = round(time.monotonic() - started, 1)
        (out / 'diagnosis.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print('HEIGHT_REPORT ' + str(out / 'diagnosis.json'), flush=True)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
