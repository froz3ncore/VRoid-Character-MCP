"""Failure and selection boundaries at the public session tool entry points."""
import asyncio

import pytest

from vroid_mcp import server


@pytest.fixture
def session_tools(monkeypatch, tmp_path):
    instances, events = [], []
    class FakeRuntime:
        def __init__(self, lab):
            self.mode, self.pid, self.dead = 'copy', None, False
            self.fail_adopt = False
            instances.append(self)
        def start(self):
            events.append(('start', self))
        async def initialize(self, *args): pass
        def attach(self, pid):
            self.mode, self.pid = 'attached', pid
            events.append(('attach', pid))
        async def adopt(self):
            if self.fail_adopt:
                raise RuntimeError('adoption failed')
            return {'adopted': True}
        async def status(self):
            return {'mode': self.mode, 'pid': self.pid}
        def close(self):
            events.append(('close', self.mode, self.pid))
            self.dead = True
            return {'background_restored': True}
    monkeypatch.setattr(server, 'Runtime', FakeRuntime)
    monkeypatch.setattr(server.bridge, 'find_open_vroid', lambda _: [
        {'pid': 100, 'path': str(tmp_path / 'external' / 'VRoidStudio.exe')}])
    monkeypatch.setattr(server.bridge, 'validate_assembly', lambda _: None)
    mcp = server.create_server(tmp_path, 'F00')
    async def invoke(name, **args):
        return await mcp._tool_manager.get_tool(name).fn(**args)
    return invoke, instances, events


def test_ambiguous_process_selection_does_not_touch_current_session(session_tools, monkeypatch):
    invoke, instances, events = session_tools
    monkeypatch.setattr(server.bridge, 'find_open_vroid', lambda _: [
        {'pid': 100, 'path': 'a/VRoidStudio.exe'}, {'pid': 101, 'path': 'b/VRoidStudio.exe'}])
    with pytest.raises(ValueError, match='Select one'):
        asyncio.run(invoke('attach_open_vroid'))
    assert events == []


def test_unknown_build_does_not_close_running_copy(session_tools, monkeypatch):
    invoke, instances, events = session_tools
    async def scenario():
        await invoke('get_status')
        def refuse(path): raise RuntimeError('Untested VRoid binary')
        monkeypatch.setattr(server.bridge, 'validate_assembly', refuse)
        with pytest.raises(RuntimeError, match='Untested'):
            await invoke('attach_open_vroid', pid=100, discard_copy_unsaved=True)
    asyncio.run(scenario())
    assert len(instances) == 1 and not instances[0].dead
    assert not any(e[0] == 'close' for e in events)


def test_copy_requires_explicit_discard_before_attachment(session_tools):
    invoke, instances, events = session_tools
    async def scenario():
        await invoke('get_status')
        with pytest.raises(ValueError, match='discard_copy_unsaved'):
            await invoke('attach_open_vroid', pid=100)
    asyncio.run(scenario())
    assert not instances[0].dead
    assert not any(e[0] == 'attach' for e in events)


def test_same_target_is_idempotent_and_restart_only_detaches(session_tools):
    invoke, instances, events = session_tools
    async def scenario():
        await invoke('attach_open_vroid', pid=100)
        await invoke('attach_open_vroid', pid=100)
        assert len([e for e in events if e[0] == 'attach']) == 1
        result = await invoke('restart_session')
        assert result['detached']
    asyncio.run(scenario())
    assert not any(e[0] == 'start' for e in events)


def test_failed_adoption_releases_attachment_and_allows_retry(session_tools, monkeypatch):
    invoke, instances, events = session_tools
    cls = type(instances[0])
    original = cls.adopt
    async def fail(self): raise RuntimeError('adoption failed')
    monkeypatch.setattr(cls, 'adopt', fail)
    async def scenario():
        with pytest.raises(RuntimeError, match='adoption failed'):
            await invoke('attach_open_vroid', pid=100)
        assert instances[-2].dead and instances[-1].mode == 'copy'
        monkeypatch.setattr(cls, 'adopt', original)
        assert (await invoke('attach_open_vroid', pid=100))['mode'] == 'attached'
    asyncio.run(scenario())
    assert ('close', 'attached', 100) in events
