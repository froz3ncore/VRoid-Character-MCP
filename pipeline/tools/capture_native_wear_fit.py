import asyncio,json,shutil,hashlib
from pathlib import Path
from clean_native_clothing import client_for,OUT,LAB,SOURCE
async def main():
    record=json.loads((OUT/'clean-wear-acceptance.json').read_text(encoding='utf8'))
    saved=Path(record['save']['path']);before=hashlib.sha256(saved.read_bytes()).hexdigest()
    async with client_for(LAB/'saves'/SOURCE,'wear-fit-reference') as (client,call):
        catalog=await client.list_tools();assert 'capture_wear_reference' in {t.name for t in catalog.tools}
        status=await call('get_wear_status');status=await call('open_wear_project',{'filename':saved.name,'expected_wear':status['wear_token'],'discard_unsaved':True})
        snap=await call('get_wear_snapshot',{'expected_wear':status['wear_token']})
        item=snap['items'][0];names=[r['name'] for inst in item['instances'] for r in inst['renderers'] if r['name'].startswith(('FIT_T001','FIT_T007','FIT_T008','FIT_T011','FIT_T022'))]
        assert len(names)==5
        await call('capture_wear_reference',{'expected_wear':'stale','item_id':item['id'],'mesh_names':names},True)
        await call('capture_wear_reference',{'expected_wear':status['wear_token'],'item_id':'wrong','mesh_names':names},True)
        captured=await call('capture_wear_reference',{'expected_wear':status['wear_token'],'item_id':item['id'],'mesh_names':names})
        target=OUT/'actual_worn_fit_reference_v02.json'
        assert not target.exists();shutil.copy2(captured['path'],target)
        assert hashlib.sha256(target.read_bytes()).hexdigest()==captured['sha256']
        assert hashlib.sha256(saved.read_bytes()).hexdigest()==before
        result={'passed':True,'tools':len(catalog.tools),'capture':captured,'xroid_unchanged':True,'stale_and_unknown_item_rejected':True}
        (OUT/'wear-fit-reference-acceptance-v02.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps(result),flush=True)
asyncio.run(main())
