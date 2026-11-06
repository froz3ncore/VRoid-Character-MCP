import asyncio
import copy
import json
import struct

import pytest

from vroid_mcp.runtime import Runtime
from vroid_mcp.runtime_ordinary import check_vrm_container


def document(version=1):
    ext = ({'VRMC_vrm': {'specVersion': '1.0', 'meta': {'name': 'Test', 'authors': ['A']}}}
           if version else {'VRM': {'specVersion': '0.0', 'meta': {'title': 'Test', 'author': 'A'}}})
    return {'buffers': [{'byteLength': 4}], 'bufferViews': [{'buffer': 0, 'byteLength': 4}],
            'accessors': [{'bufferView': 0, 'count': 3}], 'nodes': [{'mesh': 0, 'skin': 0}],
            'skins': [{'joints': [0]}], 'meshes': [{'primitives': [{'attributes': {'POSITION': 0}, 'indices': 0}]}],
            'extensions': ext}


def glb(data):
    text = json.dumps(data).encode('utf-8'); text += b' ' * (-len(text) % 4)
    chunks = struct.pack('<I4s', len(text), b'JSON') + text + struct.pack('<I4s', 4, b'BIN\0') + b'\0' * 4
    return struct.pack('<4sII', b'glTF', 2, 12 + len(chunks)) + chunks


def harness(tmp_path, monkeypatch, *, opened=False, outcome='true', refuse=False):
    runtime = Runtime(tmp_path)
    calls = []; state = {'open': opened, 'staging': None}; values = {'hair': 17, 'face': 19, 'material_mode': 0}
    snapshot = lambda: {'settings': copy.copy(values), 'choices': {'material_mode': [{'index': 0, 'name': 'Default', 'value': 'None'}]}}
    async def sleep(*args): pass
    monkeypatch.setattr('vroid_mcp.runtime_ordinary.asyncio.sleep', sleep)
    async def settle(*args): return {'model_token': 'live'}
    async def call(op, args=None):
        calls.append((op, args))
        if op == 'status': return {'model_ready': True, 'model_token': 'live'}
        if op == 'vrm_export_state': return {'model_token': 'live', 'export_screen': state['open'], 'busy': False, 'ready': state['open']}
        if op == 'enter_vrm_export': state['open'] = True; return {}
        if op == 'leave_vrm_export': state['open'] = False; return {}
        if op == 'vrm_export_options': return snapshot()
        if op == 'apply_vrm_export_options':
            if not refuse: values.update(args['options'])
            return snapshot()
        if op == 'start_vrm_export':
            state['staging'] = args['path']
            if outcome == 'start_error': raise RuntimeError('dispatch failed')
            from pathlib import Path
            Path(args['path']).write_bytes(glb(document(args['version'])))
            return {'started': True}
        if op == 'vrm_export_status':
            return {'running': False, 'done': outcome == 'true', 'result': outcome == 'true',
                    'faulted': outcome == 'fault', 'canceled': outcome == 'cancel'}
        if op == 'finish_vrm_export': return {'released': True}
        raise AssertionError(op)
    runtime._settle, runtime._call = settle, call
    return runtime, calls, state


@pytest.mark.parametrize('option,value', [('hair', True), ('hair', 1.5), ('hair', -1), ('hair', 101),
                                        ('delete_transparent', 1), ('material_mode', -1), ('texture_mode', False), ('unknown', 1)])
def test_invalid_options_rejected_before_dispatch(tmp_path, monkeypatch, option, value):
    runtime, calls, _ = harness(tmp_path, monkeypatch)
    with pytest.raises(ValueError): asyncio.run(runtime.export_vrm('live', 'a.vrm', options={option: value}))
    assert calls == []


@pytest.mark.parametrize('value', ['', ' ', 123, 'a\n', 'x' * 161])
def test_model_version_validated_before_dispatch(tmp_path, monkeypatch, value):
    runtime, calls, _ = harness(tmp_path, monkeypatch)
    with pytest.raises(ValueError): asyncio.run(runtime.export_vrm('live', 'a.vrm', model_version=value))
    assert calls == []


@pytest.mark.parametrize('hair', [0, 100])
def test_options_overlay_observed_and_stage_reopen_readback(tmp_path, monkeypatch, hair):
    runtime, calls, _ = harness(tmp_path, monkeypatch, opened=True)
    result = asyncio.run(runtime.export_vrm('live', 'a.vrm', options={'hair': hair}, model_version='2'))
    names = [op for op, _ in calls]
    assert result['requested'] == {'hair': hair} and result['effective']['hair'] == hair
    assert result['effective']['face'] == 19 and not result['warnings']
    assert names.index('leave_vrm_export') < names.index('enter_vrm_export') < names.index('apply_vrm_export_options')
    assert names.count('leave_vrm_export') == 2  # fresh entry and rebuild; original ownership retained
    assert names.count('apply_vrm_export_options') == 3
    assert names.index('finish_vrm_export') > names.index('vrm_export_status')


def test_invalid_native_choice_never_sets_or_starts(tmp_path, monkeypatch):
    runtime, calls, _ = harness(tmp_path, monkeypatch)
    with pytest.raises(ValueError): asyncio.run(runtime.export_vrm('live', 'a.vrm', options={'material_mode': 1}))
    assert not any(op in {'apply_vrm_export_options', 'start_vrm_export'} for op, _ in calls)


def test_refused_settings_only_reapplied_once(tmp_path, monkeypatch):
    runtime, calls, _ = harness(tmp_path, monkeypatch, refuse=True)
    result = asyncio.run(runtime.export_vrm('live', 'a.vrm', options={'hair': 100}))
    assert sum(op == 'apply_vrm_export_options' for op, _ in calls) == 6
    assert result['effective']['hair'] == 17 and result['warnings']


@pytest.mark.parametrize('opened,leave,expected', [(False, None, False), (True, None, True), (False, False, True), (True, True, False)])
def test_leave_ownership(tmp_path, monkeypatch, opened, leave, expected):
    runtime, _, state = harness(tmp_path, monkeypatch, opened=opened)
    asyncio.run(runtime.export_vrm('live', 'a.vrm', leave=leave))
    assert state['open'] is expected


@pytest.mark.parametrize('outcome', ['false', 'fault', 'cancel', 'start_error'])
def test_uncertain_or_failed_task_retains_native_handles_and_screen(tmp_path, monkeypatch, outcome):
    runtime, calls, state = harness(tmp_path, monkeypatch, outcome=outcome)
    with pytest.raises(RuntimeError): asyncio.run(runtime.export_vrm('live', 'a.vrm'))
    assert not (tmp_path / 'saves' / 'a.vrm').exists()
    names = [op for op, _ in calls]
    assert names.count('start_vrm_export') == 1 and 'finish_vrm_export' not in names
    assert state['open'] and runtime.uncertain


def test_query_returns_real_choices_and_leaves_by_default(tmp_path, monkeypatch):
    runtime, _, state = harness(tmp_path, monkeypatch, opened=True)
    result = asyncio.run(runtime.get_vrm_export_options('live'))
    assert result['choices']['material_mode'][0]['name'] == 'Default'
    assert result['settings']['hair'] == 17 and not state['open']


@pytest.mark.parametrize('version', [0, 1])
@pytest.mark.parametrize('change', [lambda d: d.pop('buffers'), lambda d: d['buffers'][0].update(uri='outside.bin'),
                                  lambda d: d.update(images=[{'uri': 'outside.png'}]),
                                  lambda d: d['nodes'][0].update(mesh=5), lambda d: d['skins'][0].update(joints=[3])])
def test_both_versions_require_embedded_valid_resources(tmp_path, version, change):
    data = document(version); change(data); path = tmp_path / 'bad.vrm'; path.write_bytes(glb(data))
    with pytest.raises(ValueError): check_vrm_container(path, version)


def test_malformed_later_chunk_rejected(tmp_path):
    raw = bytearray(glb(document())); raw[-12:-8] = struct.pack('<I', 80)
    path = tmp_path / 'bad.vrm'; path.write_bytes(raw)
    with pytest.raises(ValueError): check_vrm_container(path, 1)


@pytest.mark.parametrize('change', [
    lambda d: d.update(textures=[{'source': 3}]),
    lambda d: d.update(textures=[{'source': 0}], images=[{'bufferView': 0}], materials=[{'pbrMetallicRoughness': {'baseColorTexture': {'index': 4}}}]),
    lambda d: d['meshes'][0]['primitives'][0].update(targets=[{'POSITION': 4}]),
    lambda d: d['accessors'][0].update(sparse={'count': 1, 'indices': {'bufferView': 4}, 'values': {'bufferView': 0}}),
    lambda d: d.update(scenes=[{'nodes': [4]}]),
])
def test_embedded_resource_indices_cover_materials_targets_sparse_and_scenes(tmp_path, change):
    data = document(); change(data); path = tmp_path / 'bad.vrm'; path.write_bytes(glb(data))
    with pytest.raises(ValueError): check_vrm_container(path, 1)


def test_timeout_retains_job_and_never_navigates(tmp_path, monkeypatch):
    runtime, calls, state = harness(tmp_path, monkeypatch)
    native = runtime._call
    async def call(op, args=None):
        if op == 'vrm_export_status':
            calls.append((op, args)); return {'running': True}
        return await native(op, args)
    runtime._call = call
    ticks = iter(range(0, 100000, 20))
    monkeypatch.setattr('vroid_mcp.runtime_ordinary.time.monotonic', lambda: next(ticks))
    with pytest.raises(TimeoutError): asyncio.run(runtime.export_vrm('live', 'a.vrm'))
    assert runtime.uncertain and state['open']
    assert all(op not in {'leave_vrm_export', 'finish_vrm_export'} for op, _ in calls)


def test_stale_model_before_start_never_dispatches(tmp_path, monkeypatch):
    runtime, calls, _ = harness(tmp_path, monkeypatch)
    native = runtime._call
    count = 0
    async def call(op, args=None):
        nonlocal count
        if op == 'status':
            count += 1
            if count > 1: return {'model_ready': True, 'model_token': 'other'}
        return await native(op, args)
    runtime._call = call
    with pytest.raises(ValueError, match='STALE_MODEL'): asyncio.run(runtime.export_vrm('live', 'a.vrm'))
    assert all(op != 'start_vrm_export' for op, _ in calls)


def test_native_setter_exception_blocks_cleanup_navigation(tmp_path, monkeypatch):
    runtime, calls, state = harness(tmp_path, monkeypatch)
    native = runtime._call
    async def call(op, args=None):
        if op == 'apply_vrm_export_options': raise RuntimeError('setter may have dispatched preview')
        return await native(op, args)
    runtime._call = call
    with pytest.raises(RuntimeError): asyncio.run(runtime.export_vrm('live', 'a.vrm', options={'hair': 100}))
    assert runtime.uncertain and state['open']
    assert all(op != 'finish_vrm_export' for op, _ in calls)


def test_no_options_keeps_observed_settings_without_setter(tmp_path, monkeypatch):
    runtime, calls, _ = harness(tmp_path, monkeypatch)
    result = asyncio.run(runtime.export_vrm('live', 'a.vrm'))
    assert result['effective']['hair'] == 17 and result['requested'] is None
    assert not any(op == 'apply_vrm_export_options' for op, _ in calls)


def test_completion_requires_consecutive_file_stability_before_release(tmp_path, monkeypatch):
    import os
    from pathlib import Path
    runtime, _, state = harness(tmp_path, monkeypatch)
    waits = 0; released_after = None
    native = runtime._call
    async def call(op, args=None):
        nonlocal released_after
        if op == 'finish_vrm_export': released_after = waits
        return await native(op, args)
    runtime._call = call
    async def sleep(*args):
        nonlocal waits
        if state['staging']:
            waits += 1
            if waits == 3:
                path = Path(state['staging']); stat = path.stat()
                os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10000000))
    monkeypatch.setattr('vroid_mcp.runtime_ordinary.asyncio.sleep', sleep)
    asyncio.run(runtime.export_vrm('live', 'a.vrm'))
    assert released_after >= 8


@pytest.mark.parametrize('kind', ['preview', 'missing', 'leave'])
def test_preview_missing_file_and_leave_timeouts_are_uncertain(tmp_path, monkeypatch, kind):
    from pathlib import Path
    runtime, calls, state = harness(tmp_path, monkeypatch)
    native = runtime._call
    async def call(op, args=None):
        if kind == 'preview' and op == 'vrm_export_state':
            result = await native(op, args); result['ready'] = False; return result
        if kind == 'leave' and op == 'leave_vrm_export': return {}
        result = await native(op, args)
        if kind == 'missing' and op == 'start_vrm_export': Path(state['staging']).unlink()
        return result
    runtime._call = call
    ticks = iter(range(0, 1000000, 2))
    monkeypatch.setattr('vroid_mcp.runtime_ordinary.time.monotonic', lambda: next(ticks))
    with pytest.raises(TimeoutError): asyncio.run(runtime.export_vrm('live', 'a.vrm'))
    assert runtime.uncertain
    assert not (tmp_path / 'saves' / 'a.vrm').exists()
    if kind in {'preview', 'missing'}: assert all(op != 'finish_vrm_export' for op, _ in calls)


@pytest.mark.parametrize('change', [
    lambda d: d['skins'][0].update(skeleton=6),
    lambda d: d['extensions']['VRMC_vrm']['meta'].update(thumbnailImage=3),
    lambda d: d['extensions']['VRMC_vrm'].update(firstPerson={'meshAnnotations': [{'node': 4}]}),
    lambda d: d['extensions']['VRMC_vrm'].update(expressions={'custom': {'smile': {'morphTargetBinds': [{'node': 4, 'index': 0}]}}}),
    lambda d: d['buffers'][0].update(byteLength=True),
])
def test_avatar_metadata_and_resource_types_reject_bad_references(tmp_path, change):
    data = document(); change(data); path = tmp_path / 'bad.vrm'; path.write_bytes(glb(data))
    with pytest.raises(ValueError): check_vrm_container(path, 1)


def test_native_navigation_exception_is_uncertain(tmp_path, monkeypatch):
    runtime, calls, state = harness(tmp_path, monkeypatch, opened=True)
    native = runtime._call
    async def call(op, args=None):
        if op == 'leave_vrm_export': raise RuntimeError('after possible screen transition')
        return await native(op, args)
    runtime._call = call
    with pytest.raises(RuntimeError): asyncio.run(runtime.export_vrm('live', 'a.vrm', leave=False))
    assert runtime.uncertain


def test_uncertain_export_status_is_inspectable_without_retry_or_release(tmp_path):
    from types import SimpleNamespace
    from vroid_mcp import bridge
    runtime = Runtime(tmp_path); runtime.uncertain = True
    calls = []
    runtime.script = SimpleNamespace(exports_sync=SimpleNamespace(call=lambda op, args: calls.append(op) or {'running': True}))
    result = asyncio.run(bridge.call(runtime, 'vrm_export_status', {'expected_model': 'live'}))
    assert result['running'] and calls == ['vrm_export_status']
    for op in ('start_vrm_export', 'finish_vrm_export', 'leave_vrm_export'):
        with pytest.raises(RuntimeError, match='PREVIOUS_CALL_UNCERTAIN'): asyncio.run(bridge.call(runtime, op))
    assert calls == ['vrm_export_status']
