"""Native body/texture guard regression on one exclusive lab and a saved copy.

Checks all three public body-writing routes, confirms rejection before editor
entry, then saves a new file and verifies editor entry in a fresh process.
The input model is never overwritten. No unsafe editor call is forced through.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vroid_mcp.runtime import Runtime


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def check(lab, model, report):
    original = sha(model)
    saved = 'guard-recovery-' + uuid.uuid4().hex[:10] + '.vroid'
    runtime = Runtime(lab)
    try:
        await asyncio.to_thread(runtime.start)
        state = await runtime.initialize(model_file=model)
        token = state['model_token']
        report['initial_pid'] = runtime.pid
        regions = await runtime.parameter_call('list_texture_regions', {'expected_model': token})
        cheek = next(r['region_id'] for r in regions['regions'] if r['part'] == 'Cheek')
        await runtime.parameter_call('open_texture_editor', {'expected_model': token, 'region_id': cheek}, True)
        await runtime.parameter_call('close_texture_editor', {'expected_model': token}, True)
        report['initial_editor_entry'] = True
        report['routes'] = []
        for route in ('set_body_params', 'set_parameters', 'set_height'):
            body = await runtime.list_params('body')
            height = next(p for p in body['parameters'] if p['id'] == 'body/WholeBody/002')
            next_value = min(height['max'], height['value'] + .03)
            if next_value == height['value']:
                next_value = height['value'] - .03
            changes = [{'id': height['id'], 'value': next_value}]
            if route == 'set_body_params':
                result = await runtime.set_params('body', token, changes)
            elif route == 'set_parameters':
                result = await runtime.parameter_call('set_parameters',
                    {'expected_model': token, 'domain': 'body', 'changes': changes}, True)
            else:
                measured = await runtime.parameter_call('get_height')
                result = await runtime.set_height(token, measured['centimeters'] - 1)
            if result.get('ok') is False:
                raise RuntimeError('Native body write failed: ' + str(result))
            try:
                await runtime.parameter_call('open_texture_editor',
                    {'expected_model': token, 'region_id': cheek}, True)
            except RuntimeError as error:
                if 'TEXTURE_EDITOR_REOPEN_REQUIRED' not in str(error):
                    raise
            else:
                raise AssertionError('The dangerous editor entry was not refused')
            health = await runtime.status()
            if not health['model_ready'] or health['writes_blocked']:
                raise AssertionError('Guard rejection damaged the running session')
            report['routes'].append({'route': route, 'rejected_before_editor': True,
                                     'model_ready': True, 'guard': health['texture_editor_guard']})
        await runtime.save_as(saved, token)
        report['saved_copy'] = str(lab / 'saves' / saved)
    finally:
        await asyncio.to_thread(runtime.close)
    fresh = Runtime(lab)
    try:
        await asyncio.to_thread(fresh.start)
        state = await fresh.initialize(model_file=lab / 'saves' / saved)
        report['reopened_pid'] = fresh.pid
        token = state['model_token']
        regions = await fresh.parameter_call('list_texture_regions', {'expected_model': token})
        cheek = next(r['region_id'] for r in regions['regions'] if r['part'] == 'Cheek')
        await fresh.parameter_call('open_texture_editor', {'expected_model': token, 'region_id': cheek}, True)
        report['cold_editor_entry'] = True
        await fresh.parameter_call('close_texture_editor', {'expected_model': token}, True)
    finally:
        await asyncio.to_thread(fresh.close)
    report['input_unchanged'] = sha(model) == original
    if not report['input_unchanged']:
        raise AssertionError('The input model changed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('lab', 'model', 'json'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    lab, model = args.lab.resolve(), args.model.resolve()
    if not model.is_relative_to(lab / 'saves') or not model.is_file() or model.suffix.lower() != '.vroid':
        parser.error('Use an existing .vroid inside this lab saves/ directory')
    if args.json.exists():
        parser.error('Choose a new report filename')
    report = {'schema': 'vroid-edit-sequence-native-v1', 'lab': str(lab),
              'input_model': str(model), 'ok': False}
    try:
        asyncio.run(check(lab, model, report))
        report['ok'] = True
    except Exception as error:
        report['error'] = str(error)
    with args.json.open('x', encoding='utf8') as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
