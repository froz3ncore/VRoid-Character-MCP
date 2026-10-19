"""Import each unique parameter variant once and inspect the same native sitting pose."""
import asyncio,hashlib,json,shutil
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'projects/whale-maid/target-fit-v04/calibration-v02';native.OUT=OUT
async def main():
    variants=json.loads((OUT/'variants.json').read_text(encoding='utf8'))
    base=json.loads((ROOT/'projects/whale-maid/clean-wear-v01/clean-base-acceptance.json').read_text(encoding='utf8'))['save']
    results=[]
    async with native.client_for(Path(base['path']),'spring-calibration') as (_,call):
        for variant in variants['variants']:
            folder=OUT/variant['label'];folder.mkdir(exist_ok=False)
            staged=native.LAB/'saves'/Path(variant['path']).name
            assert not staged.exists();shutil.copy2(variant['path'],staged)
            state=await call('get_wear_status');state=await call('open_wear_project',{'filename':Path(base['path']).name,'expected_wear':state['wear_token'],'discard_unsaved':True})
            state=await call('import_xwear',{'filename':staged.name,'expected_wear':state['wear_token']})
            token=state['wear_token'];snap=await call('get_wear_snapshot',{'expected_wear':token});item=snap['items'][0]
            # Read back real instantiated components before trusting changed inputs.
            joints={b['name']:b['spring_joint'] for b in item['skeletons'][0]['bones'] if b['spring_joint']}
            ring=variant['config']['rings'][0];probe=joints[f'WM_Skirt_{ring:02d}_00']
            assert abs(probe['stiffness']-variant['config']['stiffness'])<1e-5 and abs(probe['gravity_power']-variant['config']['gravity'])<1e-5
            names=[r['name'] for inst in item['instances'] for r in inst['renderers'] if r['name'].startswith('FIT_T001')];assert len(names)==1
            await call('set_wear_animation',{'expected_wear':token,'playing':True});await call('set_wear_animation',{'expected_wear':token,'playing':False})
            clips=(await call('list_wear_preview_clips',{'expected_wear':token}))['clips'];clip=next(c for c in clips if c['name']=='shot_sitting')
            await call('select_wear_preview_clip',{'expected_wear':token,'clip_id':clip['id']});await call('set_wear_animation',{'expected_wear':token,'playing':True})
            try:
                await asyncio.sleep(2)
                captured=await call('capture_wear_reference',{'expected_wear':token,'item_id':item['id'],'mesh_names':names,'preview':True})
                shutil.copy2(captured['path'],folder/'sit-reference.json')
                motion=await call('capture_wear_motion',{'expected_wear':token,'samples':5,'interval_seconds':.2,'view':'side','size':768})
                for i,image in enumerate(motion['images']):shutil.copy2(image['path'],folder/('frame-%02d.png'%i))
                shutil.copy2(motion['manifest_path'],folder/'motion.json')
                results.append({'label':variant['label'],'parameter_readback':probe,'capture':captured,'motion':motion['summary']})
            finally:
                await call('set_wear_animation',{'expected_wear':token,'playing':False});await call('select_wear_preview_clip',{'expected_wear':token,'clip_id':None})
    assert hashlib.sha256(Path(base['path']).read_bytes()).hexdigest()==base['sha256']
    (OUT/'native-calibration.json').write_text(json.dumps({'mcp_passed':True,'base_unchanged':True,'results':results},ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'mcp_passed':True,'variants':[r['label'] for r in results]}),flush=True)
if __name__=='__main__':asyncio.run(main())
