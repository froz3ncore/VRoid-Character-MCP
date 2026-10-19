"""Real MCP selection and native walking/sitting capture on the saved final assembly."""
import asyncio,json,hashlib,shutil
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'projects/whale-maid/target-fit-v03/final-wear';native.OUT=OUT
async def main():
    source=json.loads((OUT/'refined-wear-acceptance.json').read_text(encoding='utf8'))['save']
    base=json.loads((ROOT/'projects/whale-maid/clean-wear-v01/clean-base-acceptance.json').read_text(encoding='utf8'))['save']['path']
    async with native.client_for(Path(base),'named-motion') as (client,call):
        catalog=await client.list_tools();assert {'list_wear_preview_clips','select_wear_preview_clip'}<={t.name for t in catalog.tools}
        status=await call('get_wear_status');status=await call('open_wear_project',{'filename':Path(source['path']).name,'expected_wear':status['wear_token'],'discard_unsaved':True})
        token=status['wear_token'];await call('set_wear_animation',{'expected_wear':token,'playing':True})
        await call('set_wear_animation',{'expected_wear':token,'playing':False})
        listed=await call('list_wear_preview_clips',{'expected_wear':token})
        (OUT/'native-clip-catalog.json').write_text(json.dumps(listed,ensure_ascii=False,indent=2),encoding='utf8')
        results=[]
        try:
            for label,names in [('walk',['WALK00_F','walk_00']),('sit',['shot_sitting'])]:
                clip=next((c for name in names for c in listed['clips'] if c['name']==name),None)
                assert clip,('Native clip unavailable',label,len(listed['clips']))
                await call('select_wear_preview_clip',{'expected_wear':token,'clip_id':'0x123'},True)
                await call('select_wear_preview_clip',{'expected_wear':'stale','clip_id':clip['id']},True)
                chosen=await call('select_wear_preview_clip',{'expected_wear':token,'clip_id':clip['id']})
                assert chosen['selected_preview_clip']['id']==clip['id']
                again=await call('select_wear_preview_clip',{'expected_wear':token,'clip_id':clip['id']})
                assert again['selected_preview_clip']==chosen['selected_preview_clip']
                await call('set_wear_animation',{'expected_wear':token,'playing':True})
                try:
                    await call('select_wear_preview_clip',{'expected_wear':token,'clip_id':clip['id']},True)
                    captured=await call('capture_wear_motion',{'expected_wear':token,'samples':8,'interval_seconds':.15,'view':'side','size':768})
                    folder=OUT/('native-'+label);assert not folder.exists();folder.mkdir()
                    for i,sample in enumerate(captured['images']):shutil.copy2(sample['path'],folder/('frame-%02d.png'%i))
                    shutil.copy2(captured['manifest_path'],folder/'motion.json')
                    results.append({'case':label,'selected':chosen['selected_preview_clip'],'duration':clip['duration_seconds'],'motion':captured['summary']})
                finally:await call('set_wear_animation',{'expected_wear':token,'playing':False})
            restored=await call('select_wear_preview_clip',{'expected_wear':token,'clip_id':None})
            assert restored['selected_preview_clip'] is None
            final=await call('capture_wear_review',{'expected_wear':token,'views':['back'],'size':768})
        finally:
            status=await call('get_wear_status')
            if status['animation_playing']:await call('set_wear_animation',{'expected_wear':token,'playing':False})
            if status['selected_preview_clip'] is not None:await call('select_wear_preview_clip',{'expected_wear':token,'clip_id':None})
    assert hashlib.sha256(Path(source['path']).read_bytes()).hexdigest()==source['sha256']
    result={'mcp_passed':True,'tools':len(catalog.tools),'available_native_clips':len(listed['clips']),'cases':results,
        'restored_default':True,'source_unchanged':True,'visual_review_required':True,'scope':'Native clip replacement/capture; visual pose and collision review are separate'}
    (OUT/'named-motion-acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False),flush=True)
if __name__=='__main__':asyncio.run(main())
