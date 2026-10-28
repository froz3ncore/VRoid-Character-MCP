import asyncio
import json
import struct
from types import SimpleNamespace

import pytest

from vroid_mcp import bridge
from vroid_mcp.runtime import Runtime
from vroid_mcp.runtime_ordinary import check_vrm_container


def test_attached_close_detaches_without_killing_process(monkeypatch, tmp_path):
    calls = []
    subject = Runtime(tmp_path)
    subject.mode = 'attached'
    subject.pid = 1234
    subject.device = SimpleNamespace(kill=lambda pid: calls.append(('kill', pid)))
    subject.script = SimpleNamespace(exports_sync=SimpleNamespace(release=lambda: calls.append('release') or {}),
                                     unload=lambda: calls.append('unload'))
    subject.session = SimpleNamespace(detach=lambda: calls.append('detach'))
    monkeypatch.setattr(bridge, 'record', lambda *args: None)
    subject.close()
    assert calls == ['release', 'unload', 'detach']
    assert subject.dead


def test_process_discovery_excludes_other_managed_labs(monkeypatch, tmp_path):
    other = tmp_path / 'other-lab'
    app = other / 'app'
    app.mkdir(parents=True)
    (other / '.mcp-owner.lock').touch()
    external = tmp_path / 'installed' / 'VRoidStudio.exe'
    rows = [SimpleNamespace(name='VRoidStudio.exe', pid=10, parameters={'path': str(app / 'VRoidStudio.exe')}),
            SimpleNamespace(name='VRoidStudio.exe', pid=11, parameters={'path': str(external)}),
            SimpleNamespace(name='unrelated.exe', pid=12, parameters={'path': str(external)})]
    monkeypatch.setattr(bridge.frida, 'get_local_device', lambda: SimpleNamespace(enumerate_processes=lambda **kw: rows))
    assert bridge.find_open_vroid(tmp_path / 'this-lab') == [{'pid': 11, 'path': str(external.resolve())}]


def test_failed_attached_release_reports_background_not_restored(monkeypatch, tmp_path):
    subject = Runtime(tmp_path)
    subject.mode = 'attached'
    def fail(): raise RuntimeError('release failed')
    subject.script = SimpleNamespace(exports_sync=SimpleNamespace(release=fail), unload=lambda: None)
    subject.session = SimpleNamespace(detach=lambda: None)
    monkeypatch.setattr(bridge, 'record', lambda *args: None)
    result = subject.close()
    assert result['detached'] and not result['background_restored']
    assert 'release failed' in result['release_error']


@pytest.mark.parametrize('op', ['open_texture_editor', 'open_wear_project',
                                'open_model', 'new_model'])
def test_attached_dangerous_transition_refused_before_dispatch(tmp_path, op):
    subject = Runtime(tmp_path)
    subject.mode = 'attached'
    calls = []
    subject.script = SimpleNamespace(exports_sync=SimpleNamespace(call=lambda *x: calls.append(x)))
    with pytest.raises(RuntimeError, match='ATTACHED_'):
        asyncio.run(subject._call(op, {}))
    assert calls == []


@pytest.mark.parametrize('token', ['', 'old'])
def test_list_parts_requires_current_model_before_native_action(tmp_path, token):
    subject = Runtime(tmp_path)
    calls = []
    async def native(op, args=None):
        calls.append(op)
        assert op == 'status'
        return {'model_ready': True, 'model_token': 'live'}
    subject._call = native
    with pytest.raises(ValueError):
        asyncio.run(subject.list_parts(token))
    assert calls == ([] if not token else ['status'])


def test_screenshot_empty_and_stale_token_never_prepare_capture(tmp_path):
    subject = Runtime(tmp_path)
    calls = []
    async def settle(*args): return {'model_token': 'live'}
    async def call(op, args=None): calls.append(op)
    subject._settle, subject._call = settle, call
    for token in ['', 'old']:
        with pytest.raises(ValueError):
            asyncio.run(subject.screenshot('front', token))
    assert calls == []


def test_attached_custom_item_save_is_refused_without_native_dispatch(tmp_path):
    subject = Runtime(tmp_path)
    subject.mode = 'attached'
    calls = []
    async def call(op, args=None): calls.append(op)
    subject._call = call
    with pytest.raises(RuntimeError, match='ATTACHED_CUSTOM_ITEM_SAVE_UNAVAILABLE'):
        asyncio.run(subject.save_custom_items('live', ['Iris']))
    assert calls == []


@pytest.mark.parametrize('types', [[], ['Iris', 'Iris'], [''], 'Iris'])
def test_invalid_custom_types_never_dispatch(tmp_path, types):
    subject = Runtime(tmp_path)
    calls = []
    async def call(op, args=None): calls.append(op)
    subject._call = call
    with pytest.raises(ValueError):
        asyncio.run(subject.save_custom_items('live', types))
    assert calls == []


def test_custom_save_verifies_file_and_registry_instead_of_native_return(tmp_path):
    import zipfile
    root = tmp_path / 'profile' / 'custom_items'
    root.mkdir(parents=True)
    target = root / 'new.vroidcustomitem'
    subject = Runtime(tmp_path)
    item = {'id': 'custom-id', 'group_type': 'native.Iris', 'path': str(target)}
    calls = []
    async def settle(*args): pass
    async def call(op, args=None):
        calls.append(op)
        if op == 'status': return {'model_ready': True, 'model_token': 'live'}
        if op == 'custom_item_state':
            return {'base_path': str(root), 'parts': [{'id': 'active', 'type': 'Iris', 'group_type': 'native.Iris'}],
                    'files': [item] if target.exists() else []}
        if op == 'save_custom_item':
            with zipfile.ZipFile(target, 'w') as z:
                z.writestr('v1customitem/meta.json', json.dumps({'rootTransferableGroupId': 'custom-id',
                            'rootTransferableGroupTypeId': 'native.Iris'}))
            return {'requested': True}  # not a persistence assertion
        raise AssertionError(op)
    subject._settle, subject._call = settle, call
    result = asyncio.run(subject.save_custom_items('live', ['Iris']))
    assert result['saved'][0]['sha256'] and result['saved'][0]['bytes'] > 0
    assert calls.count('save_custom_item') == 1


def write_glb(path, extension):
    payload = json.dumps({'extensions': {extension: {}}}).encode()
    payload += b' ' * (-len(payload) % 4)
    body = struct.pack('<I4s', len(payload), b'JSON') + payload
    path.write_bytes(struct.pack('<4sII', b'glTF', 2, 12 + len(body)) + body)


@pytest.mark.parametrize('version,extension', [(0, 'VRM'), (1, 'VRMC_vrm')])
def test_vrm_container_checks_version_and_length(tmp_path, version, extension):
    path = tmp_path / 'model.vrm'
    write_glb(path, extension)
    assert check_vrm_container(path, version)['format'].startswith('VRM')
    with pytest.raises(ValueError, match='extension missing'):
        check_vrm_container(path, 1 - version)
    path.write_bytes(path.read_bytes()[:-1])
    with pytest.raises(ValueError, match='length'):
        check_vrm_container(path, version)


def test_replacing_part_raises_reopen_guard_even_if_native_operation_fails(tmp_path):
    subject = Runtime(tmp_path)
    async def settle(*args): return {'model_token': 'live'}
    async def call(op, args=None):
        if op == 'status': return {'model_ready': True, 'model_token': 'live'}
        if op == 'list_parts': return {'parts': []}
        raise RuntimeError('native failure')
    subject._settle, subject._call = settle, call
    with pytest.raises(RuntimeError, match='native failure'):
        asyncio.run(subject.replace_part('live', 'sample.transferablegroup'))
    assert 'live' in subject.body_edited_tokens


def test_already_active_part_is_noop(tmp_path):
    subject = Runtime(tmp_path)
    calls = []
    async def settle(*args): return {'model_token': 'live'}
    async def call(op, args=None):
        calls.append(op)
        if op == 'status': return {'model_ready': True, 'model_token': 'live'}
        if op == 'list_parts': return {'parts': [{'id': 'existing.transferablegroup'}]}
        raise AssertionError('must not invoke the replacement')
    subject._settle, subject._call = settle, call
    result = asyncio.run(subject.replace_part('live', 'existing.transferablegroup'))
    assert result['reason'] == 'ALREADY_ACTIVE'
    assert calls == ['status', 'list_parts']
    assert not subject.body_edited_tokens
