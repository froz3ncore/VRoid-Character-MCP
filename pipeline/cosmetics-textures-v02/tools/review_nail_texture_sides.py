"""Read-only reverse-view review of the already-saved nail diagnostic."""
import asyncio,json,shutil,hashlib
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1];SOURCE=ROOT/'projects/whale-maid/diagnostics/nail-targets-native-v05';OUT=ROOT/'projects/whale-maid/diagnostics/nail-target-sides-v02'
native.PROJECT=ROOT/'VRoid-MCP';native.LAB=ROOT/'lab-clothing-fit-v17';native.OUT=OUT
def read(p):return json.loads(p.read_text(encoding='utf8'))
def write(name,data):(OUT/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
async def main():
 OUT.mkdir(exist_ok=False);saved=read(SOURCE/'saved.json');assert hashlib.sha256(Path(saved['path']).read_bytes()).hexdigest()==saved['sha256']
 async with native.client_for(Path(saved['path']),'review') as (_,call):
  token=(await call('list_face_params'))['model_token'];write('bindings',await call('inspect_texture_renderers',{'expected_model':token}))
  for mesh in ('Hand','Foot'):write('rendered-'+mesh,await call('export_renderer_texture',{'expected_model':token,'mesh_name':mesh,'material_slot':0}))
  for side,params in read(SOURCE/'cameras.json').items():
   for view,direction in [('reverse',[-v for v in params['direction']]),('front',[0,0,-1]),('back',[0,0,1])]:
    result=await call('capture_texture_detail',{'expected_model':token,**params,'direction':direction});write(side+'-'+view,result);shutil.copy2(result['path'],OUT/(side+'-'+view+'.png'))
  regions=await call('list_texture_regions',{'expected_model':token});region=next(r for r in regions['regions'] if r['part']=='BodySkin');write('open',await call('open_texture_editor',{'expected_model':token,'region_id':region['region_id']}));write('canvas',await call('inspect_texture_canvas',{'expected_model':token}))
  layers=await call('list_texture_layers',{'expected_model':token,'region_id':region['region_id']});write('layers',layers)
  for i,layer in enumerate(layers['layers']):write('layer-'+str(i),await call('export_texture_layer',{'expected_model':token,'region_id':region['region_id'],'layer_id':layer['layer_id']}))
 assert hashlib.sha256(Path(saved['path']).read_bytes()).hexdigest()==saved['sha256']
 print('Read-only alternate hand views and actual layers exported',flush=True)
if __name__=='__main__':asyncio.run(main())
