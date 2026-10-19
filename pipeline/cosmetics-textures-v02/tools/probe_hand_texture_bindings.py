"""Inspect real hand UV/material ownership before implementing nail placement."""
import asyncio,hashlib,json,shutil
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'projects/whale-maid/diagnostics/hand-texture-bindings-v01'
native.PROJECT=ROOT/'VRoid-MCP';native.LAB=ROOT/'lab-clothing-fit-v17';native.OUT=OUT
def write(name,d):
 with (OUT/(name+'.json')).open('x',encoding='utf8') as f:json.dump(d,f,ensure_ascii=False,indent=2)
async def main():
 OUT.mkdir(exist_ok=False);source=json.loads((ROOT/'projects/whale-maid/accessory-refinement-v02/chest-skirt-v17b/isolated-base-record.json').read_text(encoding='utf8'))['save'];model=Path(source['path']);assert hashlib.sha256(model.read_bytes()).hexdigest()==source['sha256']
 async with native.client_for(model,'binding') as (client,call):
  token=(await call('list_face_params'))['model_token'];write('bindings-before',await call('inspect_texture_renderers',{'expected_model':token}))
  ref=await call('capture_body_reference',{'expected_model':token,'label':'Native Hand geometry and UV for cosmetics mapping'});write('reference-record',ref);shutil.copy2(ref['path'],OUT/'body-reference.json')
  regions=await call('list_texture_regions',{'expected_model':token});write('regions-before',regions);region=next(r for r in regions['regions'] if r['part']=='BodySkin')
  write('opened',await call('open_texture_editor',{'expected_model':token,'region_id':region['region_id']}));await asyncio.sleep(2)
  write('canvas',await call('inspect_texture_canvas',{'expected_model':token}));write('bindings-after',await call('inspect_texture_renderers',{'expected_model':token}))
  write('surface',await call('export_texture_surface',{'expected_model':token}));write('uv-guide',await call('export_texture_guide',{'expected_model':token}))
  catalog=await client.list_tools();write('catalog',{'tools':len(catalog.tools),'names':[t.name for t in catalog.tools]})
 assert hashlib.sha256(model.read_bytes()).hexdigest()==source['sha256'];write('acceptance',{'passed':True,'source_unchanged':True,'model_saved':False,'source':source})
 print('Native Hand binding and body geometry captured; original source unchanged',flush=True)
if __name__=='__main__':asyncio.run(main())
