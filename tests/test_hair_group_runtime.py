"""Real serialized runtime behavior and public wrapper routing, with native doubles."""
import asyncio
from functools import wraps
import pytest

from vroid_mcp.runtime import Runtime
from vroid_mcp import tools_hair


def async_test(function):
    @wraps(function)
    def run(*args, **kwargs):
        return asyncio.run(function(*args, **kwargs))
    return run


def runtime():
    r = Runtime.__new__(Runtime)
    r.lock = asyncio.Lock()
    r.uncertain = False
    calls = []

    async def settle(frame=-1):
        calls.append(('settle', frame))
        return {'model_token': 'fresh'}

    async def call(name, args):
        assert r.lock.locked()
        calls.append((name, args))
        if name == 'get_hair_group_state':
            return {'model_token': 'fresh', 'group': {'scope': 't/g', 'strands': []}}
        if name == 'list_hair_groups':
            return {'model_token': 'fresh', 'groups': []}
        if name == 'get_procedural_hair_controls':
            return {'model_token': 'fresh', 'controls': [{'key': 'length', 'min': .01, 'max': 2},
                                                        {'key': 'hair_count', 'min': 1, 'max': 100}]}
        return {'model_token': 'fresh', 'ok': True, 'frame': 8,
                'verification_snapshot': {'scope': 't/g', 'strands': []}}

    r._settle = settle
    r._call = call
    return r, calls


@async_test
async def test_group_edit_settles_and_reads_exact_target_under_one_lock():
    r, calls = runtime()
    result = await r.scale_brush_hair('fresh', 'HairFront', 't/g', 2)
    assert result['settled'] is True
    assert [c[0] for c in calls] == ['settle', 'scale_brush_hair', 'settle', 'get_hair_group_state']
    assert 'verification_snapshot' not in result
    assert not r.uncertain


@async_test
async def test_clone_reads_new_scope_without_replaying_clone():
    r, calls = runtime()
    result = await r.clone_brush_hair('fresh', 'HairFront', 't/g', [0, 0, 0])
    assert result['settled']
    assert len([c for c in calls if c[0] == 'clone_brush_hair']) == 1


@pytest.mark.parametrize('factor', [True, '2', 0, -1, 10.1, float('inf'), float('nan')])
@async_test
async def test_invalid_factor_has_no_native_calls(factor):
    r, calls = runtime()
    with pytest.raises(ValueError, match='FACTOR'):
        await r.scale_brush_hair('fresh', 'HairFront', 't/g', factor)
    assert calls == []


@pytest.mark.parametrize('offset', [[True, 0, 0], [1, 2], [1, 2, float('inf')]])
@async_test
async def test_invalid_offset_has_no_native_calls(offset):
    r, calls = runtime()
    with pytest.raises(ValueError, match='OFFSET'):
        await r.clone_brush_hair('fresh', 'HairFront', 't/g', offset)
    assert calls == []


@async_test
async def test_partial_receipt_marks_session_uncertain_without_replay():
    r, calls = runtime()

    async def partial(name, args):
        calls.append((name, args))
        return {'model_token': 'fresh', 'ok': False, 'partial': True, 'uncertain': True,
                'command_count': 2, 'completed_points': [{'strand_id': 's', 'index': 1}]}

    r._call = partial
    result = await r.scale_brush_hair('fresh', 'HairFront', 't/g', 2)
    assert result['command_count'] == 2
    assert r.uncertain
    assert [c[0] for c in calls] == ['settle', 'scale_brush_hair']


@async_test
async def test_settled_readback_mismatch_marks_uncertain():
    r, calls = runtime()
    original = r._call

    async def changed(name, args):
        result = await original(name, args)
        if name == 'get_hair_group_state':
            result['group']['strands'] = ['changed']
        return result

    r._call = changed
    result = await r.scale_brush_hair('fresh', 'HairFront', 't/g', 2)
    assert result['ok'] is False
    assert result['uncertain'] is True
    assert 'READBACK' in result['error']
    assert r.uncertain


@async_test
async def test_transport_failure_reports_unknown_completion_without_zero_count():
    r, calls = runtime()
    async def failed(name, args):
        calls.append((name, args))
        raise TimeoutError('no response')
    r._call = failed
    result = await r.clone_brush_hair('fresh', 'HairFront', 't/g', [1, 2, 3])
    assert result['uncertain'] is True
    assert result['command_count'] is None
    assert result['completed_points'] is None
    assert r.uncertain
    assert [c[0] for c in calls] == ['settle', 'clone_brush_hair']


@async_test
async def test_list_requires_token_and_checks_native_identity():
    r, calls = runtime()
    result = await r.list_hair_groups('fresh')
    assert result['groups'] == []
    with pytest.raises(ValueError):
        await r.list_hair_groups('', None)


def test_public_hair_group_tools_are_registered():
    functions = {}

    def register(**kwargs):
        def add(f):
            functions[f.__name__] = f
            return f
        return add

    tools_hair.register(register, object(), None, {}, {})
    assert {'list_hair_groups', 'scale_brush_hair', 'clone_brush_hair', 'set_procedural_hair'} <= functions.keys()


def test_public_group_tool_validation_rejects_bool_and_string_numbers():
    from mcp.server.fastmcp.utilities.func_metadata import func_metadata
    from pydantic import ValidationError
    functions = {}
    def register(**kwargs):
        def add(f):
            functions[f.__name__] = f
            return f
        return add
    tools_hair.register(register, object(), None, {}, {})
    for operation, field, invalid in [('scale_brush_hair', 'factor', True),
                                      ('scale_brush_hair', 'factor', '2'),
                                      ('clone_brush_hair', 'offset', [True, 0, 0]),
                                      ('set_procedural_hair', 'hair_count', True)]:
        args = {'expected_model': 'fresh', 'category': 'HairFront', 'scope': 't/g', field: invalid}
        with pytest.raises(ValidationError):
            func_metadata(functions[operation]).arg_model.model_validate(args)


@pytest.mark.parametrize('changes', [{}, {'length': True}, {'hair_count': True}, {'hair_count': 0},
                                    {'hair_count': 1.5}, {'length': float('nan')}])
@async_test
async def test_invalid_procedural_arguments_have_no_native_calls(changes):
    r, calls = runtime()
    with pytest.raises(ValueError, match='PROCEDURAL'):
        await r.set_procedural_hair('fresh', 'HairFront', 't/g', **changes)
    assert calls == []


@async_test
async def test_procedural_range_validates_entire_change_set_before_writer():
    r, calls = runtime()
    with pytest.raises(ValueError, match='RANGE'):
        await r.set_procedural_hair('fresh', 'HairFront', 't/g', length=.5, hair_count=101)
    assert [c[0] for c in calls] == ['settle', 'get_procedural_hair_controls']
    assert not r.uncertain


@async_test
async def test_procedural_postsettle_geometry_may_regenerate_but_scalar_must_match():
    r, calls = runtime()
    original = r._call
    async def native(name, args):
        result = await original(name, args)
        if name == 'set_procedural_hair':
            result['verification_snapshot'] = {'scope': 't/g', 'type': 'procedural', 'configured': {'length': .5, 'hair_count': 16}, 'strands': []}
        if name == 'get_hair_group_state':
            result['group'] = {'scope': 't/g', 'type': 'procedural', 'configured': {'length': .5, 'hair_count': 16}, 'strands': ['regenerated']}
        return result
    r._call = native
    result = await r.set_procedural_hair('fresh', 'HairFront', 't/g', length=.5, hair_count=16)
    assert result['ok'] and result['settled']
    assert result['settled_readback']['strands'] == ['regenerated']
