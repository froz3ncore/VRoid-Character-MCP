"""Read actual eyebrow/face editable geometry and PNGs in the clothing lab only."""
import asyncio,json,hashlib,shutil
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'projects/whale-maid/diagnostics/brow-under-eye-probe-v02'
SOURCE=Path(json.loads((ROOT/'projects/whale-maid/cosmetics-texture-tools-v03/evidence/saved.json').read_text(encoding='utf8'))['path'])
native.PROJECT=ROOT/'VRoid-MCP';native.LAB=ROOT/'lab-clothing-fit-v17';native.OUT=OUT
def write(name,data):(OUT/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
async def main():
 OUT.mkdir(exist_ok=False);sha=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
 async with native.client_for(SOURCE,'probe') as (_,call):
  token=(await call('list_face_params'))['model_token'];regions=await call('list_texture_regions',{'expected_model':token});write('regions',regions)
  write('bindings',await call('inspect_texture_renderers',{'expected_model':token}))
  for part in ('Eyebrow','FaceSkin','Eyelid'):
   region=next(r for r in regions['regions'] if r['part']==part);rid=region['region_id']
   write(part+'-open',await call('open_texture_editor',{'expected_model':token,'region_id':rid,'bake_colors':True}))
   layers=await call('list_texture_layers',{'expected_model':token,'region_id':rid});write(part+'-layers',layers)
   surface=await call('export_texture_surface',{'expected_model':token});write(part+'-surface',surface);shutil.copy2(surface['path'],OUT/(part+'-geometry.json'))
   write(part+'-canvas',await call('inspect_texture_canvas',{'expected_model':token}))
   for i,layer in enumerate(layers['layers']):
    result=await call('export_texture_layer',{'expected_model':token,'region_id':rid,'layer_id':layer['layer_id']});write(part+'-layer-'+str(i),result);shutil.copy2(result['path'],OUT/(part+'-layer-'+str(i)+'.png'))
   await call('close_texture_editor',{'expected_model':token})
  result=await call('capture_texture_detail',{'expected_model':token,'target':[0,1.61,.04],'direction':[0,0,1],'radius_m':.13,'size':1024,'eye_closure':0.});write('before',result);shutil.copy2(result['path'],OUT/'before.png')
 assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==sha
 write('acceptance',{'passed':True,'source_unchanged':True,'model_saved':False,'source_sha256':sha})
 print('Eyebrow, FaceSkin and Eyelid geometry and editable pixels captured',flush=True)
if __name__=='__main__':asyncio.run(main())
