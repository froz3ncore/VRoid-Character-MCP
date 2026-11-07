"""Native cosmetics addressing, raster overlays and guarded layer-state editing."""
import asyncio,json
from pydantic import Field
from .texture_input import read_texture_input
from .texture_targets import register_texture_targets
from .makeup_tools import register_makeup_tools
from .texture_layer_state import describe_layers,register_layer_state_tools
from .texture_layer_management import register_layer_management_tools

def register_texture_tools(ready_tool,runtime,lab,read,edit):
    register_texture_targets(ready_tool,runtime,lab,read)
    register_makeup_tools(ready_tool,runtime,lab,read,edit)
    register_layer_state_tools(ready_tool,runtime,read,edit)
    register_layer_management_tools(ready_tool,runtime,read,edit)
    @ready_tool(annotations=read)
    async def inspect_texture_renderers(expected_model: str) -> dict:
        """Read actual Face/Body/Hand/Foot material slots, texture identities and UV transforms. Identical instance IDs in one sample prove texture sharing."""
        return await runtime.parameter_call('inspect_texture_renderers',{'expected_model':expected_model})

    @ready_tool(annotations=read)
    async def list_texture_regions(expected_model: str) -> dict:
        """List real model groups, texture image bindings and editable images. Native keys identify body/face slots; UV mapping is reported separately."""
        return await runtime.parameter_call('list_texture_regions',{'expected_model':expected_model})

    @ready_tool(annotations=read)
    async def list_texture_layers(expected_model: str, region_id: str) -> dict:
        """List native raster layers, state_sha256 tokens, per-image layer_ids/stack_sha256 and supported composition_modes. Keep returned enumeration order when editing a stack; relist after Undo/Redo, import or reopening. Native folder editing is not exposed."""
        return describe_layers(await runtime.parameter_call('list_texture_layers',{'expected_model':expected_model,'region_id':region_id}))

    @ready_tool(annotations=read)
    async def export_texture_layer(expected_model: str, region_id: str, layer_id: str) -> dict:
        """Export the real native raster layer PNG into this lab's reviews directory."""
        import base64, hashlib, uuid
        result=await runtime.parameter_call('export_texture_layer',{'expected_model':expected_model,'region_id':region_id,'layer_id':layer_id})
        data=base64.b64decode(result.pop('base64'),validate=True)
        folder=lab.resolve()/'reviews'/('texture-'+uuid.uuid4().hex);folder.mkdir(parents=True,exist_ok=False)
        target=folder/'layer.png';target.write_bytes(data)
        result.update(path=str(target),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
        return result

    @ready_tool(annotations=edit)
    async def open_texture_editor(expected_model: str, region_id: str,bake_colors: bool = False) -> dict:
        """Open native texture editing for a listed region. Optional native color baking creates an editable colored base so authored RGB can survive skin recoloring. Does not save; inspect before further edits."""
        return await runtime.parameter_call('open_texture_editor',{'expected_model':expected_model,'region_id':region_id,'bake_colors':bake_colors},True)

    @ready_tool(annotations=read)
    async def inspect_texture_canvas(expected_model: str) -> dict:
        """Read active canvas image paths and their actual referring native texture paths."""
        return await runtime.parameter_call('inspect_texture_canvas',{'expected_model':expected_model})

    @ready_tool(annotations=edit)
    async def import_texture_layer(expected_model: str, region_id: str, image_id: str, filename: str, layer_name: str, opacity: float = Field(default=1,ge=0,le=1), expected_png_sha256: str = Field(min_length=64,max_length=64)) -> dict:
        """Add a PNG from this lab's saves directory above existing layers in the matching open canvas. Preserves existing layers; reports exact history command count including optional moves. Verify pixels, visible color and save/reopen separately."""
        import base64
        data,width,height=read_texture_input(lab,filename,expected_png_sha256,layer_name)
        result=await runtime.parameter_call('import_texture_layer',{'expected_model':expected_model,'region_id':region_id,'image_id':image_id,'png_base64':base64.b64encode(data).decode(),'width':width,'height':height,'layer_name':layer_name,'opacity':opacity},True)
        result['input_sha256']=expected_png_sha256
        return result

    @ready_tool(annotations=read)
    async def inspect_hair_materials(expected_model: str) -> dict:
        """Read active shared hair material channels and exact image regions.

        Base overlay IDs are global and deduplicated. Their exact readback is
        unavailable; aggregate hair colors are never substituted as evidence.
        """
        return await runtime.parameter_call('inspect_hair_materials', {'expected_model':expected_model})

    @ready_tool(annotations=edit)
    async def begin_clothing_edit(expected_model: str, group_id: str) -> dict:
        """Convert an exact active garment to editable native textures through history.

        Waits for native readiness and returns fresh image/layer identities.
        screen_entered=false: conversion does not establish canvas navigation.
        Does not save; native Undo/Redo requires separate supported-build testing.
        """
        return await runtime.begin_clothing_edit(expected_model, group_id)

    @ready_tool(annotations=edit)
    async def begin_hair_edit(expected_model: str, material_id: str) -> dict:
        """Convert one active shared hair material and return fresh exact image regions.

        Shared image ownership comes from native material sections. This does not
        navigate to a canvas; screen_entered=false. Does not save or retry.
        """
        return await runtime.begin_hair_edit(expected_model, material_id)

    @ready_tool(annotations=edit)
    async def replace_texture_layer(expected_model: str, region_id: str, image_id: str,
            layer_id: str, filename: str, expected_png_sha256: str, expected_layer_sha256: str,
            expected_state_sha256: str | None = None) -> dict:
        """Replace an existing raster, preserving name/state/order, with one native history command.

        Requires exact image/layer IDs, input PNG hash and current exported PNG
        hash; optional state token adds caller metadata preconditions. RGBA8 PNG
        dimensions must match. Rechecks actual pixels at native write boundary.
        Returns actual before/after hashes; no canvas navigation or save implied.
        """
        return await runtime.replace_texture_layer(expected_model, region_id, image_id, layer_id,
            filename, expected_png_sha256, expected_layer_sha256, expected_state_sha256)

    @ready_tool(annotations=edit)
    async def recolor_texture_layer(expected_model: str, region_id: str, image_id: str,
            layer_id: str, color: list[float], expected_layer_sha256: str,
            mode: str = 'multiply', strength: float = Field(default=1, ge=0, le=1),
            expected_state_sha256: str | None = None) -> dict:
        """Recolor exact existing raster RGB with source multiply or luminance colorize math.

        Alpha bytes are preserved, including transparent pixels. Strength zero
        preserves input PNG bytes. Uses guarded native replacement/history and
        returns actual readback hashes; visible appearance needs separate review.
        """
        return await runtime.recolor_texture_layer(expected_model, region_id, image_id, layer_id,
            color, mode, strength, expected_layer_sha256, expected_state_sha256)

    @ready_tool(annotations=edit)
    async def set_hair_material_color(expected_model: str, material_id: str, key: str,
                                       color: list[float]) -> dict:
        """Write one discovered exact shared material channel or global base:<id> overlay.

        Ordinary material readback uses its actual section path. Global base IDs
        have unavailable exact readback; known command completion is labelled
        separately from verification. No getter proves visible appearance.
        """
        return await runtime.set_hair_material_color(expected_model, material_id, key, color)

    @ready_tool(annotations=edit)
    async def colorize(expected_model: str, target: str, color: list[float], group_id: str,
            material_ids: list[str] | None = None, layer_ids: list[str] | None = None,
            mode: str = 'multiply', strength: float = Field(default=1, ge=0, le=1)) -> dict:
        """Compose global|texture|both writes within one exact active group.

        Exact optional material/layer filters restrict scope. Shared bindings and
        rasters are deduplicated. Returns individual receipts and stops on native
        uncertainty, with partial results and no synthetic rollback. Both can
        compound tint and baked pixels; rendered color is not verified here.
        """
        return await runtime.colorize(expected_model, target, color, group_id, material_ids,
                                      layer_ids, mode, strength)

    @ready_tool(annotations=edit)
    async def close_texture_editor(expected_model: str) -> dict:
        """Leave native texture editing through its own Exit; does not save the model."""
        return await runtime.parameter_call('close_texture_editor',{'expected_model':expected_model},True)

    @ready_tool(annotations=read)
    async def export_texture_guide(expected_model: str) -> dict:
        """Export the active native UV guide PNG. Open the correct cosmetics region first; does not paint or save the model."""
        import base64,hashlib,uuid
        for _ in range(100):
            result=await runtime.parameter_call('export_texture_guide',{'expected_model':expected_model})
            if not result.get('pending'):break
            await asyncio.sleep(.05)
        else:raise RuntimeError('UV guide still loading; no model write performed')
        data=base64.b64decode(result.pop('base64'),validate=True)
        folder=lab.resolve()/'reviews'/('uv-guide-'+uuid.uuid4().hex);folder.mkdir(parents=True,exist_ok=False)
        target=folder/'uv-guide.png';target.write_bytes(data)
        result.update(path=str(target),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
        return result

    @ready_tool(annotations=read)
    async def export_texture_surface(expected_model: str) -> dict:
        """Export the active canvas mesh, triangles, UVs and native bone identities with exact image addresses. This is not an automatic nail segmentation mask."""
        import hashlib,uuid
        result=await runtime.parameter_call('export_texture_surface',{'expected_model':expected_model})
        folder=lab.resolve()/'reviews'/('texture-surface-'+uuid.uuid4().hex);folder.mkdir(parents=True,exist_ok=False)
        data=json.dumps(result,ensure_ascii=False).encode('utf8');target=folder/'surface.json';target.write_bytes(data)
        return {'model_token':result['model_token'],'current_group_type':result['current_group_type'],'path':str(target),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'mesh_count':len(result['meshes']),'vertices':sum(len(m['positions']) for m in result['meshes']),'scope':result['scope']}

