"""Offline checks for body masks, decals, freckles, moles and toenail refusal."""
import asyncio
import base64
import copy
import json

import pytest

from vroid_mcp.body_paint import bind_toenail_canvas, composite_decal, discover_toenails, freckle_marks, mole_marks, raster_body_mask
from vroid_mcp.body_paint_tools import register_body_paint_tools
from vroid_mcp.bounded_paint import decode_rgba_png
from vroid_mcp.texture_mapping import png_rgba

IDENTITY = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]


def image():
    return {'transferable_id': 'body', 'image_id': 'skin'}


def triangle_mesh(positions, uv, indices, label=None):
    return {'image': image(), 'positions': positions, 'uv0': uv, 'submeshes': [{'triangles': indices}]}


def test_body_mask_clips_to_triangles_and_reports_shared_uv():
    mesh = triangle_mesh([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1], [1, 1], [0, 0]], [0, 1, 2])
    shared = triangle_mesh([[10, 0, 0], [11, 0, 0], [10, 1, 0]], [[0, 1], [1, 1], [0, 0]], [0, 1, 2])
    mask, info = raster_body_mask([mesh, shared], image(), 4, 4)
    assert info['shared_uv_pixels'] > 0 and info['anatomical_sides_independent'] is False
    assert any(mask) and not all(mask)


def test_decal_keeps_alpha_and_rejects_pixels_outside_the_mask():
    mask = bytearray(8 * 8)
    for y in range(3, 6):
        for x in range(3, 6):
            mask[y * 8 + x] = 255
    source = bytearray(4 * 4 * 4)
    source[5 * 4:5 * 4 + 4] = bytes((10, 20, 30, 200))
    png, stats = composite_decal(8, 8, bytes(mask), png_rgba(4, 4, source), [0.5, 0.5], 0.5, 0)
    _, _, rgba = decode_rgba_png(png)
    assert stats['written_pixels'] == 1 and stats['clipped_pixels'] == 0
    assert any(pixel[3] == 200 for pixel in (rgba[i:i + 4] for i in range(0, len(rgba), 4)))
    with pytest.raises(ValueError, match='outside the body UV coverage'):
        composite_decal(8, 8, bytes(mask), png_rgba(4, 4, source), [0.1, 0.1], 0.5, 0)


def test_freckles_repeat_for_the_same_seed_and_stay_inside_the_mask():
    mask = bytearray(64 * 64)
    for index in range(64 * 64):
        y, x = divmod(index, 64)
        if 8 <= x < 56 and 8 <= y < 56:
            mask[index] = 255
    color = [0.4, 0.2, 0.1, 0.8]
    first, stats, _ = freckle_marks(64, 64, bytes(mask), 7, 8, 0.02, color, 0.05)
    second, _, _ = freckle_marks(64, 64, bytes(mask), 7, 8, 0.02, color, 0.05)
    other, _, _ = freckle_marks(64, 64, bytes(mask), 9, 8, 0.02, color, 0.05)
    assert first == second and first != other and stats['seed'] == 7
    _, _, rgba = decode_rgba_png(first)
    for index, alpha in enumerate(mask):
        if not alpha:
            assert rgba[index * 4 + 3] == 0


@pytest.mark.parametrize('center,angle', [([0, .5], 0), ([1, .5], 0), ([.5, 0], 0), ([.5, 1], 0), ([0, .5], 45)])
def test_decal_rejects_opaque_pixels_outside_canvas(center, angle):
    with pytest.raises(ValueError, match='outside the body UV coverage'):
        composite_decal(16, 16, bytes([255]) * 256,
                        png_rgba(4, 4, bytes([1, 2, 3, 255]) * 16), center, .5, angle)


def test_decal_allows_transparent_padding_outside_canvas():
    source = bytearray(4 * 4 * 4)
    source[8:12] = bytes([1, 2, 3, 200])
    _, stats = composite_decal(16, 16, bytes([255]) * 256, png_rgba(4, 4, source), [0, .5], .5, 0)
    assert stats['written_pixels'] == 4 and stats['clipped_pixels'] == 0


def test_mole_outside_the_mask_is_rejected():
    mask = bytearray(16 * 16)
    mask[8 * 16 + 8] = 255
    with pytest.raises(ValueError):
        mole_marks(16, 16, bytes(mask), [{'point': [0.05, 0.05], 'radius': 0.01, 'color': [0, 0, 0, 1]}])


def toe_scene(separate=True):
    mesh = {'name': 'Foot', 'world_matrix': copy.deepcopy(IDENTITY), 'positions': [], 'uv0': [], 'triangles': [],
            'weights': [], 'bone_nodes': [0, 1]}
    nodes = [{'id': 0, 'name': 'J_Bip_L_ToeBase'}, {'id': 1, 'name': 'J_Bip_R_ToeBase'}]
    for side, bone in enumerate(('L', 'R')):
        for cap in range(2):
            start = len(mesh['positions'])
            x = side * 0.2
            z = cap * 0.0001
            u = 0.1 + side * 0.4
            v = 0.1 + cap * 0.2
            mesh['positions'] += [[x, 0, z], [x + 0.01, 0, z], [x + 0.01, 0.01, z], [x, 0.01, z]]
            mesh['uv0'] += [[u, v], [u + 0.08, v], [u + 0.08, v + 0.08], [u, v + 0.08]]
            mesh['weights'] += [{'indices': [side, 0, 0, 0], 'weights': [1, 0, 0, 0]} for _ in range(4)]
            mesh['triangles'] += [start + i for i in ([0, 1, 2, 0, 2, 3] if cap == 0 else [0, 2, 1, 0, 3, 2])]
    if not separate:
        mesh['weights'][0]['weights'] = [0.5, 0.5, 0, 0]
    reference = {'model_token': 'model', 'meshes': [mesh], 'nodes': nodes}
    bindings = {'model_token': 'model', 'renderers': [{
        'name': 'Foot', 'materials': [{'slot': 0, 'name': 'foot', 'textures': [
            {'property': '_MainTex', 'instance_id': 3, 'width': 40, 'height': 40, 'offset': [0, 0], 'scale': [1, 1]}]}]}]}
    return reference, bindings


def test_isolated_toe_caps_are_reported_without_claiming_five_toes():
    found = discover_toenails(*toe_scene())
    assert found['separable'] is True and found['individual_toes_separable'] is False
    assert {item['id'] for item in found['targets']} == {'L_toes', 'R_toes'}


def test_fused_toes_and_missing_feet_are_refused():
    assert discover_toenails(*toe_scene(False))['separable'] is False
    assert discover_toenails({'model_token': 'model', 'meshes': [], 'nodes': []}, {'model_token': 'model', 'renderers': []})['reason'] == 'FOOT_RENDERER_MISSING_OR_AMBIGUOUS'


def test_shared_toenail_uv_is_not_independent():
    reference, bindings = toe_scene()
    mesh = reference['meshes'][0]
    mesh['uv0'][8:16] = copy.deepcopy(mesh['uv0'][:8])
    found = discover_toenails(reference, bindings)
    assert found['separable'] is False and 'UV' in found['reason']


def toe_surface(reference):
    mesh = copy.deepcopy(reference['meshes'][0])
    mesh['image'] = image()
    mesh['bone_ids'] = [{'name': n['name']} for n in reference['nodes']]
    mesh['submeshes'] = [{'triangles': mesh.pop('triangles')}]
    return {'model_token': 'model', 'meshes': [mesh]}


@pytest.mark.parametrize('mismatch', ['image', 'uv', 'bone', 'shared', 'ambiguous', 'model'])
def test_toenail_binding_rejects_unproven_canvas_correspondence(mismatch):
    reference, bindings = toe_scene()
    found = discover_toenails(reference, bindings)
    surface = toe_surface(reference)
    images = [image()]
    mesh = surface['meshes'][0]
    if mismatch == 'image':
        mesh['image'] = {'transferable_id': 'foreign', 'image_id': 'skin'}
    elif mismatch == 'uv':
        mesh['uv0'][0][0] += .01
    elif mismatch == 'bone':
        mesh['bone_ids'][0]['name'] = 'J_Bip_L_Hand'
    elif mismatch == 'shared':
        foreign = copy.deepcopy(mesh)
        foreign['positions'] = [[x + 1, y, z] for x, y, z in mesh['positions']]
        surface['meshes'].append(foreign)
    elif mismatch == 'ambiguous':
        foreign = copy.deepcopy(mesh)
        foreign['image'] = {'transferable_id': 'second', 'image_id': 'skin'}
        surface['meshes'].append(foreign)
        images.append(foreign['image'])
    else:
        surface['model_token'] = 'other-model'
    with pytest.raises(ValueError):
        bind_toenail_canvas(reference, surface, images, found)


def test_toenail_binding_refuses_renderer_skin_sharing_nail_uv():
    reference, bindings = toe_scene()
    surface = toe_surface(reference)
    mesh = reference['meshes'][0]
    start = len(mesh['positions'])
    mesh['positions'] += [[x + 1, y, z] for x, y, z in mesh['positions'][:4]]
    mesh['uv0'] += copy.deepcopy(mesh['uv0'][:4])
    reference['nodes'].append({'id': 2, 'name': 'J_Bip_L_Foot'})
    mesh['bone_nodes'].append(2)
    mesh['weights'] += [{'indices': [2, 0, 0, 0], 'weights': [1, 0, 0, 0]} for _ in range(4)]
    mesh['triangles'] += [start + i for i in [0, 1, 2, 0, 2, 3]]
    found = discover_toenails(reference, bindings)
    assert found['separable'] is True
    with pytest.raises(ValueError, match='unshared cap pixels'):
        bind_toenail_canvas(reference, surface, [image()], found)


class Native:
    def __init__(self):
        self.image = image()
        self.region = {'region_id': 'body', 'native_type': 'Native.BodySkin', 'part': 'BodySkin'}
        rgba = bytearray(16 * 16 * 4)
        for i in range(16 * 16):
            rgba[i * 4 + 3] = 255
        self.layer = png_rgba(16, 16, rgba)
        self.surface = {'meshes': [triangle_mesh([[0, 0, 0], [.2, 0, 0], [0, .2, 0]], [[0, 1], [.5, 1], [0, .5]], [0, 1, 2])]}
        self.writes = []
        self.reference = toe_scene()[0]
        self.bindings = toe_scene()[1]

    async def parameter_call(self, operation, args, mutating=False):
        assert args['expected_model'] == 'model'
        if operation == 'list_texture_regions':
            return {'regions': [self.region]}
        if operation == 'inspect_texture_canvas':
            return {'current_group_type': self.region['native_type'], 'images': [{'image': self.image}]}
        if operation == 'list_texture_layers':
            return {'layers': [{'layer_id': 'base', 'image': self.image}]}
        if operation == 'export_texture_layer':
            return {'base64': base64.b64encode(self.layer).decode(), 'layer': {'image': self.image}}
        if operation == 'export_texture_surface':
            return self.surface
        if operation == 'inspect_texture_renderers':
            return self.bindings
        if operation == 'import_texture_layer':
            assert mutating
            self.writes.append(args)
            return {'history_command_count': 3, 'layer': {'layer_id': 'new'}}
        raise AssertionError(operation)

    async def capture_body_reference(self, expected_model, label):
        path = self.path
        path.write_text(json.dumps(self.reference), encoding='utf8')
        return {'path': str(path)}


def tools(tmp_path):
    (tmp_path / 'saves').mkdir()
    (tmp_path / 'reviews').mkdir()
    native = Native()
    native.path = tmp_path / 'reference.json'
    registered = {}

    def decorator(**kwargs):
        def add(function):
            registered[function.__name__] = function
            return function
        return add

    register_body_paint_tools(decorator, native, tmp_path, None, None)
    return native, registered


def test_body_preview_creates_a_missing_saves_directory(tmp_path):
    async def scenario():
        native, api = tools(tmp_path)
        (tmp_path / 'saves').rmdir()
        mask = await api['export_body_paint_mask']('model', 'body')
        preview = await api['preview_body_marks'](
            expected_model='model', mask_id=mask['mask_id'], expected_mask_sha256=mask['manifest_sha256'],
            marks=[{'kind': 'stamp', 'points': [[0.1, 0.1]], 'radius': 0.2, 'hardness': 1,
                    'color': [1, 0, 0, 1], 'mirror_x': False}])
        written = tmp_path / 'saves' / preview['filename']
        assert written.is_file() and written.read_bytes()
        assert native.writes == []
    asyncio.run(scenario())


def test_body_paint_preview_matches_apply_and_leaves_the_source_png(tmp_path):
    async def scenario():
        native, api = tools(tmp_path)
        source = png_rgba(4, 4, bytes([9, 8, 7, 255]) + bytes(4 * 15))
        (tmp_path / 'saves' / 'tattoo.png').write_bytes(source)
        mask = await api['export_body_paint_mask']('model', 'body')
        args = {'expected_model': 'model', 'mask_id': mask['mask_id'], 'expected_mask_sha256': mask['manifest_sha256'],
                'filename': 'tattoo.png', 'png_sha256': __import__('hashlib').sha256(source).hexdigest(),
                'center': (0.1, 0.1), 'scale': 0.25, 'rotation_deg': 0}
        preview = await api['preview_body_decal'](**args)
        painted = await api['paint_body_decal'](**args, layer_name='tattoo', opacity=1)
        assert preview['png_sha256'] == painted['preview']['png_sha256']
        assert native.writes and painted['saved'] is False
        assert (tmp_path / 'saves' / 'tattoo.png').read_bytes() == source
    asyncio.run(scenario())


def test_stale_body_mask_is_rejected_before_import(tmp_path):
    async def scenario():
        native, api = tools(tmp_path)
        mask = await api['export_body_paint_mask']('model', 'body')
        native.surface = {'meshes': []}
        with pytest.raises(ValueError):
            await api['paint_body_marks'](expected_model='model', mask_id=mask['mask_id'],
                                          expected_mask_sha256=mask['manifest_sha256'],
                                          marks=[{'points': [[0.1, 0.1]], 'radius': 0.05, 'color': [1, 0, 0, 1]}])
        assert native.writes == []
    asyncio.run(scenario())


def test_toenail_paint_refuses_until_caps_are_separable(tmp_path):
    async def scenario():
        native, api = tools(tmp_path)
        native.reference = toe_scene(False)[0]
        report = await api['inspect_toenail_targets']('model')
        assert report['separable'] is False and 'map_id' not in report
        native.reference = toe_scene()[0]
        report = await api['inspect_toenail_targets']('model')
        assert report['separable'] is True and report['individual_toes_separable'] is False
        native.region = {'region_id': 'foot', 'native_type': 'Native.BodySkin', 'part': 'BodySkin'}
        native.layer = png_rgba(40, 40, bytes([0, 0, 0, 255]) * (40 * 40))
        native.surface = toe_surface(native.reference)
        preview = await api['preview_toenail_color']('model', 'foot', report['map_id'], report['manifest_sha256'],
                                                     [{'id': 'L_toes', 'color': [0.8, 0.1, 0.2, 1]}])
        _, _, pixels = decode_rgba_png((tmp_path / 'saves' / preview['filename']).read_bytes())
        assert any(pixels[i + 3] for i in range(0, len(pixels), 4))
        assert sum(pixels[i + 3] > 0 for i in range(0, len(pixels), 4)) == next(item['pixels'] for item in report['targets'] if item['id'] == 'L_toes')
        await api['paint_toenail_color']('model', 'foot', report['map_id'], report['manifest_sha256'],
                                      [{'id': 'L_toes', 'color': [0.8, 0.1, 0.2, 1]}], 'toes', 1)
        assert len(native.writes) == 1 and json.loads(native.writes[0]['image_id']) == image()
    asyncio.run(scenario())


def test_toenail_same_size_unrelated_canvas_never_imports(tmp_path):
    async def scenario():
        native, api = tools(tmp_path)
        report = await api['inspect_toenail_targets']('model')
        native.layer = png_rgba(40, 40, bytes([0, 0, 0, 255]) * 1600)
        with pytest.raises(ValueError):
            await api['paint_toenail_color']('model', 'body', report['map_id'], report['manifest_sha256'],
                                          [{'id': 'L_toes', 'color': [1, 0, 0, 1]}], 'toes', 1)
        assert native.writes == []
    asyncio.run(scenario())


def test_toenail_canvas_is_rechecked_immediately_before_import(tmp_path):
    async def scenario():
        native, api = tools(tmp_path)
        report = await api['inspect_toenail_targets']('model')
        native.surface = toe_surface(native.reference)
        native.layer = png_rgba(40, 40, bytes([0, 0, 0, 255]) * 1600)
        call = native.parameter_call
        exports = 0
        async def changed(operation, args, mutating=False):
            nonlocal exports
            if operation == 'export_texture_surface':
                exports += 1
                if exports == 2:
                    native.surface['meshes'][0]['uv0'][0][0] += .01
            return await call(operation, args, mutating)
        native.parameter_call = changed
        with pytest.raises(ValueError):
            await api['paint_toenail_color']('model', 'body', report['map_id'], report['manifest_sha256'],
                                          [{'id': 'L_toes', 'color': [1, 0, 0, 1]}], 'toes', 1)
        assert exports == 2 and native.writes == []
    asyncio.run(scenario())
