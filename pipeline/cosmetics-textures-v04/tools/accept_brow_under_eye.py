"""Native eyebrow/under-eye local painting; isolated candidate, undo/redo, cold reopen."""
import argparse,asyncio,hashlib,json,shutil,sys,uuid
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'VRoid-MCP'))
from vroid_mcp.bounded_paint import decode_rgba_png
OUT=ROOT/'projects/whale-maid/diagnostics/brow-under-eye-native-v01'
native.PROJECT=ROOT/'VRoid-MCP';native.LAB=ROOT/'lab-clothing-fit-v17'
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(name,data):
 with (OUT/(name+'.json')).open('x',encoding='utf8') as f:json.dump(data,f,ensure_ascii=False,indent=2)
async def picture(call,token,label,closure=0.,direction=None):
 result=await call('capture_texture_detail',{'expected_model':token,'target':[0,1.49,.07],'direction':direction or [0,0,1],'radius_m':.105,'size':1024,'eye_closure':closure});write(label,result);shutil.copy2(result['path'],OUT/(label+'.png'));assert result['eye_pose']['restored']
async def texture(call,token,slot,label):
 result=await call('export_renderer_texture',{'expected_model':token,'mesh_name':'Face','material_slot':slot});write(label,result);shutil.copy2(result['path'],OUT/(label+'.png'));return result
async def layer(call,token,rid,lid):return await call('export_texture_layer',{'expected_model':token,'region_id':rid,'layer_id':lid})
def marks_for(part,mask):
 if part=='Eyebrow':
  marks=[];small=min(mask['width'],mask['height'])
  for c in mask['components'][:2]:
   box=c['bbox_top_left'];cx,cy=c['center_canvas'];dx=(box[2]-box[0])*.3/mask['width']
   marks.append({'kind':'stroke','points':[[cx-dx,cy],[cx,cy],[cx+dx,cy]],'radius':min(.22,(box[3]-box[1])*.9/small),'aspect':1.2,'color':[.20,.15,.27,.75],'hardness':.15})
  return marks
 marks=[]
 for eye in mask['localization']['eyes']:
  marks.extend([
   {'kind':'stroke','points':eye['shadow_guide_canvas'],'radius':.006,'hardness':0,'color':[.55,.32,.36,.095]},
   {'kind':'stroke','points':eye['highlight_guide_canvas'],'radius':.006,'hardness':0,'color':[1.,.91,.86,.16]}])
 return marks
async def main():
 OUT.mkdir(exist_ok=False);native.OUT=OUT;source=read(ROOT/'projects/whale-maid/cosmetics-texture-tools-v03/evidence/saved.json');assert digest(source['path'])==source['sha256'];results=[]
 async with native.client_for(Path(source['path']),'edit') as (client,call):
  token=(await call('list_face_params'))['model_token'];catalog=await client.list_tools();write('catalog',{'count':len(catalog.tools),'mask_schema':next(t.inputSchema for t in catalog.tools if t.name=='export_makeup_region_mask')})
  bindings=await call('inspect_texture_renderers',{'expected_model':token});write('bindings',bindings);face=next(r for r in bindings['renderers'] if r['name']=='Face')
  skin=next(m['slot'] for m in face['materials'] if m['name']=='N00_000_00_Face_00_SKIN');brow=next(m['slot'] for m in face['materials'] if m['name']=='N00_000_00_FaceBrow_00_FACE')
  protected={m['slot']:await texture(call,token,m['slot'],'protected-before-'+str(m['slot'])) for m in face['materials'] if m['slot'] not in (skin,brow)}
  await picture(call,token,'before-open');await picture(call,token,'before-closed',1.)
  for part,slot in [('Eyebrow',brow),('FaceSkin',skin)]:
   region=next(r for r in (await call('list_texture_regions',{'expected_model':token}))['regions'] if r['part']==part);rid=region['region_id']
   write(part+'-bake',await call('open_texture_editor',{'expected_model':token,'region_id':rid,'bake_colors':True}));await call('close_texture_editor',{'expected_model':token})
   await texture(call,token,slot,part+'-rendered-before')
   await call('open_texture_editor',{'expected_model':token,'region_id':rid})
   layers=(await call('list_texture_layers',{'expected_model':token,'region_id':rid}))['layers'];write(part+'-original-layers',layers)
   originals={l['Name']:(await layer(call,token,rid,l['layer_id']))['sha256'] for l in layers};write(part+'-original-hashes',originals)
   args={'expected_model':token,'region_id':rid,'layer_id':layers[0]['layer_id'],'area':'under_eye' if part=='FaceSkin' else 'region','padding_px':0}
   mask=await call('export_makeup_region_mask',args);write(part+'-mask',mask);shutil.copy2(mask['mask_path'],OUT/(part+'-mask.png'))
   marks=marks_for(part,mask);write(part+'-marks',marks);brush={'expected_model':token,'mask_id':mask['mask_id'],'expected_mask_sha256':mask['manifest_sha256'],'marks':marks}
   preview=await call('preview_makeup_marks',brush);write(part+'-preview',preview);shutil.copy2(preview['path'],OUT/(part+'-overlay.png'))
   name='MCP_'+('brow_tint' if part=='Eyebrow' else 'under_eye_shadow_highlight')+'_v04'
   painted=await call('paint_makeup_marks',{**brush,'layer_name':name,'opacity':1.});write(part+'-painted',painted)
   output=await layer(call,token,rid,painted['native_import']['layer']['layer_id']);write(part+'-native-layer',output);shutil.copy2(output['path'],OUT/(part+'-native-layer.png'))
   assert decode_rgba_png(Path(output['path']).read_bytes())==decode_rgba_png(Path(preview['path']).read_bytes())
   steps=painted['native_import']['history_command_count'];await call('undo',{'expected_model':token,'steps':steps})
   undone=(await call('list_texture_layers',{'expected_model':token,'region_id':rid}))['layers'];write(part+'-undo-layers',undone);assert len(undone)==len(layers)
   await call('redo',{'expected_model':token,'steps':steps});redone=(await call('list_texture_layers',{'expected_model':token,'region_id':rid}))['layers'];write(part+'-redo-layers',redone);assert len(redone)==len(layers)+1
   for l in redone:
    if l['Name'] in originals:assert (await layer(call,token,rid,l['layer_id']))['sha256']==originals[l['Name']]
   await call('close_texture_editor',{'expected_model':token});await texture(call,token,slot,part+'-rendered-after');await picture(call,token,'after-'+part)
   results.append({'part':part,'area':args['area'],'layer_name':name,'layer_sha256':output['sha256'],'native_rgba_equal':True,'undo_redo_passed':True,'original_layer_hashes':originals,'mask_pixels':mask['pixels'],'painted_pixels':preview['painted_pixels']})
  for slot,record in protected.items():assert (await texture(call,token,slot,'protected-after-'+str(slot)))['sha256']==record['sha256']
  await picture(call,token,'candidate-closed',1.);await picture(call,token,'candidate-left',0.,[-.5,0,1]);await picture(call,token,'candidate-right',0.,[.5,0,1])
  saved=await call('save_as',{'expected_model':token,'filename':'brow-under-eye-'+uuid.uuid4().hex+'.vroid'});write('saved',saved)
 assert digest(source['path'])==source['sha256']
 async with native.client_for(Path(saved['path']),'cold') as (_,call):
  token=(await call('list_face_params'))['model_token'];await picture(call,token,'cold-open');await picture(call,token,'cold-closed',1.)
  for item in results:
   part=item['part'];region=next(r for r in (await call('list_texture_regions',{'expected_model':token}))['regions'] if r['part']==part);rid=region['region_id'];layers=(await call('list_texture_layers',{'expected_model':token,'region_id':rid}))['layers'];write(part+'-cold-layers',layers)
   for l in layers:
    result=await layer(call,token,rid,l['layer_id'])
    if l['Name']==item['layer_name']:assert result['sha256']==item['layer_sha256'];write(part+'-cold-layer',result)
    if l['Name'] in item['original_layer_hashes']:assert result['sha256']==item['original_layer_hashes'][l['Name']]
   old=read(OUT/(part+'-mask.json'));await call('preview_makeup_marks',{'expected_model':token,'mask_id':old['mask_id'],'expected_mask_sha256':old['manifest_sha256'],'marks':read(OUT/(part+'-marks.json'))},error=True)
  await texture(call,token,skin,'FaceSkin-cold-rendered');await texture(call,token,brow,'Eyebrow-cold-rendered')
 assert digest(source['path'])==source['sha256'];assert digest(saved['path'])==saved['sha256'];shutil.copy2(saved['path'],OUT/'brow-under-eye-candidate.vroid')
 write('acceptance',{'passed':True,'source_unchanged':True,'save_reopen_passed':True,'old_masks_rejected_on_reopen':True,'parts':results,'other_face_materials_unchanged':len(protected),'source':source,'saved':saved,'formal_art_applied':False,'visual_review_required':True})
 print('Eyebrow and under-eye native layers, Undo/Redo and cold reopen passed',flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=OUT);a=p.parse_args();OUT=a.out.resolve();asyncio.run(main())
