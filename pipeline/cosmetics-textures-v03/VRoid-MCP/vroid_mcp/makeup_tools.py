"""Measured regional masks, bounded raster brush previews and native new-layer painting."""
import base64,hashlib,json,math,re,uuid
from pathlib import Path
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator
from .bounded_paint import decode_rgba_png,alpha_mask,describe_mask,validate_marks,render_marks
from .texture_mapping import png_rgba,raster_nails
from .texture_input import read_texture_input

class CanvasMark(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind: Literal['stamp','stroke']='stamp'
    points: list[tuple[float,float]]=Field(min_length=1,max_length=128,description='Normalized canvas x/y in 0..1, origin top-left; stamp: one point, stroke: at least two.')
    radius: float=Field(default=.025,ge=.002,le=.25,description='Brush minor radius as a fraction of the shorter image side.')
    aspect: float=Field(default=1,ge=.25,le=4,description='Major/minor radius ratio before rotation.')
    rotation_deg: float=Field(default=0,ge=-180,le=180)
    hardness: float=Field(default=0,ge=0,le=1,description='0: fully feathered; 1: hard edge with pixel antialiasing.')
    color: tuple[float,float,float,float]
    mirror_x: bool=Field(default=False,description='Reflect points and brush rotation about the canvas center; does not infer anatomical left/right.')

    @model_validator(mode='before')
    @classmethod
    def validate_raw(cls,value):
        if not isinstance(value,dict):raise ValueError('A mark must be a structured object')
        validate_marks([value]);return value

def digest(data):return hashlib.sha256(data).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode('utf8')
def geometry_digest(surface):return digest(canonical([{'image':m['image'],'uv0':m['uv0'],'submeshes':m['submeshes']} for m in surface['meshes']]))

def load_mask(lab,mask_id,expected_sha,expected_model):
    if not re.fullmatch(r'[a-f0-9]{32}',mask_id):raise ValueError('Use a freshly exported makeup mask ID')
    folder=lab.resolve()/'reviews'/('makeup-mask-'+mask_id);path=folder/'manifest.json';png=folder/'mask.png'
    for p in (folder,path,png):
        if p.is_symlink() or p.resolve()!=p:raise ValueError('Mask artifacts must remain inside their original lab directory')
    data=path.read_bytes()
    if digest(data)!=expected_sha:raise ValueError('Makeup mask manifest changed')
    manifest=json.loads(data)
    if manifest['model_token']!=expected_model:raise ValueError('Stale makeup mask model identity; export a new mask')
    data=png.read_bytes()
    if digest(data)!=manifest['mask_png_sha256']:raise ValueError('Makeup mask pixels changed')
    width,height,rgba=decode_rgba_png(data)
    if (width,height)!=(manifest['width'],manifest['height']):raise ValueError('Mask dimensions changed')
    return manifest,bytes(rgba[3::4])

def register_makeup_tools(ready_tool,runtime,lab,read,edit):
    async def layer_png(expected_model,region_id,layer_id):
        result=await runtime.parameter_call('export_texture_layer',{'expected_model':expected_model,'region_id':region_id,'layer_id':layer_id})
        data=base64.b64decode(result.pop('base64'),validate=True);return result,data

    async def current_canvas(expected_model,region_id):
        regions=await runtime.parameter_call('list_texture_regions',{'expected_model':expected_model})
        matches=[r for r in regions['regions'] if r['region_id']==region_id]
        if len(matches)!=1:raise ValueError('Texture region no longer exists')
        region=matches[0];canvas=await runtime.parameter_call('inspect_texture_canvas',{'expected_model':expected_model})
        if canvas['current_group_type']!=region['native_type']:raise ValueError('Open the matching native texture canvas first')
        return region,canvas

    @ready_tool(annotations=read)
    async def export_makeup_region_mask(expected_model: str,region_id: str,layer_id: str,alpha_threshold: int = Field(default=1,ge=1,le=255),padding_px: int = Field(default=0,ge=0,le=16)) -> dict:
        """Export a model/image-bound paint mask. Cheek and MouthLine use a reference layer's actual alpha footprint (optional bounded padding); Eyelid uses its actual canvas UV triangles. Mouth is oral interior and is rejected. No painting or saving."""
        region,canvas=await current_canvas(expected_model,region_id)
        if region['part'] not in ('Cheek','MouthLine','Eyelid'):raise ValueError('Supported local regions: Cheek, MouthLine and Eyelid. Mouth means oral interior, not lipstick.')
        result,png=await layer_png(expected_model,region_id,layer_id);width,height,rgba=decode_rgba_png(png);image=result['layer']['image']
        if not any(i['image']==image for i in canvas['images']):raise ValueError('Reference layer does not belong to the active canvas image')
        geometry_hash=None
        if region['part']=='Eyelid':
            if padding_px:raise ValueError('Do not expand an eyelid geometry mask')
            surface=await runtime.parameter_call('export_texture_surface',{'expected_model':expected_model});geometry_hash=geometry_digest(surface)
            meshes=[m for m in surface['meshes'] if m['image']==image]
            if not meshes:raise ValueError('No matching native eyelid overlay mesh')
            triangles=[[m['uv0'][i] for i in sub['triangles'][j:j+3]] for m in meshes for sub in m['submeshes'] for j in range(0,len(sub['triangles']),3)]
            pixels=raster_nails({'texture':{'width':width,'height':height},'nails':[{'id':'eyelid','islands':[{'uv_triangles':triangles}]}]})['eyelid']
            mask=bytearray(width*height)
            for i in pixels:mask[i]=255
            mode='Actual native Eyelid canvas UV-triangle coverage'
        else:mask=alpha_mask(width,height,rgba,alpha_threshold,padding_px);mode='Reference alpha support with bounded circular expansion'
        description=describe_mask(width,height,mask);raw=bytearray(width*height*4)
        for i,a in enumerate(mask):
            if a:raw[4*i:4*i+4]=bytes((255,255,255,a))
        mask_png=png_rgba(width,height,raw);identifier=uuid.uuid4().hex;folder=lab.resolve()/'reviews'/('makeup-mask-'+identifier);folder.mkdir(parents=True,exist_ok=False)
        (folder/'mask.png').write_bytes(mask_png);(folder/'reference-layer.png').write_bytes(png)
        manifest={'schema':'vroid-bounded-makeup-mask-v1','model_token':expected_model,'mask_id':identifier,'region_id':region_id,'native_type':region['native_type'],'part':region['part'],'image':image,'source_layer_id':layer_id,
            'source_png_sha256':digest(png),'mask_png_sha256':digest(mask_png),'width':width,'height':height,'mode':mode,'alpha_threshold':alpha_threshold,'padding_px':padding_px,'uv_geometry_sha256':geometry_hash,**description,
            'scope':'Reference-derived local paint boundary; not an inferred full anatomical lip shape. Preview and native visual verification are required.'}
        data=json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf8');(folder/'manifest.json').write_bytes(data)
        return {**manifest,'manifest_path':str(folder/'manifest.json'),'manifest_sha256':digest(data),'mask_path':str(folder/'mask.png'),'reference_path':str(folder/'reference-layer.png')}

    async def verify_manifest(expected_model,manifest):
        region,canvas=await current_canvas(expected_model,manifest['region_id'])
        if region['native_type']!=manifest['native_type'] or not any(i['image']==manifest['image'] for i in canvas['images']):raise ValueError('Canvas region or image changed')
        _,source=await layer_png(expected_model,manifest['region_id'],manifest['source_layer_id'])
        if digest(source)!=manifest['source_png_sha256']:raise ValueError('Reference layer changed; export a fresh mask')
        if manifest['uv_geometry_sha256']:
            surface=await runtime.parameter_call('export_texture_surface',{'expected_model':expected_model})
            if geometry_digest(surface)!=manifest['uv_geometry_sha256']:raise ValueError('Canvas UV geometry changed')

    async def prepare(expected_model,mask_id,expected_mask_sha256,marks):
        values=[m.model_dump() if isinstance(m,CanvasMark) else m for m in marks];validate_marks(values)
        manifest,mask=load_mask(lab,mask_id,expected_mask_sha256,expected_model);await verify_manifest(expected_model,manifest)
        png,stats=render_marks(manifest['width'],manifest['height'],mask,values);identifier=uuid.uuid4().hex;filename='makeup-overlay-'+identifier+'.png'
        target=lab.resolve()/'saves'/filename;target.write_bytes(png);folder=lab.resolve()/'reviews'/('makeup-overlay-'+identifier);folder.mkdir(parents=True,exist_ok=False)
        (folder/'overlay.png').write_bytes(png)
        result={'model_token':expected_model,'mask_id':mask_id,'part':manifest['part'],'region_id':manifest['region_id'],'image':manifest['image'],'filename':filename,'path':str(target),'preview_path':str(folder/'overlay.png'),'png_sha256':digest(png),'width':manifest['width'],'height':manifest['height'],'marks':values,**stats}
        (folder/'preview.json').write_bytes(canonical(result));return manifest,result

    @ready_tool(annotations=read)
    async def preview_makeup_marks(expected_model: str,mask_id: str,expected_mask_sha256: str = Field(min_length=64,max_length=64),marks: list[CanvasMark] = Field(min_length=1,max_length=32)) -> dict:
        """Render soft/hard elliptical stamps or connected brush strokes to a transparent PNG, strictly clipped to a fresh measured mask. Coordinates are normalized top-left canvas x/y, not Unity UV. Creates review artifacts, no model changes."""
        _,result=await prepare(expected_model,mask_id,expected_mask_sha256,marks);result['model_modified']=False;return result

    @ready_tool(annotations=edit)
    async def paint_makeup_marks(expected_model: str,mask_id: str,expected_mask_sha256: str = Field(min_length=64,max_length=64),marks: list[CanvasMark] = Field(min_length=1,max_length=32),layer_name: str = Field(default='MCP local makeup',min_length=1,max_length=80),opacity: float = Field(default=1,ge=0,le=1)) -> dict:
        """Paint bounded stamps/strokes as a NEW native overlay layer above existing layers. Validates mask/source/model/current canvas before writes. Uses generated raster PNG and native layer history, not simulated mouse drawing. Does not save. Bake colors when opening the region if native recoloring would swallow RGB; verify visible output separately."""
        if not math.isfinite(opacity) or not 0<=opacity<=1 or not 1<=len(layer_name)<=80:raise ValueError('Invalid layer opacity or name')
        manifest,preview=await prepare(expected_model,mask_id,expected_mask_sha256,marks)
        data,width,height=read_texture_input(lab,preview['filename'],preview['png_sha256'],layer_name)
        # Rendering can take longer than a frame. Check the reference again at the write boundary.
        await verify_manifest(expected_model,manifest)
        imported=await runtime.parameter_call('import_texture_layer',{'expected_model':expected_model,'region_id':manifest['region_id'],'image_id':json.dumps(manifest['image'],separators=(',',':')),'png_base64':base64.b64encode(data).decode(),'width':width,'height':height,'layer_name':layer_name,'opacity':opacity},True)
        return {'model_token':expected_model,'preview':preview,'native_import':imported,'saved':False,'history_policy':'Undo the reported native history_command_count to remove this new overlay; color baking is a separate earlier operation.'}
