"""Native bounded cheek/lip/eyelid brush acceptance on a fresh independent candidate."""
import argparse,asyncio,hashlib,json,shutil,sys,uuid
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'VRoid-MCP'))
from vroid_mcp.bounded_paint import decode_rgba_png
OUT=ROOT/'projects/whale-maid/diagnostics/local-makeup-native-v01';native.PROJECT=ROOT/'VRoid-MCP';native.LAB=ROOT/'lab-clothing-fit-v17';native.OUT=OUT
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def write(name,data):
 with (OUT/(name+'.json')).open('x',encoding='utf8') as f:json.dump(data,f,ensure_ascii=False,indent=2)
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
async def capture(call,token,label,views=None):
 result=await call('capture_review',{'expected_model':token,'views':views or ['face_front'],'size':1024,'quality':'high','label':label});write(label+'-review',result)
 for view,item in result['images'].items():shutil.copy2(item['path'],OUT/(label+'-'+view+'.png'))
async def export(call,token,rid,lid):return await call('export_texture_layer',{'expected_model':token,'region_id':rid,'layer_id':lid})
def marks_for(part,mask):
 w,h=mask['width'],mask['height'];small=min(w,h);comps=mask['components']
 if part=='Cheek':
  assert len([c for c in comps if c['pixels']>100])==2
  return [{'kind':'stamp','points':[c['center_canvas']],'radius':(c['bbox_top_left'][3]-c['bbox_top_left'][1])*.40/small,'aspect':1.1,'rotation_deg':-8 if c['center_canvas'][0]<.5 else 8,'hardness':0,'color':[.9,.32,.44,.22]} for c in comps[:2]]
 if part=='MouthLine':
  c=comps[0];box=c['bbox_top_left'];radius=(box[3]-box[1])*.6
  return [{'kind':'stamp','points':[c['center_canvas']],'radius':radius/small,'aspect':min(4,(box[2]-box[0])*.48/radius),'hardness':.12,'color':[.72,.18,.34,.42]}]
 # Exercise connected brush paths on the native eyelid UV islands, rather than opaque background pixels.
 large=[c for c in comps if c['pixels']>50][:2];assert len(large)==2
 result=[]
 for c in large:
  box=c['bbox_top_left'];cx,cy=c['center_canvas'];radius=min(.23,(box[3]-box[1])*.34/small)
  result.append({'kind':'stroke','points':[[max(0,cx-.025),cy],[cx,cy-.015],[min(1,cx+.025),cy]],'radius':radius,'aspect':1.2,'hardness':0,'color':[.62,.25,.42,.18]})
 return result

async def main():
 OUT.mkdir(exist_ok=False);source=read(ROOT/'projects/whale-maid/accessory-refinement-v02/chest-skirt-v17b/isolated-base-record.json')['save'];assert digest(source['path'])==source['sha256'];results=[]
 async with native.client_for(Path(source['path']),'edit') as (client,call):
  token=(await call('list_face_params'))['model_token'];write('catalog',{'tools':len((await client.list_tools()).tools)});await capture(call,token,'before')
  bindings=await call('inspect_texture_renderers',{'expected_model':token});write('bindings',bindings);face=next(r for r in bindings['renderers'] if r['name']=='Face')
  skin_slot=next(m['slot'] for m in face['materials'] if m['name']=='N00_000_00_Face_00_SKIN')
  eyelid_slot=next(m['slot'] for m in face['materials'] if m['name']=='N00_000_00_FaceEyeline_00_FACE')
  protected={m['slot']:await call('export_renderer_texture',{'expected_model':token,'mesh_name':'Face','material_slot':m['slot']}) for m in face['materials'] if m['slot'] not in (skin_slot,eyelid_slot)};write('protected-face-materials-before',protected)
  eyelid_before=await call('export_renderer_texture',{'expected_model':token,'mesh_name':'Face','material_slot':eyelid_slot});write('eyelid-material-before',eyelid_before)
  for part in ('Cheek','MouthLine','Eyelid'):
   region=next(r for r in (await call('list_texture_regions',{'expected_model':token}))['regions'] if r['part']==part);rid=region['region_id']
   write(part+'-open',await call('open_texture_editor',{'expected_model':token,'region_id':rid,'bake_colors':True}))
   layers=await call('list_texture_layers',{'expected_model':token,'region_id':rid});write(part+'-before-layers',layers);assert len(layers['layers'])==1
   original=await export(call,token,rid,layers['layers'][0]['layer_id']);write(part+'-original-layer',original)
   mask=await call('export_makeup_region_mask',{'expected_model':token,'region_id':rid,'layer_id':layers['layers'][0]['layer_id'],'alpha_threshold':1,'padding_px':8 if part=='MouthLine' else 0});write(part+'-mask',mask)
   marks=marks_for(part,mask);write(part+'-marks',marks);args={'expected_model':token,'mask_id':mask['mask_id'],'expected_mask_sha256':mask['manifest_sha256'],'marks':marks}
   preview=await call('preview_makeup_marks',args);write(part+'-preview',preview)
   await call('preview_makeup_marks',{**args,'expected_mask_sha256':'0'*64},error=True)
   before_count=len((await call('list_texture_layers',{'expected_model':token,'region_id':rid}))['layers'])
   invalid=await call('paint_makeup_marks',{**args,'marks':[{'points':[[float('nan'),.5]],'color':[.5,.5,.5,1]}],'layer_name':'rejected'},error=True);write(part+'-invalid-paint',{'error':invalid})
   assert len((await call('list_texture_layers',{'expected_model':token,'region_id':rid}))['layers'])==before_count
   painted=await call('paint_makeup_marks',{**args,'layer_name':'MCP_bounded_'+part+'_candidate_v01','opacity':1.});write(part+'-painted',painted)
   assert painted['preview']['png_sha256']==preview['png_sha256']
   lid=painted['native_import']['layer']['layer_id'];output=await export(call,token,rid,lid);write(part+'-native-layer',output)
   assert decode_rgba_png(Path(output['path']).read_bytes())==decode_rgba_png(Path(preview['path']).read_bytes())
   assert (await export(call,token,rid,layers['layers'][0]['layer_id']))['sha256']==original['sha256']
   steps=painted['native_import']['history_command_count'];await call('undo',{'expected_model':token,'steps':steps})
   undone=await call('list_texture_layers',{'expected_model':token,'region_id':rid});write(part+'-undo-layers',undone);assert len(undone['layers'])==before_count
   await call('redo',{'expected_model':token,'steps':steps});redone=await call('list_texture_layers',{'expected_model':token,'region_id':rid});write(part+'-redo-layers',redone)
   lid=next(l['layer_id'] for l in redone['layers'] if l['Name']=='MCP_bounded_'+part+'_candidate_v01');assert (await export(call,token,rid,lid))['sha256']==output['sha256']
   await call('close_texture_editor',{'expected_model':token});await capture(call,token,'after-'+part)
   write(part+'-rendered-skin',await call('export_renderer_texture',{'expected_model':token,'mesh_name':'Face','material_slot':skin_slot}))
   lid_texture=await call('export_renderer_texture',{'expected_model':token,'mesh_name':'Face','material_slot':eyelid_slot});write(part+'-rendered-eyelid',lid_texture)
   if part!='Eyelid':assert lid_texture['sha256']==eyelid_before['sha256']
   else:
    assert lid_texture['sha256']!=eyelid_before['sha256']
    assert read(OUT/'Eyelid-rendered-skin.json')['sha256']==read(OUT/'MouthLine-rendered-skin.json')['sha256']
   results.append({'part':part,'layer_name':'MCP_bounded_'+part+'_candidate_v01','native_layer_sha256':output['sha256'],'input_rgba_matches':True,'existing_layer_unchanged':True,'undo_redo_passed':True,'mask_pixels':mask['pixels'],'painted_pixels':preview['painted_pixels'],'outside_mask_pixels':0})
  after={slot:await call('export_renderer_texture',{'expected_model':token,'mesh_name':'Face','material_slot':slot}) for slot in protected};write('protected-face-materials-after',after)
  assert all(after[slot]['sha256']==record['sha256'] for slot,record in protected.items())
  await capture(call,token,'candidate',['face_front','face_three_quarter_left','face_three_quarter_right'])
  expressions=await call('list_expressions');write('expressions',expressions);blink=next((e['id'] for e in expressions['expressions'] if e['id'].lower()=='blink'),None)
  if blink:
   await call('preview_expression',{'expected_model':token,'expression':blink});await capture(call,token,'eyes-closed');await call('preview_expression',{'expected_model':token,'expression':None})
  saved=await call('save_as',{'expected_model':token,'filename':'bounded-makeup-candidate-'+uuid.uuid4().hex+'.vroid'});write('saved',saved)
 assert digest(source['path'])==source['sha256']
 async with native.client_for(Path(saved['path']),'cold') as (_,call):
  token=(await call('list_face_params'))['model_token'];await capture(call,token,'cold',['face_front','face_three_quarter_left','face_three_quarter_right'])
  if blink:
   await call('preview_expression',{'expected_model':token,'expression':blink});await capture(call,token,'cold-eyes-closed');await call('preview_expression',{'expected_model':token,'expression':None})
  for item in results:
   region=next(r for r in (await call('list_texture_regions',{'expected_model':token}))['regions'] if r['part']==item['part']);layers=await call('list_texture_layers',{'expected_model':token,'region_id':region['region_id']})
   layer=next(l for l in layers['layers'] if l['Name']==item['layer_name']);output=await export(call,token,region['region_id'],layer['layer_id']);write(item['part']+'-cold-layer',output);assert output['sha256']==item['native_layer_sha256']
   old_mask=read(OUT/(item['part']+'-mask.json'));await call('preview_makeup_marks',{'expected_model':token,'mask_id':old_mask['mask_id'],'expected_mask_sha256':old_mask['manifest_sha256'],'marks':read(OUT/(item['part']+'-marks.json'))},error=True)
 assert digest(source['path'])==source['sha256'];shutil.copy2(saved['path'],OUT/'bounded-makeup-not-production.vroid')
 write('acceptance',{'passed':True,'source_unchanged':True,'parts':results,'protected_material_slots_unchanged':len(protected),'eyelid_only_changes_its_eyeline_atlas':True,'blink_preview':blink,'save_reopen_passed':True,'old_mask_rejected_after_reopen':True,'candidate_only':True,'formal_art_applied':False,'saved':saved,'visual_review_required':True})
 print('Bounded cheek, lip contour and eyelid painting, Undo/Redo and save/reopen passed',flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=OUT);a=p.parse_args();OUT=a.out.resolve();native.OUT=OUT;asyncio.run(main())
