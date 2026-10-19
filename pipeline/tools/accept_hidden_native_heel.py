"""Persistent native-shoe-only hiding with untouched Foot and Tripo geometry."""
import argparse,asyncio,json,shutil,uuid,math
from pathlib import Path
import clean_native_clothing as native
from test_native_high_heel_templates import digest,write,ROOT

def compare_geometry(before,after):
    def same(x,y):
        if isinstance(x,list):return isinstance(y,list) and len(x)==len(y) and all(same(a,b) for a,b in zip(x,y))
        if isinstance(x,float):return isinstance(y,(int,float)) and math.isclose(x,y,rel_tol=0.,abs_tol=1e-6)
        return x==y
    for key in ['body','garments','base_meshes']:
        a=before[key];b=after[key]
        if isinstance(a,dict):a=[a];b=[b]
        assert len(a)==len(b)
        for x,y in zip(a,b):
            for field in ['name','positions','triangles','uv0','source_positions','world_matrix']:
                if field in x:assert same(x[field],y[field]),(key,x.get('name'),field)

def verify_artifacts(out):
    """Finalize already captured cold evidence without repeating a native write."""
    edit=json.loads((out/'saved-edit.json').read_text(encoding='utf8'))
    before=json.loads((out/'before.json').read_text(encoding='utf8'));after=json.loads((out/'after.json').read_text(encoding='utf8'));cold=json.loads((out/'cold-reference.json').read_text(encoding='utf8'))
    compare_geometry(before,after);compare_geometry(after,cold)
    state=json.loads((out/'native-shoes-cold.json').read_text(encoding='utf8'));assert not state['visible'] and state['current_triangle_count']==0
    restored=json.loads((out/'restore-test.json').read_text(encoding='utf8'));assert restored['visible'] and restored['current_triangle_count']==1812
    assert not json.loads((out/'idempotence.json').read_text(encoding='utf8'))['changed']
    assert cold['base_body_occlusion']['hidden_vertex_count']==0
    positive=json.loads((ROOT/'projects/whale-maid/accessory-refinement-v02/high-heel-retained-081-v01/acceptance.json').read_text(encoding='utf8'))
    for saved in [edit['save'],positive['heel_saved_model'],positive['wear_save']]:assert digest(saved['path'])==saved['sha256']
    delivered=out/'whale_maid_tripo_native_heel_hidden_shoes_v01.xroid';assert not delivered.exists();shutil.copy2(edit['save']['path'],delivered)
    write(out/'acceptance.json',{'passed':True,'source_unchanged':True,'base_heel_preserved':True,'body_geometry_and_imported_tripo_geometry_unchanged':True,'cold_geometry_comparison_tolerance_m':1e-6,'body_vertices_hidden':0,'native_shoe_triangles_before':1812,'native_shoe_triangles_after':0,'native_shoe_hidden_cold_passed':True,'visibility_restore_and_idempotence_passed':True,'save':edit['save'],'delivered':str(delivered),'startup_base':positive['heel_saved_model'],'native_tools':edit['native_tools'],'evidence_validation':'Existing native saved edit and cold reference validated; no native mutation retried. Original exact float equality was replaced by bounded cold-load tolerance.','scope':'Persistent native shoe appearance removal; high-heel Body and imported Tripo surfaces preserved. Shoe fit/motion/export are separate.'})
    print(json.dumps({'passed':True,'existing_cold_evidence_verified':True,'out':str(out)}),flush=True)

async def main(a):
 out=a.out.resolve();assert out.is_relative_to(ROOT/'projects/whale-maid') and not out.exists();out.mkdir(parents=True);native.OUT=out
 positive=json.loads((ROOT/'projects/whale-maid/accessory-refinement-v02/high-heel-retained-081-v01/acceptance.json').read_text(encoding='utf8'));base=positive['heel_saved_model'];source=positive['wear_save'];assert digest(base['path'])==base['sha256'] and digest(source['path'])==source['sha256']
 async with native.client_for(Path(base['path']),'hide-native-shoes') as (client,call):
  await call('list_face_params');state=await call('get_wear_status');state=await call('open_wear_project',{'expected_wear':state['wear_token'],'filename':Path(source['path']).name,'discard_unsaved':True});token=state['wear_token'];snapshot=await call('get_wear_snapshot',{'expected_wear':token});write(out/'snapshot-before.json',snapshot);item=snapshot['items'][0]
  names=[r['name'] for instance in item['instances'] for r in instance['renderers'] if r['name'].startswith('FIT_ACCESSORY_Shoe_')];assert len(names)==8
  async def capture(label):
   ref=await call('capture_wear_reference',{'expected_wear':token,'item_id':item['id'],'mesh_names':names,'include_base_meshes':True,'base_mesh_names':['Body','Foot']});p=out/(label+'.json');shutil.copy2(ref['path'],p);return json.loads(p.read_text(encoding='utf8'))
  before=await capture('before');state=await call('inspect_wear_native_shoes',{'expected_wear':token});write(out/'native-shoes-before.json',state);assert state['visible']
  result=await call('set_wear_native_shoes_visible',{'expected_wear':token,'expected_visibility_token':state['visibility_token'],'visible':False});write(out/'hide-result.json',result);assert not result['visible'] and result['current_triangle_count']==0
  after=await capture('after');compare_geometry(before,after)
  state=await call('inspect_wear_native_shoes',{'expected_wear':token});write(out/'native-shoes-after.json',state)
  same=await call('set_wear_native_shoes_visible',{'expected_wear':token,'expected_visibility_token':state['visibility_token'],'visible':False});assert not same['changed'];write(out/'idempotence.json',same)
  review=await call('capture_wear_review',{'expected_wear':token,'views':['feet_front','feet_right','feet_back'],'size':1024,'quality':'high'});write(out/'close-ups.json',review)
  save=await call('save_wear_project',{'expected_wear':token,'filename':'tripo-retained-heel-hidden-native-shoes-'+uuid.uuid4().hex+'.xroid'});write(out/'saved-edit.json',{'save':save,'base_record':str(ROOT/'projects/whale-maid/accessory-refinement-v02/high-heel-template-081-v01/measurement.json'),'native_shoe_state':state,'native_tools':len((await client.list_tools()).tools)})
  restored=await call('set_wear_native_shoes_visible',{'expected_wear':token,'expected_visibility_token':state['visibility_token'],'visible':True});assert restored['visible'] and restored['current_triangle_count']==1812;write(out/'restore-test.json',restored)
 async with native.client_for(Path(base['path']),'hidden-native-shoes-cold') as (client,call):
  await call('list_face_params');state=await call('get_wear_status');state=await call('open_wear_project',{'expected_wear':state['wear_token'],'filename':Path(save['path']).name,'discard_unsaved':True});token=state['wear_token'];visibility=await call('inspect_wear_native_shoes',{'expected_wear':token});write(out/'native-shoes-cold.json',visibility);assert not visibility['visible'] and visibility['current_triangle_count']==0
  snapshot=await call('get_wear_snapshot',{'expected_wear':token});write(out/'snapshot-cold.json',snapshot);item=snapshot['items'][0];names=[r['name'] for instance in item['instances'] for r in instance['renderers'] if r['name'].startswith('FIT_ACCESSORY_Shoe_')]
  ref=await call('capture_wear_reference',{'expected_wear':token,'item_id':item['id'],'mesh_names':names,'include_base_meshes':True,'base_mesh_names':['Body','Foot']});shutil.copy2(ref['path'],out/'cold-reference.json');cold=json.loads((out/'cold-reference.json').read_text(encoding='utf8'));compare_geometry(after,cold)
  body=await call('inspect_wear_body_occlusion',{'expected_wear':token});assert body['hidden_vertices']==[];write(out/'body-mask-cold.json',body)
 assert digest(source['path'])==source['sha256'] and digest(base['path'])==base['sha256']
 delivered=out/'whale_maid_tripo_native_heel_hidden_shoes_v01.xroid';shutil.copy2(save['path'],delivered);assert digest(delivered)==save['sha256']
 write(out/'acceptance.json',{'passed':True,'source_unchanged':True,'base_heel_preserved':True,'body_geometry_and_imported_tripo_geometry_unchanged':True,'body_vertices_hidden':0,'native_shoe_triangles_before':1812,'native_shoe_triangles_after':0,'native_shoe_hidden_cold_passed':True,'visibility_restore_and_idempotence_passed':True,'save':save,'delivered':str(delivered),'startup_base':base,'native_tools':57,'scope':'Persistent native shoe appearance removal; high-heel Body and imported Tripo surfaces preserved. Shoe fit/motion/export are separate.'})
 print(json.dumps({'passed':True,'out':str(out),'native_shoe_triangles':0}),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--verify-artifacts-only',action='store_true');a=p.parse_args()
 if a.verify_artifacts_only:verify_artifacts(a.out.resolve())
 else:asyncio.run(main(a))
