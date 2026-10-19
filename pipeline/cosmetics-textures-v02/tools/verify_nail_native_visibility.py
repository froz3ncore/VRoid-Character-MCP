"""Native ten-finger closeups and independent baked-base control; no model writes."""
import asyncio,json,shutil,hashlib
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1];SOURCE=ROOT/'projects/whale-maid/diagnostics/nail-targets-baked-color-v02';OUT=ROOT/'projects/whale-maid/diagnostics/nail-visibility-v01'
native.PROJECT=ROOT/'VRoid-MCP';native.LAB=ROOT/'lab-clothing-fit-v17';native.OUT=OUT
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def write(name,data):(OUT/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
async def main():
 OUT.mkdir(exist_ok=False);saved=read(SOURCE/'saved.json');base=read(ROOT/'projects/whale-maid/accessory-refinement-v02/chest-skirt-v17b/isolated-base-record.json')['save']
 async with native.client_for(Path(saved['path']),'ten-fingers') as (client,call):
  token=(await call('list_face_params'))['model_token'];write('bindings',await call('inspect_texture_renderers',{'expected_model':token}))
  for mesh in ('Hand','Foot','Body'):write('rendered-'+mesh,await call('export_renderer_texture',{'expected_model':token,'mesh_name':mesh,'material_slot':0}))
  for nail in read(SOURCE/'nail-map.json')['nails']:
   center=[sum(p['world_center'][k] for p in nail['islands'])/2 for k in range(3)]
   result=await call('capture_texture_detail',{'expected_model':token,'target':center,'direction':nail['islands'][0]['normal'],'radius_m':.016,'size':512});write(nail['id'],result);shutil.copy2(result['path'],OUT/(nail['id']+'.png'))
  region=next(r for r in (await call('list_texture_regions',{'expected_model':token}))['regions'] if r['part']=='BodySkin');layers=await call('list_texture_layers',{'expected_model':token,'region_id':region['region_id']});write('layers',layers)
  old=next(l for l in layers['layers'] if l['Name']!='MCP_nail_target_diagnostic_NOT_ART');write('baked-base-with-overlay',await call('export_texture_layer',{'expected_model':token,'region_id':region['region_id'],'layer_id':old['layer_id']}))
  write('catalog',{'tools':len((await client.list_tools()).tools)})
 async with native.client_for(Path(base['path']),'baked-control') as (_,call):
  token=(await call('list_face_params'))['model_token'];region=next(r for r in (await call('list_texture_regions',{'expected_model':token}))['regions'] if r['part']=='BodySkin')
  await call('open_texture_editor',{'expected_model':token,'region_id':region['region_id'],'bake_colors':True})
  region=next(r for r in (await call('list_texture_regions',{'expected_model':token}))['regions'] if r['part']=='BodySkin');layers=await call('list_texture_layers',{'expected_model':token,'region_id':region['region_id']});assert len(layers['layers'])==1
  result=await call('export_texture_layer',{'expected_model':token,'region_id':region['region_id'],'layer_id':layers['layers'][0]['layer_id']});write('baked-base-control',result)
  assert result['sha256']==read(OUT/'baked-base-with-overlay.json')['sha256']
  await call('close_texture_editor',{'expected_model':token});write('rendered-control',await call('export_renderer_texture',{'expected_model':token,'mesh_name':'Hand','material_slot':0}))
 assert digest(saved['path'])==saved['sha256'] and digest(base['path'])==base['sha256']
 write('acceptance',{'passed':True,'original_and_saved_sources_unchanged':True,'ten_native_closeups':10,'existing_baked_layer_unchanged_by_import':True,'read_only_review':True,'formal_art_applied':False})
 print('Ten nail closeups and unchanged baked-base control passed',flush=True)
if __name__=='__main__':asyncio.run(main())
