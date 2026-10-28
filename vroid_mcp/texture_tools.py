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
    async def import_texture_layer(expected_model: str, region_id: str, image_id: str, filename: str, layer_name: str, opacity: float = Field(default=1,min=0,max=1), expected_png_sha256: str = Field(min_length=64,max_length=64)) -> dict:
        """Add a PNG from this lab's saves directory above existing layers in the matching open canvas. Preserves existing layers; reports exact history command count including optional moves. Verify pixels, visible color and save/reopen separately."""
        import base64
        data,width,height=read_texture_input(lab,filename,expected_png_sha256,layer_name)
        result=await runtime.parameter_call('import_texture_layer',{'expected_model':expected_model,'region_id':region_id,'image_id':image_id,'png_base64':base64.b64encode(data).decode(),'width':width,'height':height,'layer_name':layer_name,'opacity':opacity},True)
        result['input_sha256']=expected_png_sha256
        return result

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

