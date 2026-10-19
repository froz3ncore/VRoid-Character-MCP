"""Native renderer-aware UV and nail targeting. Diagnostic masks are not final art."""
import base64,hashlib,json,math,uuid
from pathlib import Path
from typing import Literal
from pydantic import Field
from .texture_mapping import discover_nails,raster_nails,png_rgba,pick_uv,vector3,unit

def register_texture_targets(ready_tool,runtime,lab,read):
    @ready_tool(annotations=read)
    async def export_renderer_texture(expected_model: str,mesh_name: Literal['Face','Body','Hand','Foot'],material_slot: int = Field(default=0,ge=0,le=15)) -> dict:
        """Export the actual rendered main texture. Generated atlas UV coordinates may differ from editable canvas UV; do not infer an editing address from shared material identity alone."""
        result=await runtime.parameter_call('export_renderer_texture',{'expected_model':expected_model,'mesh_name':mesh_name,'material_slot':material_slot})
        data=base64.b64decode(result.pop('base64'),validate=True);folder=lab.resolve()/'reviews'/('renderer-texture-'+uuid.uuid4().hex);folder.mkdir(parents=True,exist_ok=False)
        target=folder/'texture.png';target.write_bytes(data);result.update(path=str(target),sha256=hashlib.sha256(data).hexdigest());return result

    async def geometry(expected_model):
        record=await runtime.capture_body_reference(expected_model,'Texture targeting current native geometry')
        reference=json.loads(Path(record['path']).read_text(encoding='utf8'))
        bindings=await runtime.parameter_call('inspect_texture_renderers',{'expected_model':expected_model})
        return record,reference,bindings

    @ready_tool(annotations=read)
    async def pick_texture_uv(expected_model: str,mesh_name: Literal['Face','Body','Hand','Foot'],ray_origin: list[float],ray_direction: list[float],max_distance: float = Field(default=5,gt=0,le=20)) -> dict:
        """Ray-pick current baked renderer geometry, returning exact triangle, barycentric UV, material/texture slot and top-left pixel coordinates. Coincident hits are reported separately."""
        origin=vector3(ray_origin);direction=unit(vector3(ray_direction))
        if not math.isfinite(max_distance):raise ValueError('Finite distance is required')
        record,reference,bindings=await geometry(expected_model)
        result=pick_uv(reference,bindings,mesh_name,origin,direction,max_distance);result['reference']=record
        return result

    @ready_tool(annotations=read)
    async def export_nail_uv_map(expected_model: str) -> dict:
        """Discover ten paired distal-bone nail caps from actual Hand geometry; export 10 per-finger masks plus a colored diagnostic overlay. Ambiguous topology or UV sharing is rejected. Visual verification is required."""
        record,reference,bindings=await geometry(expected_model);mapping=discover_nails(reference,bindings);masks=raster_nails(mapping)
        folder=lab.resolve()/'reviews'/('nail-map-'+uuid.uuid4().hex);folder.mkdir(parents=True,exist_ok=False)
        width=mapping['texture']['width'];height=mapping['texture']['height'];diagnostic=bytearray(width*height*4);files=[]
        colors=[(235,80,110,255),(50,160,245,255),(255,170,40,255),(90,190,115,255),(155,100,235,255),
                (245,125,80,255),(50,205,205,255),(220,120,220,255),(170,190,65,255),(90,125,245,255)]
        for number,(name,pixels) in enumerate(masks.items()):
            data=bytearray(width*height*4);color=bytes(colors[number])
            for i in pixels:data[4*i:4*i+4]=b'\xff\xff\xff\xff';diagnostic[4*i:4*i+4]=color
            raw=png_rgba(width,height,data);target=folder/(name+'-mask.png');target.write_bytes(raw)
            files.append({'nail_id':name,'path':str(target),'sha256':hashlib.sha256(raw).hexdigest(),'pixels':len(pixels),'diagnostic_color_rgba':colors[number]})
        raw=png_rgba(width,height,diagnostic);target=folder/'diagnostic-overlay.png';target.write_bytes(raw)
        mapping.update(reference=record,masks=files,diagnostic_overlay={'path':str(target),'sha256':hashlib.sha256(raw).hexdigest()},input_source_unchanged=True)
        data=json.dumps(mapping,ensure_ascii=False,indent=2).encode('utf8');target=folder/'nail-map.json';target.write_bytes(data)
        return {'model_token':expected_model,'path':str(target),'sha256':hashlib.sha256(data).hexdigest(),'nail_count':10,'uv_island_count':20,'texture':mapping['texture'],'geometry_sha256':mapping['geometry_sha256'],'masks':files,'diagnostic_overlay':mapping['diagnostic_overlay'],'status':mapping['status'],'scope':mapping['scope']}

    @ready_tool(annotations=read)
    async def capture_texture_detail(expected_model: str,target: list[float],direction: list[float],radius_m: float = Field(default=.05,ge=.005,le=.3),size: int = Field(default=768,ge=256,le=1024),eye_closure: float | None = Field(default=None,ge=0,le=1)) -> dict:
        """Render a fixed native closeup at measured world coordinates. Optional eye_closure uses verified native close shapes only during Render and restores original weights with readback. Camera resources are released; no expression definitions, textures or saved model are changed."""
        target=vector3(target);direction=unit(vector3(direction))
        if any(abs(v)>20 for v in target):raise ValueError('Target lies outside validated model bounds')
        result=await runtime.parameter_call('capture_texture_detail',{'expected_model':expected_model,'target':target,'direction':direction,'radius_m':radius_m,'size':size,'eye_closure':eye_closure})
        data=base64.b64decode(result.pop('base64'),validate=True);folder=lab.resolve()/'reviews'/('texture-detail-'+uuid.uuid4().hex);folder.mkdir(parents=True,exist_ok=False)
        target=folder/'detail.png';target.write_bytes(data);result.update(path=str(target),sha256=hashlib.sha256(data).hexdigest())
        return result
