import asyncio
from types import SimpleNamespace

import pytest

from vroid_mcp.runtime import Runtime
from vroid_mcp import edit_sequence


def runtime(responses):
    calls = []
    def native(operation, args):
        calls.append(operation)
        value = responses.get(operation, {})
        if isinstance(value, Exception): raise value
        return value
    r = Runtime.__new__(Runtime)
    r.dead = r.uncertain = False
    r.script = SimpleNamespace(exports_sync=SimpleNamespace(call=native))
    return r, calls


@pytest.mark.parametrize('op,args', [('set_body_params', {}),
                                  ('set_parameters', {'domain': 'body'})])
def test_confirmed_body_write_blocks_editor_before_native_dispatch_but_not_save_or_reads(op, args):
    r, calls = runtime({op: {'ok': True, 'model_token': 'm', 'applied': [
        {'id': 'body/WholeBody/002', 'before': 0, 'after': .2}]}})
    async def exercise():
        await r._call(op, {**args, 'expected_model': 'm'})
        with pytest.raises(RuntimeError, match='TEXTURE_EDITOR_REOPEN_REQUIRED'):
            await r._call('open_texture_editor', {'expected_model': 'm'})
        await r._call('get_height')
        await r._call('save_as', {'expected_model': 'm'})
    asyncio.run(exercise())
    assert calls == [op, 'get_height', 'save_as']
    assert r.uncertain is False


def test_partial_body_batch_also_requires_reopen_and_undo_cannot_clear_cache_guard():
    r, _ = runtime({'set_body_params': {'ok': False, 'model_token': 'm',
                  'applied': [{'before': 0, 'after': .3}], 'error': 'later change failed'}})
    async def exercise():
        await r._call('set_body_params', {'expected_model': 'm'})
        await r._call('undo', {'expected_model': 'm'})
        with pytest.raises(RuntimeError, match='TEXTURE_EDITOR_REOPEN_REQUIRED'):
            await r._call('open_texture_editor', {'expected_model': 'm'})
    asyncio.run(exercise())


@pytest.mark.parametrize('operation,args,result', [
    ('set_body_params', {}, {'model_token': 'm', 'applied': [{'before': .2, 'after': .2}]}),
    ('set_body_params', {}, {'ok': False, 'model_token': 'm', 'applied': []}),
    ('set_face_params', {}, {'model_token': 'm', 'applied': [{'before': 0, 'after': .2}]}),
    ('set_parameters', {'domain': 'colors'}, {'model_token': 'm', 'applied': [{'before': 0, 'after': 1}]}),
])
def test_noop_rejected_and_other_domain_edits_keep_editor_available(operation, args, result):
    r, calls = runtime({operation: result})
    async def exercise():
        await r._call(operation, {'expected_model': 'm', **args})
        await r._call('open_texture_editor', {'expected_model': 'm'})
    asyncio.run(exercise())
    assert calls[-1] == 'open_texture_editor'


def test_new_runtime_has_no_guard_and_other_model_tokens_do_not_inherit_it():
    r, calls = runtime({})
    r.body_edited_tokens = {'old-model'}
    asyncio.run(r._call('open_texture_editor', {'expected_model': 'new-model'}))
    fresh, _ = runtime({})
    asyncio.run(fresh._call('open_texture_editor', {'expected_model': 'old-model'}))
    assert not edit_sequence.status(fresh, 'old-model')['requires_cold_reopen']
    assert edit_sequence.status(r, 'old-model')['requires_cold_reopen']


def test_height_solver_uses_same_guarded_bridge():
    # set_height writes through _call('set_body_params'); exercise the public
    # solver itself to catch a future bypass via a different dispatch route.
    r, calls = runtime({})
    r.lock = asyncio.Lock()
    async def settle(*a): return {}
    r._settle = settle
    def native(operation, args):
        calls.append(operation)
        if operation == 'list_body_params':
            return {'parameters': [{'id': 'body/WholeBody/002', 'value': 0, 'min': -1, 'max': 1}]}
        if operation == 'get_height':
            return {'centimeters': 160,  # Stale UI already claims the target.
                    'live_centimeters': 160 if 'set_body_params' in calls else 150}
        if operation == 'set_body_params':
            return {'ok': True, 'model_token': 'm', 'frame': 1,
                    'applied': [{'before': 0, 'after': .05}]}
        return {}
    r.script.exports_sync.call = native
    async def exercise():
        result = await r.set_height('m', 160)
        assert result['settled']
        with pytest.raises(RuntimeError, match='TEXTURE_EDITOR_REOPEN_REQUIRED'):
            await r._call('open_texture_editor', {'expected_model': 'm'})
    asyncio.run(exercise())
