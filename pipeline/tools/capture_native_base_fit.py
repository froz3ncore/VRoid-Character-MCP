"""Read actual Dress-up Body/Foot skin and skeleton alongside the outfit."""
import asyncio,json,hashlib,shutil
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'projects/whale-maid/accessory-refinement-v02/native-base-fit-reference'
async def main():
    OUT.mkdir(exist_ok=True);assert not (OUT/'reference.json').exists();native.OUT=OUT
    record=json.loads((OUT.parent/'candidate-b/refined-wear-acceptance.json').read_text(encoding='utf8'));saved=record['save'];base=json.loads(Path(record['base_record']).read_text(encoding='utf8'))['save']
    async with native.client_for(Path(base['path']),'base-fit-reference') as (_,call):
        await asyncio.sleep(5);state=await call('get_wear_status');state=await call('open_wear_project',{'expected_wear':state['wear_token'],'filename':Path(saved['path']).name,'discard_unsaved':True})
        token=state['wear_token'];snapshot=await call('get_wear_snapshot',{'expected_wear':token});item=snapshot['items'][0]
        names=[r['name'] for instance in item['instances'] for r in instance['renderers'] if r['name'].startswith(('FIT_T001','FIT_ACCESSORY_Shoe_','FIT_NEW_Bow','FIT_ACCESSORY_WhaleTail_'))]
        ref=await call('capture_wear_reference',{'expected_wear':token,'item_id':item['id'],'mesh_names':names,'include_base_meshes':True})
        shutil.copy2(ref['path'],OUT/'reference.json')
    assert hashlib.sha256(Path(saved['path']).read_bytes()).hexdigest()==saved['sha256']
    (OUT/'acceptance.json').write_text(json.dumps({'source_saved':saved,'source_unchanged':True,'native_reference':ref},ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'completed':True,'base_meshes':ref['base_meshes'],'out':str(OUT)}),flush=True)
if __name__=='__main__':asyncio.run(main())
