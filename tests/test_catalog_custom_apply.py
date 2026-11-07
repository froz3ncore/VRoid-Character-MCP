"""A real catalog key reaches only its independently registered current file."""
import asyncio
import hashlib
import os
import shutil

import pytest
from test_custom_item_generation import archive
from test_preset_catalog import row as builtin
from vroid_mcp import server, runtime_groups
from vroid_mcp.preset_catalog import PresetCatalog
from vroid_mcp.runtime import Runtime


def setup(tmp_path, monkeypatch, mode, change=None):
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
