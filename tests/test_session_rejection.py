"""Public session/bridge boundaries after guard refusal, reply loss and replacement."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from vroid_mcp import bridge, runtime_session, server
from vroid_mcp.runtime import Runtime


def public_server(monkeypatch, tmp_path, current):
    monkeypatch.setattr(server, 'Runtime', lambda _: current)
    current.start = lambda: None
    async def initialize(*unused):
        return {}
    current.initialize = initialize
    mcp = server.create_server(tmp_path, 'F00')
    return lambda name: mcp._tool_manager.get_tool(name).fn


@pytest.mark.parametrize('operation', ['exit_vroid', 'return_to_main_menu'])
@pytest.mark.parametrize('modal_persists',[True,False])
def test_attached_modal_between_preflight_and_send_keeps_model_and_recovery(tmp_path, monkeypatch, operation, modal_persists):
    current = Runtime(tmp_path)
    current.mode, current.pid = 'attached', 42
    blocked = False
    forwarded = []
    pending = None
    def rpc(name, args):
        nonlocal blocked, pending
        forwarded.append(name)
        if name == 'get_session_preflight':
            return {'verified':True}
        if name == 'attached_edit_begin':
            blocked = True
            pending = {'id':'ours','dispatches':0}
            return pending
        if name == 'attached_review':
            return {'recovery_token':'reviewed','pending_edit':pending}
        if name == 'attached_acknowledge':
            assert args['recovery_token'] == 'reviewed'
            pending = None
            return {'acknowledged':True}
        if name == 'attached_edit_finish':
            assert args['id'] == 'ours'
            pending = None
            return {'needs_review':False}
        if name == 'status':
            return {'model_ready':True,'model_token':'existing'}
        pytest.fail('unexpected native dispatch: ' + name)
    current.script = SimpleNamespace(exports_sync=SimpleNamespace(call=rpc))
    def os_window(_):
        nonlocal blocked
        visible = blocked
        blocked = visible and modal_persists
        return {'blocked':visible}
    monkeypatch.setattr(bridge.attached_ui, 'window_state', os_window)
    monkeypatch.setattr(runtime_session, 'verified_window', lambda _: '0x1')
    closed = []
    monkeypatch.setattr(runtime_session, 'ExitWatch', lambda _: SimpleNamespace(
        exited=lambda: False, close=lambda:closed.append('closed')))
    monkeypatch.setattr(runtime_session, 'DEADLINE', 0)
    fn = public_server(monkeypatch,tmp_path,current)
    async def run():
        nonlocal blocked
        await fn('get_status')()
        with pytest.raises(bridge.NativeCallNotSent, match='ATTACHED_OS_MODAL_BLOCKED'):
            await fn(operation)('existing', **({'close_attached':True} if operation == 'exit_vroid' else {}))
        assert operation not in forwarded and not getattr(current,'exit_watch',None)
        assert len(closed) == (1 if operation == 'exit_vroid' else 0)
        assert current.uncertain == modal_persists
        assert (pending is not None) == modal_persists
        blocked = False
        assert (await fn('get_status')())['model_token'] == 'existing'
        review = await fn('get_attached_state')()
        if pending is not None:
            assert review['pending_edit']['dispatches'] == 0
            await fn('acknowledge_attached_state')(review['recovery_token'])
        assert pending is None and not current.uncertain
    asyncio.run(run())


@pytest.mark.parametrize('lost_reply',[False,True])
def test_history_continue_depends_on_proven_dispatch_boundary(tmp_path,monkeypatch,lost_reply):
    current = Runtime(tmp_path)
    calls = []
    def rpc(op,args):
        calls.append((op,args))
        if op == 'undo' and len(calls) == 1:
            return {'frame':1,'task_id':1}
        if op == 'undo' and lost_reply:
            raise RuntimeError('RPC failed after possible native dispatch')
        if op == 'undo':
            return {'dispatched':False, 'reason':'HISTORY_PREWRITE_REJECTED', 'error':'STALE_MODEL'}
        if op == 'redo':
            return {'frame':1,'task_id':2}
        if op == 'list_face_params':
            return {'model_token':'new','parameters':[]}
        pytest.fail(op)
    async def confirmed(*unused):
        return {}
    current._task = current._settle = confirmed
    current.script = SimpleNamespace(exports_sync=SimpleNamespace(call=rpc))
    fn = public_server(monkeypatch,tmp_path,current)
    async def run():
        rows = await fn('run_batch')([
            {'tool':'undo','args':{'expected_model':'old','steps':2}},
            {'tool':'redo','args':{'expected_model':'new','steps':1}},
        ],stop_on_error=False)
        receipt = json.loads(rows[0].text)
        history = receipt['results'][0]['result'][0]
        assert history['completed'] == 1 and history['requested'] == 2
        assert current.uncertain == lost_reply
        if lost_reply:
            assert receipt['executed'] == 1 and receipt['stopped_at'] == 0
        else:
            assert history['reason'] == 'HISTORY_PREWRITE_REJECTED' and history['error'] == 'STALE_MODEL'
            assert receipt['executed'] == 2 and receipt['stopped_at'] is None
            assert receipt['results'][1]['result'][0]['completed'] == 1
    asyncio.run(run())


@pytest.mark.parametrize('phase',['initialization','adoption'])
def test_current_retained_replacement_owns_status_after_exit(tmp_path,monkeypatch,phase):
    instances, starts = [], []
    class Replacement(Runtime):
        def __init__(self, lab):
            super().__init__(lab)
            self.pid = 10 + len(instances)
            self.block_close = False
            instances.append(self)
        def start(self):
            starts.append(self.pid)
        async def initialize(self,*args):
            if len(instances) == 2:
                self.block_close = True
                raise RuntimeError('REPLACEMENT_INIT')
        def attach(self,pid):
            self.pid,self.mode = pid,'attached'
        async def adopt(self):
            self.block_close = True
            raise RuntimeError('REPLACEMENT_ADOPT')
        def close(self):
            return {'close_blocked':self.block_close,'reason':'test owner'}
        async def status(self):
            return {'pid':self.pid,'model_ready':True}
        async def session_transition(self,*args):
            self.exit_stopped = True
            return {'stopped':True}
    monkeypatch.setattr(server,'Runtime',Replacement)
    monkeypatch.setattr(bridge,'find_open_vroid',lambda _: [{'pid':91,'path':'E:/external/VRoidStudio.exe'}])
    monkeypatch.setattr(bridge,'validate_assembly',lambda _: None)
    mcp = server.create_server(tmp_path,'F00')
    fn = lambda name: mcp._tool_manager.get_tool(name).fn
    async def run():
        await fn('get_status')()
        await fn('exit_vroid')('m')
        with pytest.raises(RuntimeError, match='REPLACEMENT'):
            if phase == 'initialization':
                await fn('restart_session')(True)
            else:
                await fn('attach_open_vroid')(pid=91)
        retained = instances[-1]
        status = await fn('get_status')()
        assert status['pid'] == retained.pid and status['reason'] == 'SESSION_CLEANUP_PENDING'
        assert status['pending_session'] and status['retained_session']['phase'] == phase and not status.get('stopped')
        before = list(starts)
        with pytest.raises(RuntimeError, match='SESSION_CLEANUP_PENDING'):
            await fn('list_face_params')()
        assert starts == before and len(instances) == 2
        retained.block_close = False
        if phase == 'adoption':
            assert 'restart_session' in (await fn('detach_open_vroid')())['next']
            assert (await fn('get_status')())['stopped'] and starts == before
        assert (await fn('restart_session')(True))['model_ready']
        assert (await fn('get_status')())['model_ready']
    asyncio.run(run())
