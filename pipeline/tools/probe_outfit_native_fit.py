"""Bounded unsaved native fit comparison on a previously saved assembly."""
import asyncio,json,hashlib,shutil
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'projects/whale-maid/accessory-refinement-v02/native-fit-probe'
async def main():
    OUT.mkdir(exist_ok=False);native.OUT=OUT
    record=json.loads((OUT.parent/'candidate-b/refined-wear-acceptance.json').read_text(encoding='utf8'))
    saved=record['save'];base=json.loads(Path(record['base_record']).read_text(encoding='utf8'))['save'];rows=[]
    async with native.client_for(Path(base['path']),'fit-probe') as (_,call):
        await asyncio.sleep(5);state=await call('get_wear_status');state=await call('open_wear_project',{'expected_wear':state['wear_token'],'filename':Path(saved['path']).name,'discard_unsaved':True})
        token=state['wear_token'];snap=await call('get_wear_snapshot',{'expected_wear':token});item=snap['items'][0]
        for y,z in [(1.,1.)]:
            changed=await call('set_wear_fit',{'expected_wear':token,'item_id':item['id'],'fit_y':y,'fit_z':z})
            await asyncio.sleep(2)
            shot=await call('capture_wear_review',{'expected_wear':token,'views':['feet_front','feet_right','body_front','body_right'],'quality':'high','size':1024})
            names=[r['name'] for inst in item['instances'] for r in inst['renderers'] if r['name'].startswith(('FIT_T001','FIT_ACCESSORY_Shoe_','FIT_ACCESSORY_WhaleTail_Body'))]
            ref=await call('capture_wear_reference',{'expected_wear':token,'item_id':item['id'],'mesh_names':names})
            shutil.copy2(ref['path'],OUT/'fitted-reference.json')
            rows.append({'fit_y':y,'fit_z':z,'status':changed,'capture':shot,'reference':ref})
    assert hashlib.sha256(Path(saved['path']).read_bytes()).hexdigest()==saved['sha256']
    (OUT/'probe.json').write_text(json.dumps({'saved_source_preserved':True,'saved':False,'cases':rows},ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'probe_completed':True,'out':str(OUT)}),flush=True)
if __name__=='__main__':asyncio.run(main())
