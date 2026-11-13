"""Exercise the registered teardown transaction without attaching to a real editor."""
import asyncio
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from vroid_mcp import bridge, server
from vroid_mcp.runtime import Runtime


@pytest.mark.parametrize('action', ['detach', 'restart', 'switch', 'adoption', 'nested_attach'])
@pytest.mark.parametrize('blocked', [False, True])
def test_cancelled_teardown_finishes_under_gate(tmp_path, monkeypatch, action, blocked):
    entered, resume = threading.Event(), threading.Event()
    events, instances = [], []
    def release():
        events.append('release')
        entered.set()
        assert resume.wait(5)
        return {'released':not blocked, 'pending_work':['native task'] if blocked else []}

    # This disposable process stands in for a user's open window. The real
    # bridge close is used; its fake device cannot terminate any process.
    user = subprocess.Popen([sys.executable,'-B','-c','import sys; sys.stdin.buffer.read(1)'],
                            stdin=subprocess.PIPE)
    class Model(Runtime):
        def __init__(self, lab):
            super().__init__(lab)
            instances.append(self)
        def start(self): events.append('copy_started')
        async def initialize(self, *args): pass
        async def status(self): return dict(mode=self.mode, pid=self.pid, dead=self.dead)
        def attach(self, pid):
            events.append(('attach',pid))
            self.mode,self.pid='attached',pid
            self.script=SimpleNamespace(exports_sync=SimpleNamespace(release=release),
                                        unload=lambda:events.append('unload'))
            self.session=SimpleNamespace(detach=lambda:events.append('detach'))
            if action=='nested_attach':
                # Same inner bridge.close -> outer server cleanup as bridge.attach.
                bridge.close(self)
                raise ValueError('acquisition failed')
        async def adopt(self):
            if action=='adoption': raise ValueError('adoption failed')
            return {}
    monkeypatch.setattr(server,'Runtime',Model)
    monkeypatch.setattr(bridge,'find_open_vroid',lambda _: [
        {'pid':pid,'path':'E:/external/VRoidStudio.exe'} for pid in (user.pid,user.pid+1)])
    monkeypatch.setattr(bridge,'validate_assembly',lambda _:None)
    monkeypatch.setattr(bridge,'record',lambda *args:None)
    mcp=server.create_server(tmp_path,'F00')
    async def call(name, **args):
        return await mcp._tool_manager.get_tool(name).fn(**args)
    async def scenario():
        nonlocal blocked
        if action in ('adoption','nested_attach'):
            operation=call('attach_open_vroid',pid=user.pid)
        else:
            await call('attach_open_vroid',pid=user.pid)
            if action=='switch': operation=call('attach_open_vroid',pid=user.pid+1)
            else: operation=call('detach_open_vroid' if action=='detach' else 'restart_session')
        waiter=asyncio.create_task(operation)
        assert await asyncio.to_thread(entered.wait,3)
        owner=instances[-1]
        waiter.cancel()
        follower=asyncio.create_task(call('get_status'))
        try:
            await asyncio.sleep(.025)
            waiter.cancel()
            await asyncio.sleep(.025)
            assert not follower.done() and instances[-1] is owner
        finally:
            resume.set()
        with pytest.raises((asyncio.CancelledError,ValueError)) as raised: await waiter
        if action=='adoption': assert str(raised.value)=='adoption failed'
        status=await follower
        if blocked:
            assert instances[-1] is owner and 'unload' not in events and 'detach' not in events
            if action in ('adoption','nested_attach'): assert status['pending_session']
            blocked=False
            assert (await call('detach_open_vroid'))['detached']
        else:
            assert status['mode']=='copy' and instances[-1] is not owner
            assert events.count('release')==1
        before=list(events)
        assert owner.close()['detached'] and owner.close()['detached']
        assert not (await call('detach_open_vroid'))['detached']
        assert events==before and events.count('detach')==events.count('unload')==1
        assert events.count(('attach',user.pid+1))==0 and user.poll() is None
    try:
        asyncio.run(scenario())
    finally:
        resume.set()
        user.stdin.close()
        user.wait(5)
