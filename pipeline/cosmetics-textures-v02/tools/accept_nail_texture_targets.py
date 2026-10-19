"""Colored native nail-mask, UV picking and save/reopen validation; never formal art."""
import argparse,asyncio,hashlib,json,shutil,uuid,subprocess
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'projects/whale-maid/diagnostics/nail-targets-native-v01'
native.PROJECT=ROOT/'VRoid-MCP';native.LAB=ROOT/'lab-clothing-fit-v17';native.OUT=OUT
def write(name,d):
 with (OUT/(name+'.json')).open('x',encoding='utf8') as f:json.dump(d,f,ensure_ascii=False,indent=2)
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text(encoding='utf8'))
def camera(mapping,side):
 nails=[n for n in mapping['nails'] if n['side']==side];points=[p['world_center'] for n in nails for p in n['islands']];target=[sum(p[i] for p in points)/len(points) for i in range(3)]
 direction=next(n for n in nails if n['finger']=='index')['islands'][0]['normal'];radius=max(sum((p[i]-target[i])**2 for i in range(3))**.5 for p in points)*1.5
 return {'target':target,'direction':direction,'radius_m':max(.035,radius),'size':1024}
async def capture(call,token,cameras,label):
 for side,params in cameras.items():
  result=await call('capture_texture_detail',{'expected_model':token,**params});write(label+'-'+side,result);shutil.copy2(result['path'],OUT/(label+'-'+side+'.png'))
async def main():
 OUT.mkdir(exist_ok=False);source=load(ROOT/'projects/whale-maid/accessory-refinement-v02/chest-skirt-v17b/isolated-base-record.json')['save'];assert digest(source['path'])==source['sha256']
 async with native.client_for(Path(source['path']),'edit') as (client,call):
  token=(await call('list_face_params'))['model_token'];record=await call('export_nail_uv_map',{'expected_model':token});write('map-export',record);mapping=load(record['path']);shutil.copy2(record['path'],OUT/'nail-map.json')
  if FLIP:
   subprocess.run(['C:/Users/e5654/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe','-c','from PIL import Image;import sys;Image.open(sys.argv[1]).transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(sys.argv[2])',record['diagnostic_overlay']['path'],str(OUT/'flip-control.png')],check=True)
   record['diagnostic_overlay']={'path':str(OUT/'flip-control.png'),'sha256':digest(OUT/'flip-control.png')};write('flip-control',record['diagnostic_overlay'])
  assert record['nail_count']==10 and record['uv_island_count']==20;assert len({m['nail_id'] for m in record['masks']})==10
  cameras={side:camera(mapping,side) for side in ('left','right')};write('cameras',cameras)
  await capture(call,token,cameras,'before')
  reference=load(mapping['reference']['path']);mesh=next(m for m in reference['meshes'] if m['name']=='Hand')
  # Independently test one actual visible distal-cap ray on each hand.
  import sys;sys.path.insert(0,str(ROOT/'VRoid-MCP'))
  from vroid_mcp.texture_mapping import point,cross,sub,unit,add,mul
  picks=[]
  for side in ('left','right'):
   nail=next(n for n in mapping['nails'] if n['side']==side and n['finger']=='index');island=nail['islands'][0]
   triangle=island['triangles'][0];positions=[point(mesh['world_matrix'],mesh['positions'][i]) for i in triangle];target=[sum(p[k] for p in positions)/3 for k in range(3)];normal=unit(cross(sub(positions[1],positions[0]),sub(positions[2],positions[0])))
   result=await call('pick_texture_uv',{'expected_model':token,'mesh_name':'Hand','ray_origin':add(target,mul(normal,.003)),'ray_direction':mul(normal,-1),'max_distance':.02});assert result['hit'];picks.append(result);write('pick-'+side,result)
   assert result['nearest']['texture']['width']==2048 and result['nearest']['material_name']==mapping['material_name']
  regions=await call('list_texture_regions',{'expected_model':token});region=next(r for r in regions['regions'] if r['part']=='BodySkin');write('open',await call('open_texture_editor',{'expected_model':token,'region_id':region['region_id'],'bake_colors':BAKE}))
  region=next(r for r in (await call('list_texture_regions',{'expected_model':token}))['regions'] if r['part']=='BodySkin');rid=region['region_id'];layers=await call('list_texture_layers',{'expected_model':token,'region_id':rid});write('before-layers',layers)
  filename='nail-diagnostic-'+uuid.uuid4().hex+'.png';shutil.copy2(record['diagnostic_overlay']['path'],native.LAB/'saves'/filename)
  imported=await call('import_texture_layer',{'expected_model':token,'region_id':rid,'image_id':json.dumps(layers['layers'][0]['image'],separators=(',',':')),'filename':filename,'layer_name':'MCP_nail_target_diagnostic_NOT_ART','opacity':1.,'expected_png_sha256':record['diagnostic_overlay']['sha256']});write('imported',imported)
  exported=await call('export_texture_layer',{'expected_model':token,'region_id':rid,'layer_id':imported['layer']['layer_id']});write('native-layer-export',exported)
  check=subprocess.run(['C:/Users/e5654/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe','-c',
   'from PIL import Image;import sys,hashlib,json;a=Image.open(sys.argv[1]).convert("RGBA");b=Image.open(sys.argv[2]).convert("RGBA");print(json.dumps({"equal":a.size==b.size and a.tobytes()==b.tobytes(),"input_rgba_sha256":hashlib.sha256(a.tobytes()).hexdigest(),"export_rgba_sha256":hashlib.sha256(b.tobytes()).hexdigest(),"export_colors":len(set(b.get_flattened_data()))}));sys.exit(0 if a.size==b.size and a.tobytes()==b.tobytes() else 1)',record['diagnostic_overlay']['path'],exported['path']],capture_output=True,text=True)
  write('pixel-comparison',json.loads(check.stdout));assert check.returncode==0,check.stdout+check.stderr
  await call('close_texture_editor',{'expected_model':token});await capture(call,token,cameras,'after')
  saved=await call('save_as',{'expected_model':token,'filename':'nail-target-diagnostic-'+uuid.uuid4().hex+'.vroid'});write('saved',saved)
  catalog=await client.list_tools();write('catalog',{'tools':len(catalog.tools),'names':[t.name for t in catalog.tools]})
 assert digest(source['path'])==source['sha256']
 async with native.client_for(Path(saved['path']),'reopen') as (_,call):
  token=(await call('list_face_params'))['model_token'];await capture(call,token,cameras,'cold')
  region=next(r for r in (await call('list_texture_regions',{'expected_model':token}))['regions'] if r['part']=='BodySkin');layers=await call('list_texture_layers',{'expected_model':token,'region_id':region['region_id']});write('cold-layers',layers)
  layer=next(l for l in layers['layers'] if l['Name']=='MCP_nail_target_diagnostic_NOT_ART');assert abs(layer['Opacity']-1)<1e-7
  cold=await call('export_texture_layer',{'expected_model':token,'region_id':region['region_id'],'layer_id':layer['layer_id']});write('cold-layer-export',cold);assert cold['sha256']==exported['sha256']
  fresh=await call('export_nail_uv_map',{'expected_model':token});write('cold-map-export',fresh);assert fresh['nail_count']==10
 assert digest(source['path'])==source['sha256'];shutil.copy2(saved['path'],OUT/'diagnostic-nails-not-production.vroid')
 write('acceptance',{'passed':True,'source_unchanged':True,'native_masks':10,'uv_islands':20,'native_ray_samples':2,'save_reopen_passed':True,'layer_png_hash_cold_matches':True,'saved':saved,'diagnostic_only':True,'formal_appearance_modified':False,'visual_review_required':True})
 print('Ten nail masks, native picking and colored diagnostic save/reopen passed',flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=OUT);p.add_argument('--flip-overlay',action='store_true');p.add_argument('--bake-colors',action='store_true');args=p.parse_args();FLIP=args.flip_overlay;BAKE=args.bake_colors;OUT=args.out.resolve();native.OUT=OUT;asyncio.run(main())
