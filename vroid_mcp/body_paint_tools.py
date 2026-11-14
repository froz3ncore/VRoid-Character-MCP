"""Body tattoos, freckles, moles and toenail color on measured masks.

New pixels are imported as one native layer, so history can remove them.
The model is not saved and the caller's PNG is only read.
"""
import base64
import json
import re
import uuid
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .body_paint import composite_decal, discover_toenails, freckle_marks, mole_marks, raster_body_mask
from .bounded_paint import decode_rgba_png, render_marks
from .makeup_tools import CanvasMark, canonical, digest, geometry_digest, load_mask
from .texture_input import read_texture_input
from .texture_mapping import png_rgba, raster_nails


class Mole(BaseModel):
    model_config = ConfigDict(extra='forbid')
    point: tuple[float, float]
    radius: float = Field(ge=0.002, le=0.03)
    color: tuple[float, float, float, float]


class ToenailColor(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1, max_length=32)
    color: tuple[float, float, float, float]


def register_body_paint_tools(ready_tool, runtime, lab, read, edit):
    async def current_canvas(expected_model, region_id):
        regions = await runtime.parameter_call('list_texture_regions', {'expected_model': expected_model})
        matches = [item for item in regions['regions'] if item['region_id'] == region_id]
        if len(matches) != 1:
            raise ValueError('Texture region no longer exists')
        region = matches[0]
        canvas = await runtime.parameter_call('inspect_texture_canvas', {'expected_model': expected_model})
        if canvas['current_group_type'] != region['native_type']:
            raise ValueError('Open the matching native texture canvas first')
        return region, canvas

    def artifact(prefix, identifier):
        folder = (lab.resolve() / 'reviews' / f'{prefix}-{identifier}').resolve()
        if folder.parent != (lab.resolve() / 'reviews').resolve():
            raise ValueError('Paint artifacts must stay inside the lab reviews directory')
        return folder

    def read_manifest(prefix, identifier, file_name='manifest.json'):
        if not re.fullmatch(r'[a-f0-9]{32}', identifier):
            raise ValueError('Use a fresh id from the matching export or inspect tool')
        folder = artifact(prefix, identifier)
        path = folder / file_name
        if path.is_symlink() or path.resolve() != path or not path.is_file():
            raise ValueError('Paint manifest is missing or not a regular lab file')
        data = path.read_bytes()
        return json.loads(data), data, folder

    def publish(kind, manifest, png, extra):
        identifier = uuid.uuid4().hex
        filename = f'{kind}-{identifier}.png'
        (lab.resolve() / 'saves' / filename).write_bytes(png)
        folder = artifact(kind, identifier)
        folder.mkdir(parents=True, exist_ok=False)
        (folder / 'overlay.png').write_bytes(png)
        result = {'model_token': manifest['model_token'], 'mask_id': manifest.get('mask_id'),
                  'part': manifest.get('part'), 'region_id': manifest.get('region_id'), 'image': manifest.get('image'),
                  'filename': filename, 'png_sha256': digest(png), 'width': manifest['width'], 'height': manifest['height'],
                  'anatomical_sides_independent': manifest.get('anatomical_sides_independent', False),
                  'shared_uv_pixels': manifest.get('shared_uv_pixels', 0), 'model_modified': False, 'saved': False, **extra}
        (folder / 'preview.json').write_bytes(canonical(result))
        return result

    async def import_overlay(manifest, preview, layer_name, opacity):
        if not 0 <= opacity <= 1 or not 1 <= len(layer_name) <= 80:
            raise ValueError('Invalid layer opacity or name')
        data, width, height = read_texture_input(lab, preview['filename'], preview['png_sha256'], layer_name)
        if manifest.get('schema') == 'vroid-toenail-color-v1':
            await current_canvas(preview['model_token'], manifest['region_id'])
        else:
            await verify_mask(manifest, preview['model_token'])
        imported = await runtime.parameter_call('import_texture_layer', {
            'expected_model': preview['model_token'], 'region_id': manifest['region_id'],
            'image_id': json.dumps(manifest['image'], separators=(',', ':')),
            'png_base64': base64.b64encode(data).decode(), 'width': width, 'height': height,
            'layer_name': layer_name, 'opacity': opacity}, True)
        return {'model_token': preview['model_token'], 'preview': preview, 'native_import': imported, 'saved': False,
                'source_png_modified': False,
                'history_policy': 'Undo the reported native history_command_count to remove this new overlay. The model is not saved.'}

    def mask_bytes(png_path, expected_sha):
        data = png_path.read_bytes()
        if digest(data) != expected_sha:
            raise ValueError('Mask pixels changed')
        width, height, rgba = decode_rgba_png(data)
        return bytes(rgba[3::4]), width, height

    def load_paint_mask(mask_id, expected_sha, expected_model, allowed):
        try:
            manifest, raw, folder = read_manifest('body-mask', mask_id)
            mask, width, height = mask_bytes(folder / 'mask.png', manifest['mask_png_sha256'])
        except (OSError, ValueError, KeyError):
            manifest, mask = load_mask(lab, mask_id, expected_sha, expected_model)
            width, height = manifest['width'], manifest['height']
            raw = canonical(manifest)
        else:
            if digest(raw) != expected_sha:
                raise ValueError('Body paint mask manifest changed')
        if manifest.get('model_token') != expected_model:
            raise ValueError('Stale paint mask model identity')
        part = manifest.get('part')
        if part not in allowed:
            raise ValueError('This mask cannot be used for that paint. Eyes, lips and lashes are refused.')
        if part == 'FaceSkin' and manifest.get('area') != 'under_eye':
            raise ValueError('Full FaceSkin includes eyes and mouth. Use a Cheek or under-eye mask.')
        return manifest, mask, width, height

    async def verify_mask(manifest, expected_model):
        region, canvas = await current_canvas(expected_model, manifest['region_id'])
        if region['native_type'] != manifest['native_type'] or not any(item['image'] == manifest['image'] for item in canvas['images']):
            raise ValueError('Canvas region or image changed')
        if manifest.get('schema') == 'vroid-body-paint-mask-v1':
            surface = await runtime.parameter_call('export_texture_surface', {'expected_model': expected_model})
            if geometry_digest(surface) != manifest['uv_geometry_sha256']:
                raise ValueError('Body UV geometry changed; export a fresh mask')
            return
        layer = await runtime.parameter_call('export_texture_layer', {
            'expected_model': expected_model, 'region_id': manifest['region_id'], 'layer_id': manifest['source_layer_id']})
        png = base64.b64decode(layer.pop('base64'), validate=True)
        if digest(png) != manifest['source_png_sha256']:
            raise ValueError('Reference layer changed; export a fresh mask')

    @ready_tool(annotations=read)
    async def export_body_paint_mask(expected_model: str, region_id: str) -> dict:
        """Measure the open BodySkin canvas from its UV triangles. Pixels outside those triangles stay unpaintable. Shared pixels more than 2 cm apart are reported and cannot be edited as independent left and right sides. Does not paint or save."""
        region, canvas = await current_canvas(expected_model, region_id)
        if region['part'] != 'BodySkin':
            raise ValueError('Body paint requires BodySkin. Face regions stay on export_makeup_region_mask. Fingernails stay on export_nail_uv_map.')
        surface = await runtime.parameter_call('export_texture_surface', {'expected_model': expected_model})
        layers = await runtime.parameter_call('list_texture_layers', {'expected_model': expected_model, 'region_id': region_id})
        found = []
        for image in [item['image'] for item in canvas['images']]:
            layer = next((row for row in layers['layers'] if row['image'] == image), None)
            if layer is None:
                continue
            exported = await runtime.parameter_call('export_texture_layer', {
                'expected_model': expected_model, 'region_id': region_id, 'layer_id': layer['layer_id']})
            png = base64.b64decode(exported.pop('base64'), validate=True)
            width, height, _ = decode_rgba_png(png)
            try:
                mask, info = raster_body_mask(surface['meshes'], image, width, height)
            except ValueError:
                continue
            found.append((image, layer['layer_id'], png, width, height, mask, info))
        if len(found) != 1:
            raise ValueError('BodySkin must expose exactly one image with measured UV coverage')
        image, layer_id, png, width, height, mask, info = found[0]
        raw = bytearray(width * height * 4)
        for index, alpha in enumerate(mask):
            if alpha:
                raw[4 * index:4 * index + 4] = bytes((255, 255, 255, alpha))
        mask_png = png_rgba(width, height, raw)
        identifier = uuid.uuid4().hex
        folder = artifact('body-mask', identifier)
        folder.mkdir(parents=True, exist_ok=False)
        (folder / 'mask.png').write_bytes(mask_png)
        manifest = {'schema': 'vroid-body-paint-mask-v1', 'model_token': expected_model, 'mask_id': identifier,
                    'region_id': region_id, 'native_type': region['native_type'], 'part': 'BodySkin', 'image': image,
                    'source_layer_id': layer_id, 'source_png_sha256': digest(png), 'mask_png_sha256': digest(mask_png),
                    'width': width, 'height': height, 'uv_geometry_sha256': geometry_digest(surface), **info,
                    'scope': 'Only BodySkin triangles. Other UV islands stay transparent.'}
        data = json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf8')
        (folder / 'manifest.json').write_bytes(data)
        return {**manifest, 'manifest_sha256': digest(data), 'mask_path': str(folder / 'mask.png')}

    async def marks_preview(expected_model, mask_id, expected_sha, marks):
        manifest, mask, width, height = load_paint_mask(mask_id, expected_sha, expected_model, {'BodySkin'})
        await verify_mask(manifest, expected_model)
        values = [item.model_dump() if isinstance(item, CanvasMark) else item for item in marks]
        png, stats = render_marks(width, height, mask, values)
        return manifest, publish('body-marks', manifest, png, stats)

    @ready_tool(annotations=read)
    async def preview_body_marks(expected_model: str, mask_id: str, expected_mask_sha256: str = Field(min_length=64, max_length=64),
                                 marks: list[CanvasMark] = Field(min_length=1, max_length=32)) -> dict:
        """Preview stamps or strokes clipped to a BodySkin UV mask. mirror_x reflects the canvas and does not create independent sides when UV is shared. No model change."""
        _, preview = await marks_preview(expected_model, mask_id, expected_mask_sha256, marks)
        return preview

    @ready_tool(annotations=edit)
    async def paint_body_marks(expected_model: str, mask_id: str, expected_mask_sha256: str = Field(min_length=64, max_length=64),
                               marks: list[CanvasMark] = Field(min_length=1, max_length=32),
                               layer_name: str = Field(default='MCP body paint', min_length=1, max_length=80),
                               opacity: float = Field(default=1, ge=0, le=1)) -> dict:
        """Import that clipped preview as a new native layer. Does not save."""
        manifest, preview = await marks_preview(expected_model, mask_id, expected_mask_sha256, marks)
        return await import_overlay(manifest, preview, layer_name, opacity)

    async def decal_preview(expected_model, mask_id, expected_sha, filename, png_sha, center, scale, rotation_deg):
        manifest, mask, width, height = load_paint_mask(mask_id, expected_sha, expected_model, {'BodySkin'})
        await verify_mask(manifest, expected_model)
        source, _, _ = read_texture_input(lab, filename, png_sha, 'decal')
        png, stats = composite_decal(width, height, mask, source, center, scale, rotation_deg)
        if read_texture_input(lab, filename, png_sha, 'decal')[0] != source:
            raise RuntimeError('Source PNG was modified')
        preview = publish('body-decal', manifest, png, stats)
        preview['source_filename'] = filename
        preview['source_png_sha256'] = png_sha
        return manifest, preview

    @ready_tool(annotations=read)
    async def preview_body_decal(expected_model: str, mask_id: str, filename: str,
                                 png_sha256: str = Field(min_length=64, max_length=64),
                                 center: tuple[float, float] = (0.5, 0.5),
                                 expected_mask_sha256: str = Field(min_length=64, max_length=64),
                                 scale: float = Field(default=0.25, gt=0.02, le=1),
                                 rotation_deg: float = Field(default=0, ge=-180, le=180)) -> dict:
        """Place one PNG from lab saves onto the BodySkin mask. Scale is the source width divided by the shorter canvas side. Rotation is clockwise degrees about the center in top-left canvas space. Source alpha is copied. An opaque pixel outside the mask is rejected. The source file is not modified."""
        _, preview = await decal_preview(expected_model, mask_id, expected_mask_sha256, filename, png_sha256, list(center), scale, rotation_deg)
        return preview

    @ready_tool(annotations=edit)
    async def paint_body_decal(expected_model: str, mask_id: str, filename: str,
                               png_sha256: str = Field(min_length=64, max_length=64),
                               center: tuple[float, float] = (0.5, 0.5),
                               expected_mask_sha256: str = Field(min_length=64, max_length=64),
                               scale: float = Field(default=0.25, gt=0.02, le=1),
                               rotation_deg: float = Field(default=0, ge=-180, le=180),
                               layer_name: str = Field(default='MCP body decal', min_length=1, max_length=80),
                               opacity: float = Field(default=1, ge=0, le=1)) -> dict:
        """Import the fitted decal as a new native layer. Does not save or rewrite the source PNG."""
        manifest, preview = await decal_preview(expected_model, mask_id, expected_mask_sha256, filename, png_sha256, list(center), scale, rotation_deg)
        return await import_overlay(manifest, preview, layer_name, opacity)

    async def freckle_preview(expected_model, mask_id, expected_sha, seed, count, radius, color, min_spacing):
        manifest, mask, width, height = load_paint_mask(mask_id, expected_sha, expected_model, {'Cheek', 'BodySkin'})
        await verify_mask(manifest, expected_model)
        png, stats, marks = freckle_marks(width, height, mask, seed, count, radius, list(color), min_spacing)
        return manifest, publish('freckles', manifest, png, {**stats, 'marks': marks})

    @ready_tool(annotations=read)
    async def preview_freckles(expected_model: str, mask_id: str, color: tuple[float, float, float, float],
                               expected_mask_sha256: str = Field(min_length=64, max_length=64),
                               seed: int = Field(default=1, ge=0, le=2**31 - 1), count: int = Field(default=16, ge=1, le=256),
                               radius: float = Field(default=0.008, ge=0.002, le=0.02),
                               min_spacing: float = Field(default=0.02, ge=0.004, le=0.2)) -> dict:
        """Scatter freckles inside a Cheek or BodySkin mask. The same seed repeats the same placement. Eye, lip and lash masks are refused. No model change."""
        _, preview = await freckle_preview(expected_model, mask_id, expected_mask_sha256, seed, count, radius, color, min_spacing)
        return preview

    @ready_tool(annotations=edit)
    async def paint_freckles(expected_model: str, mask_id: str, color: tuple[float, float, float, float],
                             expected_mask_sha256: str = Field(min_length=64, max_length=64),
                             seed: int = Field(default=1, ge=0, le=2**31 - 1), count: int = Field(default=16, ge=1, le=256),
                             radius: float = Field(default=0.008, ge=0.002, le=0.02),
                             min_spacing: float = Field(default=0.02, ge=0.004, le=0.2),
                             layer_name: str = Field(default='MCP freckles', min_length=1, max_length=80),
                             opacity: float = Field(default=1, ge=0, le=1)) -> dict:
        """Import the seeded freckle preview as a new native layer. Does not save."""
        manifest, preview = await freckle_preview(expected_model, mask_id, expected_mask_sha256, seed, count, radius, color, min_spacing)
        return await import_overlay(manifest, preview, layer_name, opacity)

    async def mole_preview(expected_model, mask_id, expected_sha, moles):
        manifest, mask, width, height = load_paint_mask(mask_id, expected_sha, expected_model, {'Cheek', 'BodySkin', 'FaceSkin'})
        await verify_mask(manifest, expected_model)
        values = [item.model_dump() if isinstance(item, Mole) else item for item in moles]
        png, stats, marks = mole_marks(width, height, mask, values)
        return manifest, publish('moles', manifest, png, {**stats, 'marks': marks})

    @ready_tool(annotations=read)
    async def preview_moles(expected_model: str, mask_id: str, expected_mask_sha256: str = Field(min_length=64, max_length=64),
                            moles: list[Mole] = Field(min_length=1, max_length=32)) -> dict:
        """Preview point marks inside a Cheek, under-eye FaceSkin, or BodySkin mask. A point outside the mask is rejected. No model change."""
        _, preview = await mole_preview(expected_model, mask_id, expected_mask_sha256, moles)
        return preview

    @ready_tool(annotations=edit)
    async def paint_moles(expected_model: str, mask_id: str, expected_mask_sha256: str = Field(min_length=64, max_length=64),
                          moles: list[Mole] = Field(min_length=1, max_length=32),
                          layer_name: str = Field(default='MCP moles', min_length=1, max_length=80),
                          opacity: float = Field(default=1, ge=0, le=1)) -> dict:
        """Import the mole preview as a new native layer. Does not save."""
        manifest, preview = await mole_preview(expected_model, mask_id, expected_mask_sha256, moles)
        return await import_overlay(manifest, preview, layer_name, opacity)

    async def fresh_toenails(expected_model):
        record = await runtime.capture_body_reference(expected_model, 'Toenail targeting')
        reference = json.loads(Path(record['path']).read_text(encoding='utf8'))
        bindings = await runtime.parameter_call('inspect_texture_renderers', {'expected_model': expected_model})
        found = discover_toenails(reference, bindings)
        return record, found

    @ready_tool(annotations=read)
    async def inspect_toenail_targets(expected_model: str) -> dict:
        """Measure isolated Foot caps weighted only to toe bones. This does not call the ten-finger nail tool. If the toes are not a separable cap, the result says why and contains no guessed pixels."""
        record, found = await fresh_toenails(expected_model)
        public = {key: value for key, value in found.items() if key != 'nails'}
        public.update(model_token=expected_model, reference_path=record['path'], hand_nail_tool='export_nail_uv_map')
        if not found['separable']:
            return public
        identifier = uuid.uuid4().hex
        folder = artifact('toenail-map', identifier)
        folder.mkdir(parents=True, exist_ok=False)
        manifest = {'schema': 'vroid-toenail-map-v1', 'map_id': identifier, 'model_token': expected_model,
                    'geometry_sha256': found['geometry_sha256'], 'texture': found['texture'],
                    'individual_toes_separable': found['individual_toes_separable'],
                    'anatomical_sides_independent': found['anatomical_sides_independent'],
                    'target_ids': [item['id'] for item in found['targets']]}
        data = json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf8')
        (folder / 'manifest.json').write_bytes(data)
        public.update(map_id=identifier, manifest_sha256=digest(data), manifest_path=str(folder / 'manifest.json'))
        return public

    async def toenail_preview(expected_model, map_id, expected_sha, colors, region_id):
        manifest, raw, _ = read_manifest('toenail-map', map_id)
        if digest(raw) != expected_sha or manifest.get('model_token') != expected_model:
            raise ValueError('Stale toenail map')
        _, found = await fresh_toenails(expected_model)
        if not found['separable'] or found['geometry_sha256'] != manifest['geometry_sha256']:
            raise ValueError('Foot geometry changed or toenails are no longer separable')
        chosen = [item.model_dump() if isinstance(item, ToenailColor) else item for item in colors]
        ids = [item['id'] for item in chosen]
        if not ids or len(ids) != len(set(ids)) or any(item not in manifest['target_ids'] for item in ids):
            raise ValueError('Choose distinct ids from inspect_toenail_targets')
        region, canvas = await current_canvas(expected_model, region_id)
        if region['part'] not in ('BodySkin', 'Foot') and not str(region.get('native_type', '')).endswith('Foot'):
            raise ValueError('Open the foot texture canvas. export_nail_uv_map remains the hand-only tool.')
        width, height = found['texture']['width'], found['texture']['height']
        matching = []
        layers = await runtime.parameter_call('list_texture_layers', {'expected_model': expected_model, 'region_id': region_id})
        for image in [item['image'] for item in canvas['images']]:
            layer = next((row for row in layers['layers'] if row['image'] == image), None)
            if layer is None:
                continue
            exported = await runtime.parameter_call('export_texture_layer', {
                'expected_model': expected_model, 'region_id': region_id, 'layer_id': layer['layer_id']})
            png = base64.b64decode(exported.pop('base64'), validate=True)
            image_width, image_height, _ = decode_rgba_png(png)
            if (image_width, image_height) == (width, height):
                matching.append(image)
        if len(matching) != 1:
            raise ValueError('The open canvas has no unique image of the measured foot texture size')
        masks = raster_nails({'texture': {'width': width, 'height': height}, 'nails': found['nails']})
        raw_pixels = bytearray(width * height * 4)
        for item in chosen:
            color = item['color']
            if len(color) != 4 or any(isinstance(channel, bool) or not isinstance(channel, (int, float)) or not 0 <= channel <= 1 for channel in color):
                raise ValueError('Toenail color needs four normalized channels')
            pixel_color = bytes(round(channel * 255) for channel in color)
            for pixel in masks[item['id']]:
                raw_pixels[pixel * 4:pixel * 4 + 4] = pixel_color
        png = png_rgba(width, height, raw_pixels)
        receipt = {'schema': 'vroid-toenail-color-v1', 'model_token': expected_model, 'region_id': region_id,
                   'native_type': region['native_type'], 'part': region['part'], 'image': matching[0],
                   'width': width, 'height': height, 'anatomical_sides_independent': found['anatomical_sides_independent'],
                   'individual_toes_separable': found['individual_toes_separable'], 'shared_uv_pixels': 0}
        preview = publish('toenail-color', receipt, png, {'nails': ids})
        return receipt, preview

    @ready_tool(annotations=read)
    async def preview_toenail_color(expected_model: str, region_id: str, map_id: str,
                                    expected_map_sha256: str = Field(min_length=64, max_length=64),
                                    nails: list[ToenailColor] = Field(min_length=1, max_length=10)) -> dict:
        """Color measured toenail caps only. Refuses when inspection did not prove separable caps. Does not recolor surrounding foot skin and does not change the model."""
        _, preview = await toenail_preview(expected_model, map_id, expected_map_sha256, nails, region_id)
        return preview

    @ready_tool(annotations=edit)
    async def paint_toenail_color(expected_model: str, region_id: str, map_id: str,
                                  expected_map_sha256: str = Field(min_length=64, max_length=64),
                                  nails: list[ToenailColor] = Field(min_length=1, max_length=10),
                                  layer_name: str = Field(default='MCP toenail color', min_length=1, max_length=80),
                                  opacity: float = Field(default=1, ge=0, le=1)) -> dict:
        """Import that toenail preview as a new native layer. Does not save. Hand nails are unchanged."""
        manifest, preview = await toenail_preview(expected_model, map_id, expected_map_sha256, nails, region_id)
        return await import_overlay(manifest, preview, layer_name, opacity)
