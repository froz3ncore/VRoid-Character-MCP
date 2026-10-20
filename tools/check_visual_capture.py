"""Capture twice from one saved model with locked framing and compare exact RGBA.

Uses one exclusive prepared lab. Does not save or overwrite the input model.
It records repeatability of this static case, not approval of a golden image.
"""
import argparse
import asyncio
import json
from pathlib import Path

import e2e_clean_lab as e2e
import visual_regression


async def capture_pair(call):
    state = await e2e.wait_for_readiness(call, e2e.Steps())
    args = {'expected_model': state['model_token'],
            'views': ['body_front', 'body_back', 'face_front'], 'size': 512}
    before = await call('capture_review', {**args, 'label': 'Repeatability candidate baseline'})
    after = await call('capture_review', {**args, 'label': 'Repeatability second capture',
                                         'baseline_id': before['capture_id']})
    return before, after, state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('lab', 'model', 'out'):
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    lab, model, out = args.lab.resolve(), args.model.resolve(), args.out.resolve()
    if not model.is_relative_to(lab / 'saves') or not model.is_file() or out.exists():
        parser.error('Use a saved model inside this lab and a new output directory')
    if out.is_relative_to(lab) or lab.is_relative_to(out):
        parser.error('Output and lab must be separate')
    out.mkdir(parents=True, exist_ok=False)
    report = {'schema': 'vroid-native-visual-repeatability-v1', 'model': str(model),
              'input_sha256': e2e.sha256(model), 'ok': False,
              'baseline_approval': 'pending_human_review'}
    try:
        before, after, state = asyncio.run(e2e.session(lab, model, capture_pair))
        report.update(baseline=before['manifest_path'], candidate=after['manifest_path'],
                      toolset_hash=state['toolset_hash'],
                      app_sha256=e2e.sha256(lab / 'app/GameAssembly.dll'))
        compared = visual_regression.compare(before['manifest_path'], after['manifest_path'],
                                              out / 'comparison')
        report['comparison'] = compared
        report['source_unchanged'] = e2e.sha256(model) == report['input_sha256']
        report['ok'] = compared['within_threshold'] and report['source_unchanged']
    except Exception as error:
        report['error'] = e2e.describe(error)
    (out / 'repeatability.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({'ok': report['ok'], 'report': str(out / 'repeatability.json')}))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
