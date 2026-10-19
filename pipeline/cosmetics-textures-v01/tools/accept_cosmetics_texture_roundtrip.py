"""Native PNG import/readback/save/cold-reopen evidence on an independent test copy."""
import argparse,asyncio,hashlib,json,shutil,uuid
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'projects/whale-maid/diagnostics/cosmetics-texture-roundtrip-v01'
native.PROJECT=ROOT/'work/cosmetics-mcp-v01';native.LAB=ROOT/'lab-clothing-fit-v17';native.OUT=OUT
def write(name,d):
 with (OUT/(name+'.json')).open('x',encoding='utf8') as f:json.dump(d,f,ensure_ascii=False,indent=2)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
async def layers(call,token,region):return await call('list_texture_layers',{'expected_model':token,'region_id':region})
async def exported(call,token,region,layer):return await call('export_texture_layer',{'expected_model':token,'region_id':region,'layer_id':layer})
async def main(a):
 OUT.mkdir(parents=True,exist_ok=False)
 source=json.loads((ROOT/'projects/whale-maid/accessory-refinement-v02/chest-skirt-v17b/isolated-base-record.json').read_text(encoding='utf8'))['save'];model=Path(source['path']);assert sha(model)==source['sha256']
 async with native.client_for(model,'edit') as (_,call):
  token=(await call('list_face_params'))['model_token']
  regions=await call('list_texture_regions',{'expected_model':token});region=next(r for r in regions['regions'] if r['part']==a.part)
  write('before-regions',regions);write('opened',await call('open_texture_editor',{'expected_model':token,'region_id':region['region_id']}));await asyncio.sleep(2)
  write('canvas',await call('inspect_texture_canvas',{'expected_model':token}))
  write('uv-guide',await call('export_texture_guide',{'expected_model':token}))
  region=next(r for r in (await call('list_texture_regions',{'expected_model':token}))['regions'] if r['part']==a.part);rid=region['region_id'];before=await layers(call,token,rid);write('before-layers',before)
  assert before['layers'];original=await exported(call,token,rid,before['layers'][0]['layer_id']);write('original-export',original)
  filename='texture-roundtrip-'+uuid.uuid4().hex+'.png';shutil.copy2(original['path'],native.LAB/'saves'/filename)
  image=json.dumps(before['layers'][0]['image'],separators=(',',':'))
  result=await call('import_texture_layer',{'expected_model':token,'region_id':rid,'image_id':image,'filename':filename,'layer_name':'MCP_roundtrip_test_not_art','opacity':0.,'expected_png_sha256':original['sha256']});write('imported',result)
  layer=result['layer']['layer_id'];new=await exported(call,token,rid,layer);write('imported-export',new)
  assert new['sha256']==original['sha256'],'Native PNG pixels/encoding differ; inspect before saving'
  assert (await exported(call,token,rid,before['layers'][0]['layer_id']))['sha256']==original['sha256']
  if a.exercise_history:
   before_count=len((await layers(call,token,rid))['layers'])
   await call('import_texture_layer',{'expected_model':token,'region_id':rid,'image_id':image,'filename':filename,'layer_name':'Rejected stale input','opacity':0.,'expected_png_sha256':'0'*64},error=True)
   assert len((await layers(call,token,rid))['layers'])==before_count
   await call('list_texture_layers',{'expected_model':'stale-token','region_id':rid},error=True)
   await call('undo',{'expected_model':token,'steps':3});undone=await layers(call,token,rid);assert len(undone['layers'])==len(before['layers']);write('undo-layers',undone)
   await call('redo',{'expected_model':token,'steps':3});redone=await layers(call,token,rid);write('redo-layers',redone)
   layer=next(l['layer_id'] for l in redone['layers'] if l['Name']=='MCP_roundtrip_test_not_art');assert (await exported(call,token,rid,layer))['sha256']==original['sha256']
  await call('close_texture_editor',{'expected_model':token})
  saved=await call('save_as',{'expected_model':token,'filename':'cosmetics-roundtrip-'+uuid.uuid4().hex+'.vroid'});write('saved',saved)
 assert sha(model)==source['sha256'];assert sha(saved['path'])==saved['sha256']
 async with native.client_for(Path(saved['path']),'cold') as (_,call):
  token=(await call('list_face_params'))['model_token'];regions=await call('list_texture_regions',{'expected_model':token});region=next(r for r in regions['regions'] if r['part']==a.part);rid=region['region_id'];cold=await layers(call,token,rid);write('cold-layers',cold)
  found=next(l for l in cold['layers'] if l['Name']=='MCP_roundtrip_test_not_art');assert found['Opacity']==0
  final=await exported(call,token,rid,found['layer_id']);write('cold-export',final);assert final['sha256']==original['sha256']
  capture=await call('capture_review',{'expected_model':token,'views':['face_front','full_front'],'size':1024,'quality':'high','label':'Cosmetics texture pipeline test; invisible roundtrip layer, not art'});write('cold-review',capture)
 target=OUT/'test-copy-not-production.vroid';shutil.copy2(saved['path'],target)
 assert sha(model)==source['sha256'];write('acceptance',{'passed':True,'part':a.part,'source':source,'source_unchanged':True,'native_png_hash_roundtrip':True,'original_layer_preserved':True,'new_layer_opacity':0,'save_reopen_passed':True,'saved':saved,'delivered':str(target),'scope':'Pipeline test only. No actual makeup/nail design, UV semantic painting or formal outfit adoption.'})
 print(json.dumps({'passed':True,'part':a.part,'cold_reopen':True,'native_png_hash':final['sha256']}),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--part',default='Cheek');p.add_argument('--out',type=Path);p.add_argument('--exercise-history',action='store_true');p.add_argument('--server-root',type=Path);a=p.parse_args()
 if a.out:OUT=a.out.resolve();native.OUT=OUT
 if a.server_root:native.PROJECT=a.server_root.resolve()
 asyncio.run(main(a))
