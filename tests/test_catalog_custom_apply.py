"""A real catalog key reaches only its independently registered current file."""
import asyncio
import hashlib
import os
import shutil
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest
from test_custom_item_generation import archive
from test_preset_catalog import row as builtin
from vroid_mcp import server, runtime_groups
from vroid_mcp.preset_catalog import PresetCatalog
from vroid_mcp.runtime import Runtime


def setup(tmp_path, monkeypatch, mode, change=None, dispatch_hook=None):
    runtime = Runtime(tmp_path)
    runtime.mode = mode
    root = tmp_path / ('external' if mode == 'attached' or change == 'escaped' else 'profile')
    root.mkdir()
    path = root / 'sample.vroidcustomitem'
    archive(path, 'A', 2)
    if change == 'hardlink':
        os.link(path, tmp_path / 'alias')
    registered = dict(id='A', group_type='Tops', path=str(path), resource_name='group/A', revision='v1',
                      registered=True, custom_resource_name='user/A', custom_revision='c1')
    row = dict(registered, kind='custom', category='Custom/Tops', resource='user/A', selectable=True,
               owned=True, usable=True, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    if change == 'unregistered-path': row['path'] = str(tmp_path / 'untrusted.vroidcustomitem')
    if change == 'unusable': row['usable'] = False
    if change == 'metadata':
        archive(path, 'B', 2)
        row['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    if change == 'bytes': archive(path, 'A', 3)
    store = PresetCatalog(tmp_path / 'preset_cache')
    source = {'session':'old' if change == 'session' else 'live', 'build':'a'*64}
    complete = {'builtin':True, 'custom':True}
    store.sync([builtin()] if change == 'builtin' else [row], source, complete)
    key = store.search(include_locked=True)[0]['key']
    if change in ('removed', 'unknown'):
        store.sync([], source, dict(complete, custom=change == 'removed'))
    calls = []
    async def native(op, args):
        calls.append(op)
        if op == 'attached_edit_begin': return {'id':'edit'}
        if op == 'attached_edit_finish': return {'needs_review':False}
        if op == 'custom_item_state':
            files = [dict(registered, revision='other')] if change == 'revision' else [registered]
            if change == 'ambiguous': files *= 2
            return dict(files=files, base_path=str(root), model_token='live', build=('b' if change == 'build' else 'a')*64)
        if op == 'custom_item_validate_begin':
            assert args['registered_item'] == registered
            if change == 'rescan': store.sync([], source, complete)
            return dict(completed=True, compatible=True, model_token='live', request_id='job')
        if op == 'apply_registered_custom_item':
            assert args['registered_item'] == registered
            if dispatch_hook:
                await dispatch_hook(store)
            return {'frame':12}
        if op == 'list_groups':
            return dict(model_token='live', groups=[dict(registered, active=True, type='Tops')])
        if op == 'custom_item_application_state': return dict(model_token='live', completed=True)
        if op == 'custom_item_validate_release': return {'released':True}
        raise AssertionError(op)
    async def settled(*args): return {'model_token':'live'}
    runtime._call = native
    runtime._settle = runtime.initialize = settled
    runtime.start = lambda:None
    monkeypatch.setattr(server, 'Runtime', lambda lab:runtime)
    manager = server.create_server(tmp_path, 'F00')._tool_manager
    assert 'filename' in manager.get_tool('apply_custom_item').parameters['required']
    return manager, key, calls


@pytest.mark.parametrize('mode',['copy','attached'])
@pytest.mark.parametrize('source_session',[None,'session'])
def test_apply_custom_item_by_key(mode, source_session, tmp_path, monkeypatch):
    manager, key, calls = setup(tmp_path, monkeypatch, mode, source_session)
    assert key.startswith('custom:user/A#')
    result = asyncio.run(manager.call_tool('apply_custom_item_by_key', {'expected_model':'live','key':key}))
    assert result['applied'] and result['key'] == key and result['readback']['id'] == 'A'
    assert calls.count('apply_registered_custom_item') == 1
    assert ('attached_edit_finish' in calls) == (mode == 'attached')


@pytest.mark.parametrize('change', ['unregistered-path','unusable','wrong-target','build','ambiguous','removed','unknown',
                                    'builtin','revision','hardlink','escaped','metadata','bytes','rescan'])
def test_custom_key_rejects_stale_or_unauthorized_selection(change, tmp_path, monkeypatch):
    manager, key, calls = setup(tmp_path, monkeypatch, 'copy' if change == 'escaped' else 'attached', change)
    reads = []
    inspect = runtime_groups.inspect_custom_item
    def observed(path, **kwargs):
        reads.append(path)
        return inspect(path, **kwargs)
    monkeypatch.setattr(runtime_groups, 'inspect_custom_item', observed)
    tool = manager.get_tool('apply_custom_item_by_key')
    assert tool is not None
    with pytest.raises(ValueError):
        asyncio.run(tool.fn(expected_model='obsolete' if change == 'wrong-target' else 'live',key=key))
    assert 'apply_registered_custom_item' not in calls
    if change not in ('metadata','bytes','rescan'):
        assert not reads


def test_registered_generation_cannot_be_replaced_by_identical_link_before_pin(tmp_path,monkeypatch):
    from vroid_mcp import custom_item_file
    manager,key,calls=setup(tmp_path,monkeypatch,'attached')
    pin=runtime_groups.pinned_application
    def interleave(runtime,path):
        foreign=tmp_path/'other.vroidcustomitem'
        shutil.copyfile(path,foreign)
        path.unlink()
        os.link(foreign,path)
        return pin(runtime,path)
    monkeypatch.setattr(runtime_groups,'pinned_application',interleave)
    def no_archive(*args):raise AssertionError('redirected generation reached archive decoding')
    monkeypatch.setattr(custom_item_file,'_inspect_archive',no_archive)
    with pytest.raises(ValueError,match='ALIAS|GENERATION'):
        asyncio.run(manager.get_tool('apply_custom_item_by_key').fn(expected_model='live',key=key))
    assert 'custom_item_validate_begin' not in calls


def test_key_selection_excludes_catalog_retirement_during_native_dispatch(tmp_path,monkeypatch):
    # A separate process attempts the actual store transaction while the
    # simulated native selector still has control. The event loop stays free.
    writer = """from pathlib import Path
import sys
from vroid_mcp.preset_catalog import PresetCatalog
s=PresetCatalog(Path(sys.argv[1]),lock_timeout=.15)
try:
    s.sync([],{'session':'other','build':'a'*64},{'custom':True,'builtin':True})
except TimeoutError as exc:
    if 'CATALOG_LOCK_TIMEOUT' not in str(exc): raise
    print('contended')
else:
    print('retired')
"""
    async def race(store):
        result=await asyncio.to_thread(subprocess.run,[sys.executable,'-B','-c',writer,str(store.root)],
                                       capture_output=True,text=True,check=True,timeout=10)
        assert result.stdout.strip()=='contended'
    manager,key,calls=setup(tmp_path,monkeypatch,'copy',dispatch_hook=race)
    assert asyncio.run(manager.get_tool('apply_custom_item_by_key').fn(expected_model='live',key=key))['applied']
    store=PresetCatalog(tmp_path/'preset_cache')
    store.sync([],{'session':'other','build':'a'*64},{'custom':True,'builtin':True})
    assert store.get(key)['removed'] and calls.count('apply_registered_custom_item')==1


@pytest.mark.parametrize('cancel',[False, True])
def test_catalog_dispatch_wait_yields_event_loop_and_is_cancellable(tmp_path,monkeypatch,cancel):
    manager,key,calls=setup(tmp_path,monkeypatch,'copy')
    store=PresetCatalog(tmp_path/'preset_cache')
    async def run():
        with store.locked():
            job=asyncio.create_task(manager.get_tool('apply_custom_item_by_key').fn(expected_model='live',key=key))
            for _ in range(100):
                if 'custom_item_validate_begin' in calls:break
                await asyncio.sleep(.01)
            assert 'custom_item_validate_begin' in calls
            await asyncio.sleep(.05)
            assert not job.done() and 'apply_registered_custom_item' not in calls
            if cancel:
                job.cancel()
                with pytest.raises(asyncio.CancelledError):await job
                assert 'custom_item_validate_release' in calls
        if not cancel:assert (await asyncio.wait_for(job,2))['applied']
    asyncio.run(run())
    with store.locked():pass


@pytest.mark.parametrize('interruption',['cancel','timeout'])
def test_catalog_lease_survives_interrupted_real_bridge_export(tmp_path,monkeypatch,interruption):
    from vroid_mcp import bridge
    manager,key,calls=setup(tmp_path,monkeypatch,'copy')
    rt=server.Runtime(tmp_path)
    original=rt._call
    store=PresetCatalog(tmp_path/'preset_cache',lock_timeout=.12)
    source=store.get(key)['source']
    entered,resume,finished=(threading.Event() for _ in range(3))
    removed_at_selection=[]
    def export(operation,payload):
        try:
            assert operation=='apply_registered_custom_item'
            entered.set()
            if not resume.wait(8):raise AssertionError('selector timed out')
            removed_at_selection.append(store.get(key)['removed'])
            return {'frame':3}
        finally:finished.set()
    async def native(operation,payload):
        if operation=='apply_registered_custom_item':
            return await bridge.call(rt,operation,payload)
        return await original(operation,payload)
    rt._call=native
    rt.script=SimpleNamespace(exports_sync=SimpleNamespace(call=export))
    if interruption=='timeout':
        monkeypatch.setitem(bridge.SLOW_OPERATIONS,'apply_registered_custom_item',.2)
    def retire():
        store.sync([],source,{'builtin':True,'custom':True})
    async def run():
        job=asyncio.create_task(manager.get_tool('apply_custom_item_by_key').fn(expected_model='live',key=key))
        try:
            assert await asyncio.to_thread(entered.wait,4)
            if interruption=='cancel':
                job.cancel()
                with pytest.raises(asyncio.CancelledError):await job
            else:
                with pytest.raises(RuntimeError,match='Native call timed out'):await job
            assert rt.uncertain and rt._pending_custom_item_pins
            with pytest.raises(TimeoutError,match='CATALOG_LOCK_TIMEOUT'):
                await asyncio.to_thread(retire)
        finally:
            resume.set()
            assert await asyncio.to_thread(finished.wait,4)
        await asyncio.to_thread(retire)
        assert store.get(key)['removed'] and removed_at_selection==[False]
    try:asyncio.run(run())
    finally:
        for pin in getattr(rt,'_pending_custom_item_pins',[]):pin.__exit__(None,None,None)


def test_deferred_selection_cannot_start_after_waiter_releases_unclaimed_lease(tmp_path,monkeypatch):
    from vroid_mcp import bridge
    manager,key,calls=setup(tmp_path,monkeypatch,'copy')
    rt=server.Runtime(tmp_path)
    original=rt._call
    to_thread=asyncio.to_thread
    submitted=asyncio.Event()
    queued=[]
    selected=[]
    async def defer(function,*args,**kwargs):
        if args and args[0]=='apply_registered_custom_item':
            # The host has submitted the closure, but the worker has yet to claim it.
            queued.append((function,args))
            submitted.set()
            await asyncio.Future()
        return await to_thread(function,*args,**kwargs)
    async def native(op,args):
        if op=='apply_registered_custom_item':return await bridge.call(rt,op,args)
        return await original(op,args)
    rt._call=native
    rt.script=SimpleNamespace(exports_sync=SimpleNamespace(call=lambda op,args:selected.append(op)))
    monkeypatch.setattr(bridge.asyncio,'to_thread',defer)
    store=PresetCatalog(tmp_path/'preset_cache',lock_timeout=.12)
    async def run():
        job=asyncio.create_task(manager.get_tool('apply_custom_item_by_key').fn(expected_model='live',key=key))
        await asyncio.wait_for(submitted.wait(),4)
        job.cancel()
        with pytest.raises(asyncio.CancelledError):await job
        store.sync([],store.get(key)['source'],{'builtin':True,'custom':True})
        function,args=queued[0]
        with pytest.raises(RuntimeError,match='DISPATCH_EXPIRED'):
            await to_thread(function,*args)
        assert store.get(key)['removed'] and not selected
    try:asyncio.run(run())
    finally:
        for pin in getattr(rt,'_pending_custom_item_pins',[]):pin.__exit__(None,None,None)
