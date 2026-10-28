import asyncio
import copy
import json

import pytest

from vroid_mcp.texture_layer_management import register_layer_management_tools
from vroid_mcp.texture_layer_state import describe_layers, metadata, stack_digest


class Native:
    def __init__(self):
        self.layers = [{'layer_id': str(i), 'image': {'transferable_id': 't', 'image_id': 'i'},
                        'Name': 'Layer '+str(i), 'Opacity': 1., 'Visibility': True,
                        'CompositionMode': 'CompositionNormal'} for i in range(3)]
        self.writes = []
        self.uncertain = False
        self.fail = None

    def snapshot(self):
        return describe_layers({'layers': copy.deepcopy(self.layers),
            'composition_modes': [{'id': 'CompositionNormal'}, {'id': 'CompositionMultiply'}]})

    async def parameter_call(self, op, args, mutating=False):
        if op == 'list_texture_layers':
            return self.snapshot()
        assert mutating
        self.writes.append((op, args))
        if self.fail:
            raise RuntimeError(self.fail)
        row = next((r for r in self.layers if r['layer_id'] == args.get('layer_id')), None)
        if op == 'rename_texture_layer':
            assert args['expected_layer'] == metadata(row)
            row['Name'] = args['name']
        elif op == 'set_texture_layer_blend':
            row['CompositionMode'] = args['composition_mode']
        elif op == 'delete_texture_layer':
            assert args['expected_stack'] == [metadata(r) for r in self.layers]
            self.layers.remove(row)
        elif op == 'reorder_texture_layers':
            assert args['expected_stack'] == [metadata(r) for r in self.layers]
            self.layers = [next(r for r in self.layers if r['layer_id'] == i) for i in args['layer_ids']]
        return {'layers': copy.deepcopy(self.layers), 'layer': copy.deepcopy(row),
                'saved': False, 'history_command_count': 1} if row else {
                    'layers': copy.deepcopy(self.layers), 'saved': False, 'history_command_count': 1}


def setup():
    native, tools = Native(), {}
    def ready(**kwargs):
        def register(fn):
            tools[fn.__name__] = fn
            return fn
        return register
    register_layer_management_tools(ready, native, None, None)
    return native, tools


def test_stack_hash_tracks_order_and_all_layer_metadata_but_not_response_annotations():
    n, _ = setup()
    original = stack_digest(n.layers)
    assert stack_digest(n.snapshot()['layers']) == original
    assert stack_digest(list(reversed(n.layers))) != original
    n.layers[1]['Opacity'] = .3
    assert stack_digest(n.layers) != original


@pytest.mark.parametrize('name', ['', ' ', 'bad\x00name', 'bad\nname', 'bad\x7fname'])
def test_invalid_names_never_dispatch(name):
    n, tools = setup()
    with pytest.raises(ValueError):
        asyncio.run(tools['rename_texture_layer']('m', 'r', '0', 'a'*64, name))
    assert not n.writes


@pytest.mark.parametrize('tool,extra', [('rename_texture_layer', {'name': 'New'}),
    ('delete_texture_layer', {'expected_stack_sha256': 'b'*64}),
    ('set_texture_layer_blend', {'composition_mode': 'CompositionMultiply'})])
def test_stale_layer_refuses_before_native_write(tool, extra):
    n, tools = setup()
    old = n.snapshot()['layers'][0]['state_sha256']
    n.layers[0]['Name'] = 'Manual edit'
    with pytest.raises(ValueError, match='metadata'):
        asyncio.run(tools[tool]('m', 'r', '0', old, **extra))
    assert not n.writes


@pytest.mark.parametrize('ids', [['0', '1'], ['0', '0', '2'], ['0', '1', 'foreign']])
def test_reorder_requires_complete_unique_per_image_permutation(ids):
    n, tools = setup()
    image = n.snapshot()['images'][0]
    with pytest.raises(ValueError, match='permutation'):
        asyncio.run(tools['reorder_texture_layers']('m', 'r', image['image_id'], image['stack_sha256'], ids))
    assert not n.writes


def test_delete_rejects_stale_stack_and_last_layer():
    n, tools = setup()
    snap = n.snapshot()
    with pytest.raises(ValueError, match='stack'):
        asyncio.run(tools['delete_texture_layer']('m', 'r', '0', snap['layers'][0]['state_sha256'], 'a'*64))
    n.layers = n.layers[:1]
    snap = n.snapshot()
    with pytest.raises(ValueError, match='last raster'):
        asyncio.run(tools['delete_texture_layer']('m', 'r', '0', snap['layers'][0]['state_sha256'], snap['images'][0]['stack_sha256']))
    assert not n.writes


def test_foreign_image_and_stale_order_refuse_before_write():
    n, tools = setup()
    image = n.snapshot()['images'][0]
    n.layers.reverse()
    for key in (image['image_id'], 'foreign-image'):
        with pytest.raises(ValueError, match='stack'):
            asyncio.run(tools['reorder_texture_layers']('m', 'r', key, image['stack_sha256'], image['layer_ids']))
    assert not n.writes


def test_successful_edits_forward_fresh_native_metadata_and_return_refreshed_tokens():
    async def run():
        n, tools = setup()
        snap = n.snapshot()
        renamed = await tools['rename_texture_layer']('m', 'r', '0', snap['layers'][0]['state_sha256'], '眼妆')
        assert renamed['layer']['Name'] == '眼妆' and renamed['saved'] is False
        blended = await tools['set_texture_layer_blend']('m', 'r', '0', renamed['layer']['state_sha256'], 'CompositionMultiply')
        image = blended['images'][0]
        ordered = await tools['reorder_texture_layers']('m', 'r', image['image_id'], image['stack_sha256'], ['2','1','0'])
        assert ordered['images'][0]['layer_ids'] == ['2','1','0']
        row = ordered['layers'][-1]
        deleted = await tools['delete_texture_layer']('m', 'r', '0', row['state_sha256'], ordered['images'][0]['stack_sha256'])
        assert [r['layer_id'] for r in deleted['layers']] == ['2','1']
    asyncio.run(run())


def test_invalid_blend_refuses_and_native_partial_failure_blocks_further_edits():
    async def run():
        n, tools = setup()
        row = n.snapshot()['layers'][0]
        with pytest.raises(ValueError, match='composition mode'):
            await tools['set_texture_layer_blend']('m', 'r', '0', row['state_sha256'], 'InventedMode')
        assert not n.writes
        n.fail = 'LAYER_EDIT_UNCERTAIN: native failure'
        with pytest.raises(RuntimeError, match='UNCERTAIN'):
            await tools['rename_texture_layer']('m', 'r', '0', row['state_sha256'], 'Updated')
        assert n.uncertain
    asyncio.run(run())
