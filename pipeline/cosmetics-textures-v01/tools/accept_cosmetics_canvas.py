"""Open a native cosmetics canvas in an isolated disposable session, never save."""
import argparse,asyncio,json
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'work/cosmetics-canvas-v01'
native.PROJECT=ROOT/'work/cosmetics-mcp-v01';native.LAB=ROOT/'lab-clothing-fit-v17';native.OUT=OUT
def write(name,d):(OUT/(name+'.json')).write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf8')
async def main():
 OUT.mkdir(exist_ok=False);model=Path(json.loads((ROOT/'projects/whale-maid/accessory-refinement-v02/chest-skirt-v17b/isolated-base-record.json').read_text(encoding='utf8'))['save']['path'])
 async with native.client_for(model,'canvas') as (client,call):
  token=(await call('list_face_params'))['model_token'];regions=await call('list_texture_regions',{'expected_model':token});write('before-regions',regions)
  catalog=await client.list_tools();write('tool-catalog',{'tools':len(catalog.tools),'names':[t.name for t in catalog.tools]})
  region=next(r for r in regions['regions'] if r['part']==PART)
  result=await call('open_texture_editor',{'expected_model':token,'region_id':region['region_id']});write('opened',result);await asyncio.sleep(3)
  canvas=await call('inspect_texture_canvas',{'expected_model':token});write('canvas',canvas)
  write('uv-guide',await call('export_texture_guide',{'expected_model':token}))
  write('surface',await call('export_texture_surface',{'expected_model':token}))
  regions=await call('list_texture_regions',{'expected_model':token});write('after-regions',regions)
  for r in regions['regions']:
   if r['part']==PART:
    layers=await call('list_texture_layers',{'expected_model':token,'region_id':r['region_id']});write('cheek-layers',layers)
    for i,l in enumerate(layers['layers']):write('layer-export-'+str(i),await call('export_texture_layer',{'expected_model':token,'region_id':r['region_id'],'layer_id':l['layer_id']}))
 print('Canvas addressed and native layers exported; source not saved',flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path);p.add_argument('--part',default='Cheek');p.add_argument('--server-root',type=Path);a=p.parse_args();PART=a.part
 if a.out:OUT=a.out.resolve();native.OUT=OUT
 if a.server_root:native.PROJECT=a.server_root.resolve()
 asyncio.run(main())
