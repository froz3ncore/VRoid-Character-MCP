"""Native raster-layer history operations guarded by current layer and stack hashes."""
import json
from typing import Annotated

from mcp.types import ToolAnnotations
from pydantic import Field

from .texture_layer_state import describe_layers, metadata, stack_digest, state_digest

Digest = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]


def register_layer_management_tools(ready_tool, runtime, read, edit):
    async def current(expected_model, region_id):
        return await runtime.parameter_call('list_texture_layers',
            {'expected_model': expected_model, 'region_id': region_id})

    def checked_layer(result, layer_id, digest):
        rows = [row for row in result['layers'] if row['layer_id'] == layer_id]
        if len(rows) != 1 or state_digest(rows[0]) != digest:
            raise ValueError('Layer metadata changed or layer is missing; relist before editing')
        return rows[0]

    def image_key(layer):
        return json.dumps(layer['image'], separators=(',', ':'), ensure_ascii=False)

    async def write(operation, payload):
        try:
            result = await runtime.parameter_call(operation, payload, True)
        except Exception as error:
            if any(code in str(error) for code in ('LAYER_EDIT_UNCERTAIN', 'READBACK_MISMATCH')):
                getattr(runtime, 'current', runtime).uncertain = True
            raise
        if 'layer' in result:
            result['layer']['state_sha256'] = state_digest(result['layer'])
        return describe_layers(result)

    @ready_tool(annotations=edit)
    async def rename_texture_layer(expected_model: str, region_id: str, layer_id: str,
                                   expected_state_sha256: Digest,
                                   name: str = Field(min_length=1, max_length=80)) -> dict:
        """Rename one existing raster layer in its matching open canvas.

        Pass its fresh state_sha256. Preserves pixels, order and other layers.
        Native Undo/Redo is supported; an unchanged name creates no command.
        Names must contain visible text and no control characters. Does not save.
        """
        if not name.strip() or any(ord(c) < 32 or ord(c) == 127 for c in name):
            raise ValueError('Layer name must contain text and no control characters')
        result = await current(expected_model, region_id)
        row = checked_layer(result, layer_id, expected_state_sha256)
        return await write('rename_texture_layer', {'expected_model': expected_model,
            'region_id': region_id, 'layer_id': layer_id, 'expected_layer': metadata(row), 'name': name})

    @ready_tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False))
    async def delete_texture_layer(expected_model: str, region_id: str, layer_id: str,
                                   expected_state_sha256: Digest, expected_stack_sha256: Digest) -> dict:
        """Delete one raster layer through native history in its matching open canvas.

        Requires fresh layer and image stack hashes from list_texture_layers.
        Refuses the image's last raster layer. Preserves other layers and order;
        native Undo restores the deleted layer and pixels. Does not save or retry.
        """
        result = await current(expected_model, region_id)
        row = checked_layer(result, layer_id, expected_state_sha256)
        stack = [layer for layer in result['layers'] if image_key(layer) == image_key(row)]
        if stack_digest(stack) != expected_stack_sha256:
            raise ValueError('Layer stack changed; relist before deleting')
        if len(stack) <= 1:
            raise ValueError('Refusing to delete the last raster layer')
        return await write('delete_texture_layer', {'expected_model': expected_model,
            'region_id': region_id, 'layer_id': layer_id, 'expected_layer': metadata(row),
            'expected_stack': [metadata(layer) for layer in stack]})

    @ready_tool(annotations=edit)
    async def reorder_texture_layers(expected_model: str, region_id: str, image_id: str,
                                     expected_stack_sha256: Digest,
                                     layer_ids: list[str] = Field(min_length=1, max_length=256)) -> dict:
        """Set one editable image's full raster-layer order in the matching open canvas.

        Use image_id and stack_sha256 from list_texture_layers.images. Supply
        exactly its current layer_ids in the desired bottom-to-top order;
        omissions, duplicates and layers from another image are refused.
        One native history command; unchanged order is a no-op. Does not save.
        """
        result = await current(expected_model, region_id)
        stack = [layer for layer in result['layers'] if image_key(layer) == image_id]
        if not stack or stack_digest(stack) != expected_stack_sha256:
            raise ValueError('Image is missing or layer stack changed; relist before reordering')
        ids = [layer['layer_id'] for layer in stack]
        if len(ids) != len(layer_ids) or len(set(layer_ids)) != len(layer_ids) or set(ids) != set(layer_ids):
            raise ValueError('Order must be a complete permutation of this image layer_ids')
        return await write('reorder_texture_layers', {'expected_model': expected_model,
            'region_id': region_id, 'image_id': image_id, 'layer_ids': layer_ids,
            'expected_stack': [metadata(layer) for layer in stack]})

    @ready_tool(annotations=edit)
    async def set_texture_layer_blend(expected_model: str, region_id: str, layer_id: str,
                                     expected_state_sha256: Digest,
                                     composition_mode: str = Field(min_length=1, max_length=80)) -> dict:
        """Set one raster layer's native blend mode in its matching open canvas.

        Take an exact id from list_texture_layers.composition_modes and pass a
        fresh layer state hash. Preserves source PNG pixels; composition changes.
        Native Undo/Redo supported; same mode creates no command. Does not save.
        """
        result = await current(expected_model, region_id)
        row = checked_layer(result, layer_id, expected_state_sha256)
        if composition_mode not in {mode['id'] for mode in result.get('composition_modes', [])}:
            raise ValueError('Choose a composition mode from the current native list')
        return await write('set_texture_layer_blend', {'expected_model': expected_model,
            'region_id': region_id, 'layer_id': layer_id, 'expected_layer': metadata(row),
            'composition_mode': composition_mode})
