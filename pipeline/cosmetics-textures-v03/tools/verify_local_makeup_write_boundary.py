"""Final native smoke of post-render reference checks; invisible layer is undone, no save."""
import asyncio,json,hashlib
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'projects/whale-maid/diagnostics/local-makeup-write-boundary-v01';native.PROJECT=ROOT/'VRoid-MCP';native.LAB=ROOT/'lab-clothing-fit-v17';native.OUT=OUT
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def write(name,data):(OUT/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
async def main():
 OUT.mkdir(exist_ok=False);saved=read(ROOT/'projects/whale-maid/diagnostics/local-makeup-native-v02/saved.json')
 async with native.client_for(Path(saved['path']),'final-guard') as (client,call):
  token=(await call('list_face_params'))['model_token'];region=next(r for r in (await call('list_texture_regions',{'expected_model':token}))['regions'] if r['part']=='Cheek');rid=region['region_id']
  await call('open_texture_editor',{'expected_model':token,'region_id':rid,'bake_colors':False});before=await call('list_texture_layers',{'expected_model':token,'region_id':rid})
  source=next(l for l in before['layers'] if l['Name']=='默认图片');mask=await call('export_makeup_region_mask',{'expected_model':token,'region_id':rid,'layer_id':source['layer_id']});write('mask',mask)
  marks=[{'points':[mask['components'][0]['center_canvas']],'radius':.04,'color':[.8,.2,.3,.4]}]
  result=await call('paint_makeup_marks',{'expected_model':token,'mask_id':mask['mask_id'],'expected_mask_sha256':mask['manifest_sha256'],'marks':marks,'layer_name':'MCP_write_boundary_smoke_not_art','opacity':0.});write('painted',result)
  await call('undo',{'expected_model':token,'steps':result['native_import']['history_command_count']});after=await call('list_texture_layers',{'expected_model':token,'region_id':rid});assert before['layers']==after['layers'];write('after-undo',after)
  catalog=await client.list_tools();write('catalog',{'tools':len(catalog.tools),'new_tools':[t.model_dump(mode='json') for t in catalog.tools if t.name in ('export_makeup_region_mask','preview_makeup_marks','paint_makeup_marks','capture_texture_detail')]})
 assert hashlib.sha256(Path(saved['path']).read_bytes()).hexdigest()==saved['sha256'];write('acceptance',{'passed':True,'post_render_reference_check_native_smoke':True,'invisible_test_layer_undone':True,'saved_source_unchanged':True,'model_saved':False})
 print('Final native write-boundary checks and Undo passed',flush=True)
if __name__=='__main__':asyncio.run(main())
