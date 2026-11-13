import asyncio
import base64
import copy
import hashlib
import json
import struct
import zlib

import pytest

from vroid_mcp.runtime import Runtime
from vroid_mcp.texture_mapping import png_rgba
from vroid_mcp.texture_layer_state import state_digest


IMAGE = json.dumps({'transferable_id': 't', 'image_id': 'i'}, separators=(',', ':'))
LAYER = '["t","i","n"]'


def subject(tmp_path):
    runtime = Runtime(tmp_path)
    runtime.pixels = png_rgba(1, 1, bytes([120, 80, 40, 77]))
    runtime.row = {'layer_id': LAYER, 'image': json.loads(IMAGE), 'Name': 'Kept', 'Opacity': .5,
                   'Visibility': False, 'CompositionMode': 'Normal'}
    runtime.writes = []
    runtime.membership = True
    runtime.active = True
    runtime.fail = False
    runtime.editable = True
    runtime.fail_op = None
    runtime.material_color = [0, 0, 0, 1]
    runtime.stale_color_readback = False
    runtime.reencode = False
    async def settle(*args): return {'model_token': 'm'}
    async def call(op, args=None):
        args = args or {}
        if op == 'list_groups':
            return {'model_token': 'm', 'membership_complete': runtime.membership,
                    'groups': [{'id': 'r', 'type': 'Clothing.Top', 'active': runtime.active, 'fingerprint': 'f'}]}
        if op == 'list_texture_layers': return {'model_token': 'm', 'layers': [copy.deepcopy(runtime.row)] if runtime.editable else []}
        if op == 'export_texture_layer':
            return {'model_token': 'm', 'layer': copy.deepcopy(runtime.row), 'width': 1, 'height': 1,
                    'base64': base64.b64encode(runtime.pixels).decode()}
        if op == 'inspect_hair_materials': return {'model_token': 'm', 'materials': [
            {'id': 'mat', 'group_ids': ['r'], 'colors': [{'key': 'base:g', 'binding_id': 'base:g', 'readback_available': False},
                {'key': 'Tint', 'binding_id': 'mat:Tint', 'readback_available': True, 'value': runtime.material_color}],
             'textures': [{'region_id': '["hair_material","mat"]', 'image_id': IMAGE}]}]}
        if op == 'list_group_parameters': return {'model_token': 'm', 'parameters': []}
        runtime.writes.append((op, args))
        if runtime.fail or op == runtime.fail_op: raise RuntimeError('LAYER_EDIT_UNCERTAIN: injected after dispatch')
        if op in ('begin_clothing_edit', 'begin_hair_edit'): runtime.editable = True
        if op == 'replace_texture_layer':
            before = runtime.pixels
            runtime.pixels = base64.b64decode(args['png_base64'])
            if runtime.reencode:
                # A legal ancillary chunk changes container SHA without pixels.
                chunk = b'tEXt'+b'encoder\x00native-double'
                runtime.pixels = (runtime.pixels[:33]+struct.pack('>I', len(chunk)-4)+chunk
                    + struct.pack('>I', zlib.crc32(chunk)&0xffffffff)+runtime.pixels[33:])
            return {'model_token': 'm', 'frame': 1, 'history_command_count': 1, 'preserved_nonpixel_state': True,
                    'before': {'base64': base64.b64encode(before).decode()},
                    'after': {'base64': base64.b64encode(runtime.pixels).decode()}}
        if op == 'set_hair_material_color':
            if args['key'] == 'Tint' and not runtime.stale_color_readback:
                runtime.material_color = args['color']
            return {'model_token': 'm', 'frame': 1,
                'readback_available': not args['key'].startswith('base:'), 'requested': args['color']}
        return {'model_token': 'm', 'frame': 1, 'screen_entered': False}
    runtime._call, runtime._settle = call, settle
    return runtime


def test_conversion_requires_complete_active_membership_and_returns_fresh_layers(tmp_path):
    async def run():
        r = subject(tmp_path)
        r.membership = False
        with pytest.raises(ValueError, match='MEMBERSHIP'): await r.begin_clothing_edit('m', 'r')
        r.membership, r.active = True, False
        with pytest.raises(ValueError, match='ACTIVE'): await r.begin_clothing_edit('m', 'r')
        assert not r.writes
        r.active = True
        out = await r.begin_clothing_edit('m', 'r')
        assert out['screen_entered'] is False and out['settled'] and out['layers'][0]['layer_id'] == LAYER
        assert r.writes[0][1]['group_fingerprint'] == 'f'
    asyncio.run(run())


def test_recolor_hash_and_metadata_preconditions_and_actual_receipt(tmp_path):
    async def run():
        r = subject(tmp_path)
        args = ('m', 'r', IMAGE, LAYER, [0.5, 1, 1])
        with pytest.raises(ValueError, match='content'): await r.recolor_texture_layer(*args, expected_layer_sha256='a'*64)
        assert not r.writes
        sha = hashlib.sha256(r.pixels).hexdigest()
        out = await r.recolor_texture_layer(*args, expected_layer_sha256=sha,
                                          expected_state_sha256=state_digest(r.row))
        assert out['before_sha256'] == sha and out['after_sha256'] == hashlib.sha256(r.pixels).hexdigest()
        assert out['preserved_nonpixel_state'] and out['settled']
        assert base64.b64decode(r.writes[0][1]['expected_rgba_base64']) == bytes([120, 80, 40, 77])
    asyncio.run(run())


def test_replacement_validates_input_hash_pixels_and_dimensions_before_write(tmp_path):
    async def run():
        r = subject(tmp_path)
        saves = tmp_path/'saves'; saves.mkdir()
        png = png_rgba(2, 1, bytes([1, 2, 3, 4]*2)); (saves/'input.png').write_bytes(png)
        sha = hashlib.sha256(r.pixels).hexdigest()
        with pytest.raises(ValueError, match='dimension'):
            await r.replace_texture_layer('m', 'r', IMAGE, LAYER, 'input.png', hashlib.sha256(png).hexdigest(), sha)
        with pytest.raises(ValueError, match='hash'):
            await r.replace_texture_layer('m', 'r', IMAGE, LAYER, 'input.png', 'a'*64, sha)
        assert not r.writes
    asyncio.run(run())


def test_known_base_completion_continues_without_fake_readback_and_uncertain_raster_blocks(tmp_path):
    async def run():
        r = subject(tmp_path)
        # Known synchronous completion is distinct from unavailable exact readback.
        out = await r.colorize('m', 'global', [1, 0, 0], group_id='r', material_ids=['mat'])
        assert not out['partial'] and out['ok'] and len(out['applied']) == 2
        assert out['applied'][0]['receipt']['readback_available'] is False
        assert not out['remaining'] and len(r.writes) == 2
        r = subject(tmp_path); r.fail = True
        with pytest.raises(RuntimeError, match='UNCERTAIN'):
            await r.recolor_texture_layer('m', 'r', IMAGE, LAYER, [1, 0, 0],
                expected_layer_sha256=hashlib.sha256(r.pixels).hexdigest())
        assert r.uncertain
    asyncio.run(run())


def test_hair_conversion_fresh_region_mapping_and_colorize_filters_prevalidate(tmp_path):
    async def run():
        r = subject(tmp_path)
        out = await r.begin_hair_edit('m', 'mat')
        assert out['screen_entered'] is False and out['textures'][0]['image_id'] == IMAGE
        count = len(r.writes)
        with pytest.raises(ValueError, match='filter'):
            await r.colorize('m', 'both', [1, 0, 0], group_id='r', material_ids=['foreign'])
        with pytest.raises(ValueError): await r.colorize('m', 'both', [2, 0, 0], group_id='r')
        assert len(r.writes) == count
    asyncio.run(run())


def test_colorize_converts_before_fresh_snapshots_and_stops_actual_uncertain_work(tmp_path):
    async def run():
        r = subject(tmp_path); r.editable = False
        out = await r.colorize('m', 'both', [.5, 1, 1], group_id='r', material_ids=['mat'], layer_ids=[LAYER])
        assert out['ok'] and [op for op, _ in r.writes] == ['begin_hair_edit',
            'set_hair_material_color', 'set_hair_material_color', 'replace_texture_layer']
        assert out['applied'][0]['kind'] == 'conversion'
        r = subject(tmp_path); r.fail_op = 'set_hair_material_color'
        out = await r.colorize('m', 'both', [1, 0, 0], group_id='r', material_ids=['mat'])
        assert not out['ok'] and out['partial'] and out['uncertain'] and not out['applied']
        assert len(r.writes) == 1 and out['remaining'] and not out['automatic_rollback']
    asyncio.run(run())


def test_recolor_wrong_image_stale_state_and_corrupt_input_do_not_dispatch(tmp_path):
    async def run():
        r = subject(tmp_path)
        sha = hashlib.sha256(r.pixels).hexdigest()
        with pytest.raises(ValueError, match='identity'):
            await r.recolor_texture_layer('m', 'r', 'foreign', LAYER, [1, 1, 1], expected_layer_sha256=sha)
        with pytest.raises(ValueError, match='metadata'):
            await r.recolor_texture_layer('m', 'r', IMAGE, LAYER, [1, 1, 1],
                expected_layer_sha256=sha, expected_state_sha256='b'*64)
        saves = tmp_path/'saves'; saves.mkdir()
        bad = r.pixels[:-1]; (saves/'bad.png').write_bytes(bad)
        with pytest.raises(ValueError):
            await r.replace_texture_layer('m', 'r', IMAGE, LAYER, 'bad.png', hashlib.sha256(bad).hexdigest(), sha)
        assert not r.writes
    asyncio.run(run())


def test_exact_available_material_readback_must_match_after_settling(tmp_path):
    async def run():
        r = subject(tmp_path); r.stale_color_readback = True
        with pytest.raises(RuntimeError, match='READBACK_MISMATCH'):
            await r.set_hair_material_color('m', 'mat', 'Tint', [1, 0, 0])
        assert r.uncertain and len(r.writes) == 1
    asyncio.run(run())


def test_raster_postsettle_content_change_is_uncertain(tmp_path):
    async def run():
        r = subject(tmp_path)
        async def changed(*args):
            r.pixels = png_rgba(1, 1, bytes([9, 9, 9, 77]))
            return {'model_token': 'm'}
        r._settle = changed
        with pytest.raises(RuntimeError, match='READBACK_MISMATCH'):
            await r.recolor_texture_layer('m', 'r', IMAGE, LAYER, [.5, 1, 1],
                expected_layer_sha256=hashlib.sha256(r.pixels).hexdigest())
        assert r.uncertain
    asyncio.run(run())


def test_native_png_container_can_differ_when_decoded_pixels_match(tmp_path):
    async def run():
        r = subject(tmp_path); r.reencode = True
        source_sha = hashlib.sha256(r.pixels).hexdigest()
        out = await r.recolor_texture_layer('m', 'r', IMAGE, LAYER, [.5, 1, 1],
            expected_layer_sha256=source_sha)
        assert out['readback_verified'] and not r.uncertain
        assert out['before_sha256'] == source_sha
        assert out['after_sha256'] != out['input_sha256']
        assert out['after_sha256'] == hashlib.sha256(r.pixels).hexdigest()
    asyncio.run(run())


def test_native_prewrite_stale_pixel_rejection_does_not_claim_unknown_dispatch(tmp_path):
    async def run():
        r = subject(tmp_path); original = r._call
        async def rejected(op, args=None):
            if op == 'replace_texture_layer': raise RuntimeError('STALE_LAYER_CONTENT')
            return await original(op, args)
        r._call = rejected
        with pytest.raises(RuntimeError, match='STALE_LAYER_CONTENT'):
            await r.recolor_texture_layer('m', 'r', IMAGE, LAYER, [.5, 1, 1],
                expected_layer_sha256=hashlib.sha256(r.pixels).hexdigest())
        assert not r.uncertain and not r.writes
    asyncio.run(run())


def test_composed_read_failure_keeps_completed_conversion_receipt(tmp_path):
    async def run():
        r = subject(tmp_path); r.editable = False; original = r._call
        async def garment(op, args=None):
            if op == 'inspect_hair_materials': return {'model_token': 'm', 'materials': []}
            if op == 'list_group_parameters': raise RuntimeError('Native garment color query failed')
            return await original(op, args)
        r._call = garment
        out = await r.colorize('m', 'both', [1, 0, 0], group_id='r')
        assert out['partial'] and not out['ok'] and not out['uncertain']
        assert len(out['applied']) == 1 and out['applied'][0]['kind'] == 'conversion'
        assert [op for op, _ in r.writes] == ['begin_clothing_edit']
        assert out['remaining']
    asyncio.run(run())


def test_garment_composition_uses_typed_exact_owner_binding_deduplicated_and_read_back(tmp_path):
    async def run():
        r = subject(tmp_path); original = r._call
        row = {'id': 'exact-binding', 'source': 'worn_color_query', 'kind': 'color', 'editable': True,
            'units': 'native_rgba', 'group_id': 'owner', 'binding_keys': ['owner/path'], 'value': [0, 0, 0, 1]}
        async def garment(op, args=None):
            if op == 'inspect_hair_materials': return {'model_token': 'm', 'materials': []}
            if op == 'list_group_parameters':
                return {'model_token': 'm', 'parameters': [copy.deepcopy(row), {**row, 'id': 'alias'}], 'errors': []}
            if op == 'set_group_parameters':
                r.writes.append((op, args)); row['value'] = args['changes'][0]['value']
                return {'model_token': 'm', 'frame': 1, 'ok': True}
            return await original(op, args)
        r._call = garment
        out = await r.colorize('m', 'global', [.5, .2, .8], group_id='r')
        assert out['ok'] and len(out['applied']) == 1 and len(r.writes) == 1
        assert r.writes[0][1]['changes'] == [{'id': 'exact-binding', 'type': 'color',
            'units': 'native_rgba', 'value': [.5, .2, .8, 1]}]
        assert out['applied'][0]['receipt']['readback_verified']
    asyncio.run(run())


def test_incomplete_worn_color_discovery_refuses_composition(tmp_path):
    async def run():
        r = subject(tmp_path); original = r._call
        async def garment(op, args=None):
            if op == 'inspect_hair_materials': return {'model_token': 'm', 'materials': []}
            if op == 'list_group_parameters':
                return {'model_token': 'm', 'parameters': [], 'errors': [{'source': 'GetClothingQuery', 'error': 'unsupported path'}]}
            return await original(op, args)
        r._call = garment
        with pytest.raises(ValueError, match='DISCOVERY_INCOMPLETE'):
            await r.colorize('m', 'global', [1, 0, 0], group_id='r')
        assert not r.writes
    asyncio.run(run())


def garment_readback_subject(tmp_path, fault):
    runtime = subject(tmp_path)
    original = runtime._call
    rows = [{'id': 'garment-'+str(i), 'group_id': 'owner', 'source': 'worn_color_query',
             'editable': True, 'binding_keys': ['owner/path-'+str(i)], 'units': 'native_rgba',
             'value': [0, 0, 0, 1]} for i in range(2)]
    async def call(op, args=None):
        if op == 'inspect_hair_materials':
            return {'model_token': 'm', 'materials': []}
        if op == 'list_group_parameters':
            if runtime.writes:
                if fault == 'query':
                    raise RuntimeError('exact post-write readback query failed')
                if fault == 'cancel':
                    raise asyncio.CancelledError('cancelled during exact garment readback')
                rows[0]['value'] = fault
            return {'model_token': 'm', 'parameters': copy.deepcopy(rows), 'errors': []}
        if op == 'set_group_parameters':
            runtime.writes.append((op, args))
            rows[0]['value'] = args['changes'][0]['value']
            return {'model_token': 'm', 'frame': 1, 'ok': True, 'history_command_count': 1}
        return await original(op, args)
    runtime._call = call
    return runtime


def assert_failed_garment_receipt(runtime, result):
    assert len(runtime.writes) == 1 and runtime.uncertain
    assert result['partial'] and result['uncertain'] and not result['ok']
    assert not result['automatic_rollback'] and len(result['applied']) == 1
    applied = result['applied'][0]
    assert applied['parameter_id'] == 'garment-0' and applied['group_id'] == 'owner'
    receipt = applied['receipt']
    assert receipt['ok'] and receipt['settled'] and receipt['history_command_count'] == 1
    assert receipt['readback_verified'] is False
    assert receipt['verification_status'] in ('failed', 'unresolved')
    assert receipt['verification_error']
    assert result['remaining'] == [{'kind': 'garment', 'parameter_id': 'garment-1', 'group_id': 'owner'}]


def test_garment_postwrite_query_failure_retains_settled_receipt_and_blocks_later_targets(tmp_path):
    async def run():
        runtime = garment_readback_subject(tmp_path, 'query')
        result = await runtime.colorize('m', 'global', [.5, .2, .8], group_id='r')
        assert_failed_garment_receipt(runtime, result)
        assert 'exact post-write readback query failed' in result['error']
        assert result['applied'][0]['receipt']['verification_status'] == 'unresolved'
    asyncio.run(run())


def test_garment_postwrite_cancellation_preserves_partial_receipt_and_propagates(tmp_path):
    async def run():
        runtime = garment_readback_subject(tmp_path, 'cancel')
        with pytest.raises(asyncio.CancelledError) as cancelled:
            await runtime.colorize('m', 'global', [.5, .2, .8], group_id='r')
        assert_failed_garment_receipt(runtime, cancelled.value.partial_result)
        assert cancelled.value.partial_result['applied'][0]['receipt']['verification_status'] == 'unresolved'
    asyncio.run(run())


@pytest.mark.parametrize('readback', [None, [.5, .2, .8], [.5, .2, .8, 1, 0],
    [.5, .2, float('nan'), 1], [.5, .2, float('inf'), 1], [.5, .2, 'bad', 1],
    [True, .2, .8, 1], [.5, .2, .8, 0]])
def test_garment_postwrite_readback_requires_four_finite_matching_channels(tmp_path, readback):
    async def run():
        runtime = garment_readback_subject(tmp_path, readback)
        result = await runtime.colorize('m', 'global', [.5, .2, .8], group_id='r')
        assert_failed_garment_receipt(runtime, result)
        assert result['applied'][0]['receipt']['verification_status'] == 'failed'
        assert 'GARMENT_COLOR_READBACK_MISMATCH' in result['error']
    asyncio.run(run())
