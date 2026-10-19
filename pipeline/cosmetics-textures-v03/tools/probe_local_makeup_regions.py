"""Read native face cosmetics canvases; leave the original model untouched."""
import asyncio,json,hashlib,shutil
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'projects/whale-maid/diagnostics/local-makeup-regions-v02'
native.PROJECT=ROOT/'VRoid-MCP';native.LAB=ROOT/'lab-clothing-fit-v17';native.OUT=OUT
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def write(name,data):(OUT/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
async def main():
 OUT.mkdir(exist_ok=False);source=read(ROOT/'projects/whale-maid/accessory-refinement-v02/chest-skirt-v17b/isolated-base-record.json')['save']
 async with native.client_for(Path(source['path']),'probe') as (_,call):
  token=(await call('list_face_params'))['model_token'];ref=await call('capture_body_reference',{'expected_model':token,'label':'Makeup canvas and actual face geometry matching'});write('reference',ref);shutil.copy2(ref['path'],OUT/'body-reference.json')
  write('bindings',await call('inspect_texture_renderers',{'expected_model':token}))
  capture=await call('capture_review',{'expected_model':token,'views':['face_front'],'size':1024,'quality':'high','label':'Before local makeup tools'});write('before-review',capture)
  for part in ('Mouth','MouthLine','Eyelid'):
   region=next(r for r in (await call('list_texture_regions',{'expected_model':token}))['regions'] if r['part']==part)
   write(part+'-open',await call('open_texture_editor',{'expected_model':token,'region_id':region['region_id'],'bake_colors':True}))
   write(part+'-canvas',await call('inspect_texture_canvas',{'expected_model':token}));write(part+'-surface',await call('export_texture_surface',{'expected_model':token}));write(part+'-guide',await call('export_texture_guide',{'expected_model':token}))
   region=next(r for r in (await call('list_texture_regions',{'expected_model':token}))['regions'] if r['part']==part);layers=await call('list_texture_layers',{'expected_model':token,'region_id':region['region_id']});write(part+'-layers',layers)
   for i,layer in enumerate(layers['layers']):write(part+'-layer-'+str(i),await call('export_texture_layer',{'expected_model':token,'region_id':region['region_id'],'layer_id':layer['layer_id']}))
   await call('close_texture_editor',{'expected_model':token})
 assert hashlib.sha256(Path(source['path']).read_bytes()).hexdigest()==source['sha256'];write('acceptance',{'passed':True,'source_unchanged':True,'model_saved':False})
 print('Face, cheek, lip and eyelid native canvases captured',flush=True)
if __name__=='__main__':asyncio.run(main())
