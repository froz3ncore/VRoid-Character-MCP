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


@pytest.mark.parametrize('tool',['detach_open_vroid','restart_session','attach_open_vroid'])
def test_pending_native_release_does_not_rebind_attached_session(session_tools,monkeypatch,tool):
    invoke,instances,events=session_tools
    async def scenario():
        await invoke('attach_open_vroid',pid=100)
        current=instances[-1]
        current.close=lambda:dict(close_blocked=True,detached=False,pending_work=['custom task'])
        monkeypatch.setattr(server.bridge,'find_open_vroid',lambda _: [
            {'pid':101,'path':'E:/other/VRoidStudio.exe'}])
        result=await invoke(tool,**({'pid':101} if tool=='attach_open_vroid' else {}))
        assert result['close_blocked'] and not result.get('detached',False)
        assert instances[-1] is current and not current.dead
        assert len([event for event in events if event[0]=='attach'])==1
        assert (await invoke('get_status'))['mode']=='attached'
    asyncio.run(scenario())


@pytest.mark.parametrize('primary',[False,True])
def test_lifespan_shutdown_reports_pending_native_work_without_losing_runtime(tmp_path,monkeypatch,primary):
    instances=[]
    class PendingRuntime:
        def __init__(self,lab):
            self.mode='attached';self.dead=False
            instances.append(self)
        def close(self):return dict(close_blocked=True,pending_work=['custom task'])
    monkeypatch.setattr(server,'Runtime',PendingRuntime)
    mcp=server.create_server(tmp_path,'F00')
    async def scenario():
        with pytest.raises((ValueError,RuntimeError),match='PRIMARY_LIFESPAN_FAILURE' if primary else 'NATIVE_WORK_PENDING') as raised:
            async with mcp.settings.lifespan(mcp) as active:
                assert active is instances[0]
                if primary: raise ValueError('PRIMARY_LIFESPAN_FAILURE')
        if primary: assert 'NATIVE_WORK_PENDING' in str(raised.value.__notes__)
        assert len(instances)==1 and not instances[0].dead
    asyncio.run(scenario())


def test_failed_adoption_preserves_primary_error_when_cleanup_is_blocked(session_tools,monkeypatch):
    invoke,instances,events=session_tools
    cls=type(instances[0])
    async def failed_adoption(self):
        self.close=lambda:dict(close_blocked=True,pending_work=['native request'])
        raise ValueError('PRIMARY_ADOPTION_FAILURE')
    monkeypatch.setattr(cls,'adopt',failed_adoption)
    with pytest.raises(ValueError,match='PRIMARY_ADOPTION_FAILURE') as raised:
        asyncio.run(invoke('attach_open_vroid',pid=100))
    assert 'NATIVE_WORK_PENDING' in str(raised.value.__notes__)
    assert instances[-1].mode=='attached' and not instances[-1].dead


@pytest.mark.parametrize('phase',['adoption','initialization'])
@pytest.mark.parametrize('cleanup',['blocked','error'])
def test_retained_uninitialized_session_never_automatically_starts_or_rebinds(tmp_path,monkeypatch,phase,cleanup):
    instances=[];events=[]
    class PendingRuntime:
        fail=True
        def __init__(self,lab):
            self.mode='copy';self.pid=None;self.dead=False;self.pending=False
            self.script=object();self.session=object();self.pins=[object()]
            instances.append(self)
        def start(self):
            events.append(('start',self))
            if self.pending:raise RuntimeError('START_RETRIED_ON_PENDING_RUNTIME')
        async def initialize(self,*args):
            events.append(('initialize',self))
            if phase=='initialization' and self.fail:
                self.pending=True
                raise ValueError('PRIMARY_INITIALIZATION_FAILURE')
        def attach(self,pid):
            self.mode='attached';self.pid=pid
            events.append(('attach',self))
        async def adopt(self):
            events.append(('adopt',self))
            if self.fail:
                self.pending=True
                raise ValueError('PRIMARY_ADOPTION_FAILURE')
            return {'adopted':True}
        async def status(self):
            events.append(('native_status',self))
            return {'mode':self.mode,'pid':self.pid}
        async def list_parts(self,*args):
            events.append(('native_tool',self))
            return {}
        def close(self):
            events.append(('close',self))
            if self.pending:
                if cleanup=='error':raise RuntimeError('CLEANUP_UNKNOWN')
                return {'close_blocked':True,'pending_work':['native task']}
            self.dead=True
            return {'detached':True}
    monkeypatch.setattr(server,'Runtime',PendingRuntime)
    monkeypatch.setattr(server.bridge,'find_open_vroid',lambda _:[{'pid':100,'path':'E:/stub/VRoidStudio.exe'}])
    monkeypatch.setattr(server.bridge,'validate_assembly',lambda _:None)
    mcp=server.create_server(tmp_path,'F00')
    async def invoke(name,**args):return await mcp._tool_manager.get_tool(name).fn(**args)
    async def scenario():
        with pytest.raises(ValueError,match='PRIMARY_'):
            await invoke('attach_open_vroid',pid=100) if phase=='adoption' else await invoke('get_status')
        retained=instances[-1]
        script,session,pins=retained.script,retained.session,retained.pins
        count,previous=len(instances),list(events)
        status=await invoke('get_status')
        assert status['pending_session'] and status['writes_blocked'] and not status['model_ready']
        with pytest.raises(RuntimeError,match='SESSION_CLEANUP_PENDING'):
            await invoke('list_parts',expected_model='live')
        assert events==previous and len(instances)==count and instances[-1] is retained
        assert (retained.script,retained.session,retained.pins)==(script,session,pins) and not retained.dead
        retained.pending=False;PendingRuntime.fail=False
        result=await invoke('restart_session',discard_unsaved=True)
        assert not result.get('close_blocked') and instances[-1] is not retained
        assert not (await invoke('get_status')).get('pending_session')
    asyncio.run(scenario())


@pytest.mark.parametrize('liveness',['absent','alive','unknown'])
def test_restart_of_disconnected_owned_copy_requires_actual_process_absence(tmp_path,monkeypatch,liveness):
    from vroid_mcp import bridge
    from vroid_mcp.runtime import Runtime
    instances=[];events=[]
    class Device:
        def get_process(self,pid):
            events.append(('probe',pid))
            if liveness=='absent':raise bridge.frida.ProcessNotFoundError('already exited')
            if liveness=='unknown':raise RuntimeError('liveness unknown')
            return object()
        def kill(self,*args):raise AssertionError('must not kill a disconnected/reused PID')
    class Pin:
        def __exit__(self,*args):events.append('pin_released')
    class FakeNativeRuntime(Runtime):
        def __init__(self,lab):
            super().__init__(lab)
            instances.append(self)
        def start(self):
            events.append(('start',self))
            self.owns_process=True;self.pid=123;self.device=Device()
        async def initialize(self,*args):events.append(('initialize',self))
        async def status(self):return {'mode':self.mode,'dead':self.dead}
    monkeypatch.setattr(server,'Runtime',FakeNativeRuntime)
    mcp=server.create_server(tmp_path,'F00')
    async def invoke(name,**args):return await mcp._tool_manager.get_tool(name).fn(**args)
    async def scenario():
        await invoke('get_status')
        retained=instances[-1];retained.dead=True
        pin=Pin();retained._pending_custom_item_pins=[pin]
        result=await invoke('restart_session',discard_unsaved=True)
        if liveness=='absent':
            assert not result.get('close_blocked') and len(instances)==2
            assert retained._pending_custom_item_pins==[]
            assert events.index('pin_released')<events.index(('start',instances[-1]))
            assert result['dead'] is False
        else:
            assert result['close_blocked'] and len(instances)==1 and instances[-1] is retained
            assert retained._pending_custom_item_pins==[pin]
            assert 'pin_released' not in events
            assert len([event for event in events if isinstance(event,tuple) and event[0]=='start'])==1
        assert events.count(('probe',123))==1
    asyncio.run(scenario())
