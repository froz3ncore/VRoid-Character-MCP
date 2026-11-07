"""Serialized conversion, direct raster history and exact color composition.

Adapted from mcjo79/vroid-mcp Textures.cs, Hair.cs, AdvancedEdit.cs and
mcp_server/vroid_mcp.py at 0dc7d5e (MIT; licenses/mcjo79-0dc7d5e.txt).
"""
import base64
import hashlib
import json
import re

from .bounded_paint import decode_rgba_png
from .texture_input import read_texture_input
from .texture_layer_state import metadata, state_digest, describe_layers
from .texture_pixels import recolor_png, validate_color, validate_recolor

PREWRITE_ERRORS = (
    'STALE_LAYER_CONTENT', 'STALE_LAYER_STACK', 'IMAGE_IDENTITY_MISMATCH',
    'EXACT_IMAGE_IDENTITY_REQUIRED', 'PNG_DIMENSION_MISMATCH',
    'NATIVE_LAYER_GROUP_UNSUPPORTED', 'ACTIVE_GROUP_MEMBERSHIP_REQUIRED',
    'ACTIVE_OR_STALE_GROUP', 'NO_ACTIVE_TRANSFERABLES', 'ACTIVE_HAIR_MATERIAL_REQUIRED',
    'EXACT_MATERIAL_COLOR_KEY_REQUIRED', 'AMBIGUOUS_MATERIAL_COLOR_KEY',
)
PREWRITE_PATTERN = r'^(?:Error: )?(?:'+'|'.join(PREWRITE_ERRORS)+r')(?::|\s|$)'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def hash_token(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('Expected a lowercase SHA256 content token')


class TextureTools:
    async def _texture_read(self, op, expected_model, **args):
        if not isinstance(expected_model, str) or not expected_model:
            raise ValueError('EXPECTED_MODEL_REQUIRED')
        out = await self._call(op, {'expected_model': expected_model, **args})
        if out.get('model_token') != expected_model:
            raise ValueError('STALE_MODEL')
        return out

    async def _texture_write(self, op, expected_model, **args):
        # These exact native preconditions run before any history dispatch.
        # A wrapped LAYER_EDIT_UNCERTAIN cannot match this anchored expression.
        completed = False
        try:
            out = await self._texture_read(op, expected_model, **args)
            completed = True
            await self._settled_for(expected_model, out.get('frame', -1))
            out['settled'] = True
            return out
        except BaseException as error:
            if completed or not isinstance(error, Exception) or not re.match(PREWRITE_PATTERN, str(error)):
                self.uncertain = True
            raise

    async def _active_texture_group(self, expected_model, group_id):
        inventory = await self._texture_read('list_groups', expected_model)
        if inventory.get('membership_complete') is not True:
            raise ValueError('GROUP_MEMBERSHIP_INCOMPLETE')
        rows = [r for r in inventory['groups'] if r['id'] == group_id and r.get('active') is True]
        if len(rows) != 1:
            raise ValueError('ACTIVE_GROUP_REQUIRED')
        return rows[0]

    async def _begin_texture_edit(self, expected_model, group_id=None, material_id=None):
        if group_id is not None:
            group = await self._active_texture_group(expected_model, group_id)
            out = await self._texture_write('begin_clothing_edit', expected_model,
                group_id=group_id, group_fingerprint=group['fingerprint'])
            try:
                fresh = await self._texture_read('list_texture_layers', expected_model, region_id=group_id)
                if not fresh['layers']:
                    raise RuntimeError('CONVERSION_READBACK_MISMATCH: no fresh raster layers')
                out.update(describe_layers(fresh))
            except BaseException:
                self.uncertain = True
                raise
        else:
            materials = await self._texture_read('inspect_hair_materials', expected_model)
            matches = [r for r in materials['materials'] if r['id'] == material_id and r['group_ids']]
            if len(matches) != 1:
                raise ValueError('ACTIVE_HAIR_MATERIAL_REQUIRED')
            out = await self._texture_write('begin_hair_edit', expected_model, material_id=material_id)
            try:
                fresh = await self._texture_read('inspect_hair_materials', expected_model)
                selected = [r for r in fresh['materials'] if r['id'] == material_id and r['group_ids']]
                if len(selected) != 1 or not selected[0]['textures']:
                    raise RuntimeError('CONVERSION_READBACK_MISMATCH: no fresh material images')
                out['textures'] = selected[0]['textures']
                out['regions'] = []
                for region in dict.fromkeys(t['region_id'] for t in out['textures']):
                    layers = await self._texture_read('list_texture_layers', expected_model, region_id=region)
                    if not layers['layers']:
                        raise RuntimeError('CONVERSION_READBACK_MISMATCH: no fresh material raster layers')
                    out['regions'].append(describe_layers(layers))
            except BaseException:
                self.uncertain = True
                raise
        out['screen_entered'] = False
        out['saved'] = False
        return out

    async def begin_clothing_edit(self, expected_model, group_id):
        async with self.lock:
            return await self._begin_texture_edit(expected_model, group_id=group_id)

    async def begin_hair_edit(self, expected_model, material_id):
        async with self.lock:
            return await self._begin_texture_edit(expected_model, material_id=material_id)

    async def _raster_snapshot(self, expected_model, region_id, image_id, layer_id,
                               expected_layer_sha256, expected_state_sha256=None):
        hash_token(expected_layer_sha256)
        if expected_state_sha256 is not None:
            hash_token(expected_state_sha256)
        listed = await self._texture_read('list_texture_layers', expected_model, region_id=region_id)
        stack = [r for r in listed['layers'] if json.dumps(r['image'], separators=(',', ':')) == image_id]
        matches = [r for r in stack if r['layer_id'] == layer_id]
        if len(matches) != 1:
            raise ValueError('Exact image/layer identity mismatch')
        row = matches[0]
        if expected_state_sha256 is not None and state_digest(row) != expected_state_sha256:
            raise ValueError('Layer metadata changed')
        exported = await self._texture_read('export_texture_layer', expected_model,
            region_id=region_id, layer_id=layer_id)
        if metadata(exported['layer']) != metadata(row):
            raise ValueError('Layer metadata changed during pixel snapshot')
        source = base64.b64decode(exported['base64'], validate=True)
        if digest(source) != expected_layer_sha256:
            raise ValueError('Layer content changed; export again before writing')
        width, height, rgba = decode_rgba_png(source)
        if (width, height) != (exported['width'], exported['height']):
            raise ValueError('Exported pixel dimensions differ')
        return source, width, height, rgba, row, stack

    async def _replace_raster(self, expected_model, region_id, image_id, layer_id, data, snapshot):
        source, width, height, rgba, row, stack = snapshot
        w, h, _ = decode_rgba_png(data)
        if (w, h) != (width, height):
            raise ValueError('Replacement dimensions must match existing raster dimensions')
        result = await self._texture_write('replace_texture_layer', expected_model,
            region_id=region_id, image_id=image_id, layer_id=layer_id,
            png_base64=base64.b64encode(data).decode(), width=width, height=height,
            expected_rgba_base64=base64.b64encode(rgba).decode(), expected_layer=metadata(row),
            expected_stack=[metadata(r) for r in stack])
        try:
            before = base64.b64decode(result.pop('before')['base64'], validate=True)
            immediate = base64.b64decode(result.pop('after')['base64'], validate=True)
            exported = await self._texture_read('export_texture_layer', expected_model,
                region_id=region_id, layer_id=layer_id)
            after = base64.b64decode(exported['base64'], validate=True)
            layers = await self._texture_read('list_texture_layers', expected_model, region_id=region_id)
            current_stack = [metadata(r) for r in layers['layers']
                             if json.dumps(r['image'], separators=(',', ':')) == image_id]
            if current_stack != [metadata(r) for r in stack]:
                raise RuntimeError('NONPIXEL_STATE_READBACK_MISMATCH')
            if (decode_rgba_png(before) != (width, height, rgba)
                    or decode_rgba_png(after) != decode_rgba_png(data)
                    or decode_rgba_png(immediate) != decode_rgba_png(data)):
                raise RuntimeError('PIXEL_READBACK_MISMATCH')
            result.update(before_sha256=digest(before), after_sha256=digest(after),
                input_sha256=digest(data), expected_layer_sha256=digest(source), width=width, height=height,
                readback_verified=True, visible_change_verified=False,
                quantization_policy='RGBA8 round-half-up input; actual native readback compared byte-for-byte')
        except BaseException:
            self.uncertain = True
            raise
        return result

    async def replace_texture_layer(self, expected_model, region_id, image_id, layer_id, filename,
                                    expected_png_sha256, expected_layer_sha256, expected_state_sha256=None):
        hash_token(expected_png_sha256)
        data, _, _ = read_texture_input(self.lab, filename, expected_png_sha256, 'replacement')
        decode_rgba_png(data)
        async with self.lock:
            snapshot = await self._raster_snapshot(expected_model, region_id, image_id, layer_id,
                expected_layer_sha256, expected_state_sha256)
            return await self._replace_raster(expected_model, region_id, image_id, layer_id, data, snapshot)

    async def recolor_texture_layer(self, expected_model, region_id, image_id, layer_id, color,
                                    mode='multiply', strength=1, expected_layer_sha256=None,
                                    expected_state_sha256=None):
        validate_recolor(color, mode, strength)
        async with self.lock:
            snapshot = await self._raster_snapshot(expected_model, region_id, image_id, layer_id,
                expected_layer_sha256, expected_state_sha256)
            return await self._replace_raster(expected_model, region_id, image_id, layer_id,
                recolor_png(snapshot[0], color, mode, strength), snapshot)

    async def _hair_color(self, expected_model, material_id, key, color):
        listed = await self._texture_read('inspect_hair_materials', expected_model)
        matches = [c for m in listed['materials'] if m['id'] == material_id and m['group_ids']
                   for c in m['colors'] if c['key'] == key]
        if len(matches) != 1:
            raise ValueError('Exact active material color key required')
        result = await self._texture_write('set_hair_material_color', expected_model,
            material_id=material_id, key=key, color=color)
        if matches[0]['readback_available']:
            try:
                fresh = await self._texture_read('inspect_hair_materials', expected_model)
                current = [c for m in fresh['materials'] if m['id'] == material_id and m['group_ids']
                           for c in m['colors'] if c['binding_id'] == matches[0]['binding_id']]
                if (len(current) != 1 or len(current[0]['value']) != 4
                        or any(abs(a-b) > 1e-5 for a, b in zip(current[0]['value'], color))):
                    raise RuntimeError('MATERIAL_COLOR_READBACK_MISMATCH')
                result.update(after=current[0]['value'], readback_verified=True)
            except BaseException:
                self.uncertain = True
                raise
        result['visible_change_verified'] = False
        return result

    async def set_hair_material_color(self, expected_model, material_id, key, color):
        color = validate_color(color)
        async with self.lock:
            return await self._hair_color(expected_model, material_id, key, color)

    async def colorize(self, expected_model, target, color, group_id, material_ids=None,
                       layer_ids=None, mode='multiply', strength=1):
        color = validate_recolor(color, mode, strength)
        if target not in ('global', 'texture', 'both'):
            raise ValueError('Target must be global, texture or both')
        if target == 'global' and layer_ids is not None:
            raise ValueError('Layer filter requires texture or both target')
        for value in (material_ids, layer_ids):
            if value is not None and (not isinstance(value, list) or not value or len(set(value)) != len(value)
                    or any(not isinstance(v, str) or not v for v in value)):
                raise ValueError('Filters require nonempty unique exact IDs')
        async with self.lock:
            await self._active_texture_group(expected_model, group_id)
            hair = await self._texture_read('inspect_hair_materials', expected_model)
            scoped = [m for m in hair['materials'] if group_id in m['group_ids']]
            if material_ids is not None:
                if not set(material_ids) <= {m['id'] for m in scoped}:
                    raise ValueError('Material filter is outside selected active group')
                scoped = [m for m in scoped if m['id'] in material_ids]
            applied = []
            raster_work = []
            if target in ('texture', 'both'):
                try:
                    raster_work = await self._colorize_rasters(expected_model, group_id, scoped,
                        layer_ids, color, mode, strength, applied)
                    # Conversion changes topology. Re-read exact color paths too.
                    fresh = await self._texture_read('inspect_hair_materials', expected_model)
                    scoped = [m for m in fresh['materials'] if m['id'] in {m['id'] for m in scoped}
                              and group_id in m['group_ids']]
                except Exception as error:
                    if not applied and not self.uncertain:
                        raise
                    return self._colorize_partial(expected_model, applied, {'kind': 'texture_preparation'},
                        [{'kind': 'unprocessed_scope', 'target': target, 'group_id': group_id,
                          'material_ids': material_ids, 'layer_ids': layer_ids}], error)
            work = []
            if target in ('global', 'both'):
                try:
                    work = await self._colorize_globals(expected_model, group_id, scoped)
                except Exception as error:
                    if not applied and not self.uncertain:
                        raise
                    return self._colorize_partial(expected_model, applied, {'kind': 'global_preparation'},
                        [{'kind': 'unprocessed_scope', 'target': target, 'group_id': group_id,
                          'material_ids': material_ids, 'layer_ids': layer_ids}], error)
            work.extend(raster_work)
            for index, item in enumerate(work):
                try:
                    if item['kind'] == 'material':
                        receipt = await self._hair_color(expected_model, item['material_id'], item['key'], color)
                    elif item['kind'] == 'garment':
                        row = item['row']
                        receipt = await self._texture_write('set_group_parameters', expected_model, group_id=group_id,
                            changes=[{'id': row['id'], 'type': 'color', 'units': row['units'], 'value': color}])
                        fresh = await self._texture_read('list_group_parameters', expected_model, group_id=group_id, kind='color')
                        values = [r['value'] for r in fresh['parameters'] if r['id'] == row['id']]
                        if receipt.get('ok') is not True or len(values) != 1 or any(abs(a-b) > 1e-5 for a, b in zip(values[0], color)):
                            self.uncertain = True
                            raise RuntimeError('GARMENT_COLOR_READBACK_MISMATCH')
                        receipt['readback_verified'] = True
                    else:
                        row = item['row']
                        receipt = await self._replace_raster(expected_model, item['region_id'],
                            json.dumps(row['image'], separators=(',', ':')), row['layer_id'], item['data'], item['snapshot'])
                    applied.append({'kind': item['kind'], 'receipt': receipt})
                except Exception as error:
                    return self._colorize_partial(expected_model, applied, self._color_target(item),
                        [self._color_target(w) for w in work[index+1:]], error)
            return {'model_token': expected_model, 'ok': True, 'partial': False, 'applied': applied,
                    'remaining': [], 'automatic_rollback': False, 'visible_change_verified': False}

    async def _colorize_globals(self, expected_model, group_id, scoped):
        work, seen = [], set()
        for material in scoped:
            for channel in material['colors']:
                if channel['binding_id'] not in seen:
                    seen.add(channel['binding_id'])
                    work.append({'kind': 'material', 'material_id': material['id'], 'key': channel['key']})
        if not scoped:
            params = await self._texture_read('list_group_parameters', expected_model, group_id=group_id, kind='color')
            if any(error.get('source') == 'GetClothingQuery' for error in params.get('errors', [])):
                raise ValueError('WORN_COLOR_DISCOVERY_INCOMPLETE')
            for row in params['parameters']:
                if row.get('source') != 'worn_color_query' or not row.get('editable'):
                    continue
                binding = tuple(row['binding_keys'])
                if binding not in seen:
                    seen.add(binding)
                    work.append({'kind': 'garment', 'row': row})
        return work

    async def _colorize_rasters(self, expected_model, group_id, scoped, layer_ids, color, mode, strength, applied):
        # A conversion is a separate, reported native history step. Refresh every
        # mapping afterwards; no preset-era node IDs are reused for a write.
        for material in scoped or [None]:
            regions = list(dict.fromkeys(t['region_id'] for t in material['textures'])) if material else [group_id]
            current = [await self._texture_read('list_texture_layers', expected_model, region_id=region)
                       for region in regions]
            if not current or not any(result['layers'] for result in current):
                receipt = await self._begin_texture_edit(expected_model,
                    material_id=material['id'] if material else None,
                    group_id=group_id if material is None else None)
                applied.append({'kind': 'conversion', 'receipt': receipt})
        fresh = await self._texture_read('inspect_hair_materials', expected_model)
        selected = [m for m in fresh['materials'] if m['id'] in {m['id'] for m in scoped}
                    and group_id in m['group_ids']]
        if scoped and len(selected) != len(scoped):
            raise ValueError('Active material scope changed during conversion')
        regions = list(dict.fromkeys(t['region_id'] for m in selected for t in m['textures'])) if scoped else [group_id]
        work, seen = [], set()
        for region in regions:
            listed = await self._texture_read('list_texture_layers', expected_model, region_id=region)
            for row in listed['layers']:
                if row['layer_id'] not in seen:
                    seen.add(row['layer_id'])
                    work.append({'kind': 'raster', 'region_id': region, 'row': row})
        if layer_ids is not None:
            if not set(layer_ids) <= seen:
                raise ValueError('Layer filter is outside selected images')
            work = [w for w in work if w['row']['layer_id'] in layer_ids]
        if not work:
            raise ValueError('No fresh editable raster targets')
        for item in work:
            row = item['row']
            exported = await self._texture_read('export_texture_layer', expected_model,
                region_id=item['region_id'], layer_id=row['layer_id'])
            source = base64.b64decode(exported['base64'], validate=True)
            item['snapshot'] = await self._raster_snapshot(expected_model, item['region_id'],
                json.dumps(row['image'], separators=(',', ':')), row['layer_id'], digest(source), state_digest(row))
            item['data'] = recolor_png(source, color, mode, strength)
        return work

    def _colorize_partial(self, expected_model, applied, failed, remaining, error):
        return {'model_token': expected_model, 'ok': False, 'partial': bool(applied) or self.uncertain,
            'applied': applied, 'failed_target': failed, 'remaining': remaining, 'error': str(error),
            'uncertain': self.uncertain, 'automatic_rollback': False, 'visible_change_verified': False}

    @staticmethod
    def _color_target(item):
        return {k: v for k, v in item.items() if k not in ('snapshot', 'data', 'row')} | (
            {'layer_id': item['row']['layer_id']} if item['kind'] == 'raster' else
            {'parameter_id': item['row']['id'], 'group_id': item['row']['group_id']}
            if item['kind'] == 'garment' else {})
