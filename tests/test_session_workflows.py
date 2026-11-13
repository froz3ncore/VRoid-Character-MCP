import asyncio
import json

import pytest

from vroid_mcp import server


def test_return_menu_initial_agreements_is_completed_without_selection_token(tmp_path):
    from vroid_mcp.runtime import Runtime
    runtime=Runtime(tmp_path)
    observed=dict(active_screen='VRoid.Studio.StartScreen.ViewModel',model_open=False,
                  model_ready=False,menu_token=None,menu_ready=False,start_screen_mode='InitialAgreements')
    async def call(op):
        assert op=='status'
        return observed
    runtime._call=call
    assert asyncio.run(runtime._await_session('return_to_main_menu',{},{}))==observed
    assert not runtime.uncertain


def test_batch_uses_registered_handler_validation_and_offline_receipts(tmp_path):
    async def run():
        mcp = server.create_server(tmp_path, 'F00')
        batch = mcp._tool_manager.get_tool('run_batch')
        assert batch is not None
        seen = []

        @mcp.tool()
        def probe(value: int) -> dict:
            seen.append(value)
            return {'ok': value > 0}

        def operation(value):
            return {'tool': 'probe', 'args': {'value': value}}

        rows = await batch.fn([operation('4'), operation(0), operation(1)], stop_on_error=False)
        receipt = json.loads(rows[0].text)
        assert seen == [4, 0, 1]
        assert (receipt['executed'], receipt['failed'], receipt['stopped_at']) == (3, 1, None)
        for invalid in [{'tool': 'unknown', 'args': {}}, {'tool': 'run_batch', 'args': {}},
                        {'tool': 'probe', 'args': []}, {'tool': 'new_character', 'args': {}},
                        {'tool': 'probe', 'args': {'unexpected': 1}}]:
            with pytest.raises(ValueError):
                await batch.fn([operation(9), invalid])
        assert seen == [4, 0, 1]
        for size in [0, 201]:
            with pytest.raises(ValueError):
                await batch.fn([operation(1)] * size)
        receipt = json.loads((await batch.fn([operation(1)] * 200))[0].text)
        assert receipt['executed'] == 200
    asyncio.run(run())


@pytest.mark.parametrize('variant', ['F00','M00'])
def test_menu_create_reads_settled_native_variant_and_owner(tmp_path, monkeypatch, variant):
    from vroid_mcp.runtime import Runtime
    from vroid_mcp import runtime_session
    current = Runtime(tmp_path)
    current.mode, current.pid = 'attached', 7
    calls = []
    observed = dict(model_token='fresh:9', model_variant=variant, edit_root_active=True, model_ready=True)
    async def call(op,args=None):
        calls.append(op)
        if op == 'attached_edit_begin':
            return {'id':'test'}
        if op == 'attached_edit_finish':
            return {'needs_review':False}
        if op == 'status':
            return observed
        return {}
    async def settle():
        return observed
    current._call, current._settle = call, settle
    monkeypatch.setattr(runtime_session,'verified_window',lambda _: '0x1')
    args = dict(expected_menu='fresh:menu:5', variant=variant)
    with pytest.raises(ValueError, match='CONFIRM_ATTACHED'):
        asyncio.run(current.session_transition('create_from_menu',args))
    assert calls == []
    args['confirm_attached'] = True
    assert asyncio.run(current.session_transition('create_from_menu',args)) == observed
    assert calls == ['get_session_preflight','attached_edit_begin','create_from_menu','status','attached_edit_finish']
    observed['model_variant'] = None
    with pytest.raises(RuntimeError, match='TEMPLATE_UNCONFIRMED'):
        asyncio.run(current.session_transition('create_from_menu',args))
    assert current.uncertain and calls[-1] == 'status'


def test_menu_open_validates_archive_and_reads_association(tmp_path,monkeypatch):
    import zipfile
    from vroid_mcp.runtime import Runtime
    from vroid_mcp import runtime_session
    current = Runtime(tmp_path)
    current.owns_process, current.pid = True, 7
    folder = tmp_path/'saves'
    folder.mkdir()
    path = folder/'character.vroid'
    calls = []
    state = dict(model_token='new', model_ready=True, edit_root_active=True, file_path=str(path))
    async def call(op,args=None):
        calls.append(op)
        return state if op == 'status' else {'task_id':'non-generic-task'}
    async def task(receipt):
        assert receipt == {'task_id':'non-generic-task'}
        calls.append('completed_non_generic_task')
    async def settle():
        return state
    current._call, current._task, current._settle = call, task, settle
    monkeypatch.setattr(runtime_session,'verified_window',lambda _: '0x1')
    def open_file(filename):
        return asyncio.run(current.session_transition('open_from_menu',dict(expected_menu='menu',filename=filename)))
    with pytest.raises(ValueError):
        open_file(str(path))
    path.write_bytes(b'invalid')
    with pytest.raises(zipfile.BadZipFile):
        open_file(path.name)
    assert calls == []
    with zipfile.ZipFile(path,'w') as archive:
        archive.writestr('model','fixture')
    assert open_file(path.name)['file_path'] == str(path)
    assert calls == ['get_session_preflight','open_from_menu','completed_non_generic_task','status']


def test_offline_help_matches_current_schema_and_chinese(tmp_path):
    async def run():
        mcp = server.create_server(tmp_path, 'F00')
        tool = mcp._tool_manager.get_tool('get_help')
        assert tool is not None
        assert (await tool.fn('run_batch', 'zh'))['inputSchema'] == mcp._tool_manager.get_tool('run_batch').parameters
        assert '模型' in str(await tool.fn('session', 'zh'))
        assert (await tool.fn('overview', 'es'))['language'] == 'en'
        assert await mcp.list_resources()
    asyncio.run(run())


def test_graceful_exit_latch_blocks_copy_kill():
    from types import SimpleNamespace
    from vroid_mcp import bridge
    kills = []
    subject = SimpleNamespace(mode='copy', owns_process=True, pid=42, dead=False, file_lock=None,
                              device=SimpleNamespace(kill=kills.append),
                              exit_watch=SimpleNamespace(exited=lambda: False))
    outcome = bridge.close(subject)
    assert kills == []
    assert outcome['close_blocked']


def test_menu_workflows_require_observed_session(tmp_path):
    async def run():
        mcp = server.create_server(tmp_path, 'F00')
        for name, args in [('return_to_main_menu', {'expected_model':'old'}),
                           ('exit_vroid', {'expected_model':'old'}),
                           ('create_from_menu', {'expected_menu':'stale', 'variant':'M00'}),
                           ('open_from_menu', {'expected_menu':'stale', 'filename':'missing.vroid'})]:
            tool = mcp._tool_manager.get_tool(name)
            assert tool is not None
            with pytest.raises(RuntimeError, match='SESSION'):
                await tool.fn(**args)
    asyncio.run(run())


def test_history_exhaustion_returns_only_completed_prefix(tmp_path):
    from vroid_mcp.runtime import Runtime
    runtime = Runtime(tmp_path)
    calls = []
    async def call(op, args):
        calls.append(op)
        if len(calls) == 1:
            return {'frame': 4, 'task_id': 1}
        return {'dispatched': False, 'available': False}
    async def wait(*args):
        return {}
    runtime._call, runtime._task, runtime._settle = call, wait, wait
    result = asyncio.run(runtime.history('undo', 'm', 3))
    assert result['completed'] == 1 and result['requested'] == 3
    assert calls == ['undo', 'undo']


def test_gate_serializes_clients_and_refuses_inherited_task():
    from vroid_mcp.batch import SessionGate
    async def run():
        gate = SessionGate()
        start = asyncio.Event()
        order = []
        async def client():
            await start.wait()
            async with gate.hold():
                order.append('client')
        async def child():
            async with gate.hold():
                pytest.fail('child acquired parent gate')
        competitor = asyncio.create_task(client())
        async with gate.hold():
            start.set()
            async with gate.hold():
                with pytest.raises(RuntimeError, match='CHILD_TASK'):
                    await asyncio.create_task(child())
            order.append('owner')
        await competitor
        assert order == ['owner', 'client']
    asyncio.run(run())


def test_batch_calls_ready_tool_under_attached_receipt_and_stops_on_uncertainty(tmp_path, monkeypatch):
    from types import SimpleNamespace
    current = SimpleNamespace(mode='attached', dead=False, uncertain=False)
    events = []
    current.start = lambda: None
    async def initialize(*args):
        pass
    async def call(op, args):
        events.append(op)
        return {'id': 'receipt'} if op == 'attached_edit_begin' else {'needs_review':current.uncertain}
    async def save_as(filename, expected):
        events.append((filename, expected))
        if expected != 'actual':
            current.uncertain = True
            raise RuntimeError('uncertain')
        return {'saved':True}
    current.initialize, current._call, current.save_as = initialize, call, save_as
    monkeypatch.setattr(server, 'Runtime', lambda lab: current)
    async def run():
        mcp = server.create_server(tmp_path,'F00')
        ops = [{'tool':'save_as', 'args':{'filename':'r.vroid','expected_model':m}} for m in ('actual','stale','actual')]
        receipt = json.loads((await mcp._tool_manager.get_tool('run_batch').fn(ops, False))[0].text)
        assert (receipt['executed'],receipt['failed'],receipt['stopped_at']) == (2,1,1)
        assert events == ['attached_edit_begin',('r.vroid','actual'),'attached_edit_finish',
                          'attached_edit_begin',('r.vroid','stale'),'attached_edit_finish']
    asyncio.run(run())


def test_batch_image_limits_and_sdk_validation(tmp_path, monkeypatch):
    from mcp.types import TextContent, ImageContent
    from vroid_mcp import batch
    import base64
    async def run():
        mcp = server.create_server(tmp_path,'F00')
        data = base64.b64encode(b'testing').decode()
        @mcp.tool()
        def legacy() -> list[TextContent | ImageContent]:
            return [TextContent(type='text',text='metadata'), ImageContent(type='image',data=data,mimeType='image/png')]
        tool = mcp._tool_manager.get_tool('run_batch')
        ops = [{'tool':'legacy','args':{}}] * 9
        for include, count in [(True,8),(False,0)]:
            blocks = await tool.fn(ops, include_images=include)
            assert len(blocks) == 1 + count and data not in blocks[0].text
            assert all(block.data == data for block in blocks[1:])
        monkeypatch.setattr(batch,'BYTE_LIMIT',13)
        assert len(await tool.fn(ops)) == 2
        bad = {'tool':'set_preset_framing','args':{'category':'Clothing/Tops','yaw':'wrong'}}
        receipt = json.loads((await tool.fn([bad,ops[0]], stop_on_error=True))[0].text)
        assert (receipt['executed'],receipt['failed'],receipt['stopped_at']) == (1,1,0)
    asyncio.run(run())


@pytest.mark.parametrize('allow_exit', [True, False])
def test_pending_or_complete_quit_never_kills_or_autostarts(tmp_path, monkeypatch, allow_exit):
    from vroid_mcp import runtime_session
    from vroid_mcp.runtime import Runtime
    from types import SimpleNamespace
    events = []
    current = Runtime(tmp_path)
    current.pid, current.owns_process = 42, True
    current.device = SimpleNamespace(kill=lambda pid: events.append('kill'))
    current.start = lambda: events.append('start')
    async def initialize(*args):
        pass
    async def call(op, args=None):
        events.append(op)
        return {}
    async def status():
        return {'model_token':'m'}
    current._call, current.initialize, current.status = call, initialize, status
    quit_observed = lambda: allow_exit and 'exit_vroid' in events
    watch = SimpleNamespace(exited=quit_observed, close=lambda: events.append('handle closed'))
    monkeypatch.setattr(runtime_session,'verified_window',lambda _: '0x1')
    monkeypatch.setattr(runtime_session,'ExitWatch',lambda _: watch)
    monkeypatch.setattr(runtime_session,'DEADLINE',0)
    monkeypatch.setattr(server,'Runtime',lambda _:current)
    async def run():
        mcp = server.create_server(tmp_path,'F00')
        invoke = lambda name: mcp._tool_manager.get_tool(name).fn
        async def exercise():
            async with mcp._mcp_server.lifespan(mcp._mcp_server):
                await invoke('get_status')()
                if allow_exit:
                    assert (await invoke('exit_vroid')('m'))['stopped']
                else:
                    with pytest.raises(TimeoutError, match='GRACEFUL_EXIT_PENDING'):
                        await invoke('exit_vroid')('m')
                    assert (await invoke('restart_session')(True))['close_blocked']
                result = await invoke('get_status')()
                assert result['stopped'] == allow_exit and result['can_undo'] is None
                with pytest.raises(RuntimeError, match='STOPPED|PENDING'):
                    await invoke('list_face_params')()
        if allow_exit:
            await exercise()
        else:
            with pytest.raises(RuntimeError, match='NATIVE_WORK_PENDING'):
                await exercise()
        assert events.count('start') == 1 and 'kill' not in events
    asyncio.run(run())


def test_exit_waits_after_rpc_disconnection_without_attached_finish(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from vroid_mcp import runtime_session
    from vroid_mcp.runtime import Runtime
    current = Runtime(tmp_path)
    current.mode, current.pid = 'attached', 91
    events = []
    waits = iter([False, False, True, True])
    def exited():
        answer = next(waits)
        events.append(('signaled',answer))
        return answer
    watch = SimpleNamespace(exited=exited,close=lambda: events.append('handle closed'))
    async def call(op,args=None):
        events.append(op)
        if op == 'attached_edit_begin':
            return {'id':'receipt'}
        if op == 'exit_vroid':
            assert args['receipt_id'] == 'receipt'
            current.dead = True
            raise RuntimeError('RPC disconnected before delivery')
        return {}
    current._call = call
    monkeypatch.setattr(runtime_session,'verified_window',lambda _: '0x1')
    monkeypatch.setattr(runtime_session,'ExitWatch',lambda _: watch)
    result = asyncio.run(current.session_transition('exit_vroid',dict(expected_model='m',close_attached=True)))
    assert result['stopped'] and events[-1] == 'handle closed'
    assert 'attached_edit_finish' not in events and current.exit_stopped
