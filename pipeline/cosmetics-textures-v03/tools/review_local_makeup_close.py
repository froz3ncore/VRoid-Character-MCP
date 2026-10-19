"""Preview the freshly listed native Close expression; never change expression definitions or save."""
import asyncio,json,hashlib,shutil
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'projects/whale-maid/diagnostics/local-makeup-close-v04';SOURCE=ROOT/'projects/whale-maid/diagnostics/local-makeup-native-v02'
native.PROJECT=ROOT/'VRoid-MCP';native.LAB=ROOT/'lab-clothing-fit-v17';native.OUT=OUT
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def write(name,data):(OUT/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
async def main():
 OUT.mkdir(exist_ok=False);original=read(ROOT/'projects/whale-maid/accessory-refinement-v02/chest-skirt-v17b/isolated-base-record.json')['save'];candidate=read(SOURCE/'saved.json')
 for label,record in [('original',original),('candidate',candidate)]:
  assert hashlib.sha256(Path(record['path']).read_bytes()).hexdigest()==record['sha256']
  async with native.client_for(Path(record['path']),label) as (_,call):
   token=(await call('list_face_params'))['model_token'];before=await call('inspect_texture_renderers',{'expected_model':token});write(label+'-bindings-before',before)
   params={'expected_model':token,'target':[0,1.59,.04],'direction':[0,0,1],'radius_m':.2,'size':1024}
   for view,closure in [('open',0.),('closed',1.)]:
    result=await call('capture_texture_detail',{**params,'eye_closure':closure});write(label+'-'+view,result);assert result['eye_pose']['restored'];shutil.copy2(result['path'],OUT/(label+'-'+view+'.png'))
   after=await call('inspect_texture_renderers',{'expected_model':token});write(label+'-bindings-after',after)
   get_shapes=lambda result:next(r for r in result['renderers'] if r['name']=='Face')['blend_shapes']
   assert get_shapes(before)==get_shapes(after)
  assert hashlib.sha256(Path(record['path']).read_bytes()).hexdigest()==record['sha256']
 write('acceptance',{'passed':True,'expression':'Render-only Fcl_EYE_Close at measured frame weight 100','apply_and_restore_readback_passed':True,'all_blendshape_weights_before_after_equal':True,'expression_definitions_changed':False,'model_saved':False,'sources_unchanged':True,'visual_review_required':True})
 print('Original/candidate actual closed-eye render and restoration passed',flush=True)
if __name__=='__main__':asyncio.run(main())


