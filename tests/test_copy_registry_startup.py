"""A failed copy registry guard must leave the newly spawned app suspended."""
from types import SimpleNamespace

import pytest

from vroid_mcp import bridge


@pytest.mark.parametrize('confirmed', [True, False, None])
def test_copy_resumes_only_after_synchronous_guard_confirmation(tmp_path, monkeypatch, confirmed):
    resumed, closed = [], []
    script = SimpleNamespace(on=lambda *a: None, load=lambda: None,
                             exports_sync=SimpleNamespace(health=lambda: {'copy_protocol_isolated': confirmed}))
    session = SimpleNamespace(on=lambda *a: None, create_script=lambda _: script)
    device = SimpleNamespace(spawn=lambda *a, **kw: 1234, attach=lambda _: session,
                             resume=resumed.append)
    subject = SimpleNamespace(lab=tmp_path, exe=tmp_path/'app/VRoidStudio.exe',
                              bridge_js=tmp_path/'bridge.js', run_dir=tmp_path/'run', events=[])
    monkeypatch.setattr(bridge, '_check_copy', lambda _: None)
    monkeypatch.setattr(bridge.lab_lock, 'acquire', lambda _: object())
    monkeypatch.setattr(bridge.frida, 'get_local_device', lambda: device)
    monkeypatch.setattr(bridge, '_environment', lambda _: {})
    monkeypatch.setattr(bridge, '_probe_config', lambda _: {})
    monkeypatch.setattr(bridge, 'script_text', lambda *a, **k: '')
    monkeypatch.setattr(bridge, 'close', closed.append)
    monkeypatch.setattr(bridge.closet_guard, 'enforce', lambda *a: pytest.fail('System registry must be preserved'))
    if confirmed:
        bridge.start(subject)
        assert resumed == [1234] and closed == []
    else:
        with pytest.raises(RuntimeError, match='COPY_REGISTRY_ISOLATION_UNAVAILABLE'):
            bridge.start(subject)
        assert resumed == [] and closed == [subject]
