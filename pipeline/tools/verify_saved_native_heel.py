"""Positive control: retained native heel template after cold editor/wear opens."""
import argparse,asyncio,json,shutil,uuid
from pathlib import Path
import clean_native_clothing as native
from test_native_high_heel_templates import describe,digest,write,ROOT

async def main(a):
 out=a.out.resolve();assert out.is_relative_to(ROOT/'projects/whale-maid') and not out.exists();out.mkdir(parents=True);native.OUT=out
 source=json.loads(a.record.read_text(encoding='utf8'));saved=source['heel_save'];assert digest(saved['path'])==saved['sha256']
 async with native.client_for(Path(saved['path']),'retained-heel-cold') as (_,call):
  token=(await call('list_face_params'))['model_token'];await asyncio.sleep(5)
  ref=await call('capture_body_reference',{'expected_model':token,'label':'retained native heel template, cold reopen'});dest=out/'heel-cold-reference.json';shutil.copy2(ref['path'],dest);cold=describe(json.loads(dest.read_text(encoding='utf8')));write(out/'heel-cold-measurement.json',cold)
  state=await call('get_wear_status');state=await call('open_wear_project',{'expected_wear':state['wear_token'],'filename':Path(saved['path']).name,'discard_unsaved':True})
  package=ROOT/'projects/whale-maid/accessory-refinement-v02/tripo-shoe-repair-v11b/whale_maid_tripo_shoe_repair_v11.xwear';package_hash=digest(package);staged=native.LAB/'saves'/(package.stem+'-'+package_hash[:12]+'.xwear');assert digest(staged)==package_hash
  state=await call('import_xwear',{'expected_wear':state['wear_token'],'filename':staged.name});snap=await call('get_wear_snapshot',{'expected_wear':state['wear_token']});item=snap['items'][0]
  names=[r['name'] for instance in item['instances'] for r in instance['renderers'] if r['name'].startswith('FIT_ACCESSORY_Shoe_')]
  ref=await call('capture_wear_reference',{'expected_wear':state['wear_token'],'item_id':item['id'],'mesh_names':names,'include_base_meshes':True,'base_mesh_names':['Body','Foot']});shutil.copy2(ref['path'],out/'retained-heel-tripo-reference.json')
  save=await call('save_wear_project',{'expected_wear':state['wear_token'],'filename':'retained-native-heel-tripo-'+uuid.uuid4().hex+'.xroid'});write(out/'wear-save.json',save)
 async with native.client_for(Path(saved['path']),'retained-heel-wear-cold') as (_,call):
  await call('list_face_params');state=await call('get_wear_status');state=await call('open_wear_project',{'expected_wear':state['wear_token'],'filename':Path(save['path']).name,'discard_unsaved':True});snap=await call('get_wear_snapshot',{'expected_wear':state['wear_token']});item=snap['items'][0]
  names=[r['name'] for instance in item['instances'] for r in instance['renderers'] if r['name'].startswith('FIT_ACCESSORY_Shoe_')]
  ref=await call('inspect_wear_fit_context',{'expected_wear':state['wear_token'],'item_id':item['id'],'mesh_names':names,'region':'feet','sample_limit':128})
  for src,dst in [(ref['report_path'],'fit.json'),(ref['raw_reference']['path'],'wear-cold-reference.json'),(ref['debug_glb']['path'],'fit.glb')]:shutil.copy2(src,out/dst)
 assert digest(saved['path'])==saved['sha256'] and digest(package)==package_hash
 write(out/'acceptance.json',{'passed':True,'source_unchanged':True,'heel_saved_model':saved,'ordinary_cold':cold,'wear_save':save,'retained_heel_with_tripo_cold':True,'native_shoes_hidden':False,'scope':'Positive control retaining native heel layer. Two shoe layers are visible; this is not appearance or shoe-fit acceptance.'})
 print(json.dumps({'passed':True,'out':str(out),'R_heel_minus_toe_min_mm':cold['sides']['R']['heel_minus_toe_min_mm']}),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--record',type=Path,required=True);p.add_argument('--out',type=Path,required=True);asyncio.run(main(p.parse_args()))
