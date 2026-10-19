"""Freeze actual native walking poses and measure/render the rear-skirt contact."""
import asyncio,argparse,hashlib,json,shutil
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1]
async def main(a):
    out=a.out.resolve();assert out.is_relative_to(ROOT/'projects');out.mkdir(parents=True,exist_ok=False);native.OUT=out
    record=json.loads(a.record.read_text(encoding='utf8'));saved=record['save'];source=Path(saved['path'])
    assert hashlib.sha256(source.read_bytes()).hexdigest()==saved['sha256']
    base=json.loads((ROOT/'projects/whale-maid/clean-wear-v01/clean-base-acceptance.json').read_text(encoding='utf8'))['save']['path']
    results=[]
    async with native.client_for(Path(base),'frozen-rear-contact') as (client,call):
        state=await call('get_wear_status');state=await call('open_wear_project',{'filename':source.name,'expected_wear':state['wear_token'],'discard_unsaved':True})
        token=state['wear_token'];snapshot=await call('get_wear_snapshot',{'expected_wear':token});assert len(snapshot['items'])==1
        item=snapshot['items'][0];names=[r['name'] for inst in item['instances'] for r in inst['renderers'] if r['name'].startswith('FIT_T001')];assert len(names)==1
        await call('set_wear_animation',{'expected_wear':token,'playing':True});await call('set_wear_animation',{'expected_wear':token,'playing':False})
        clips=(await call('list_wear_preview_clips',{'expected_wear':token}))['clips'];clip=next(c for c in clips if c['name']=='WALK00_F')
        await call('select_wear_preview_clip',{'expected_wear':token,'clip_id':clip['id']});await call('set_wear_animation',{'expected_wear':token,'playing':True})
        try:
            for index,fraction in enumerate(a.fractions):
                folder=out/('pose-%02d'%index);folder.mkdir()
                freeze=await call('hold_wear_preview_pose',{'expected_wear':token,'clip_id':clip['id'],'seconds':clip['duration_seconds']*fraction})
                await asyncio.sleep(1.)
                reference=await call('capture_wear_reference',{'expected_wear':token,'item_id':item['id'],'mesh_names':names,'preview':True})
                shutil.copy2(reference['path'],folder/'reference.json')
                motion=await call('capture_wear_motion',{'expected_wear':token,'samples':3,'interval_seconds':.15,'view':'side','size':1024})
                raw=json.loads(Path(motion['manifest_path']).read_text(encoding='utf8'));first=raw['samples'][0];last=raw['samples'][-1]
                shutil.copy2(motion['manifest_path'],folder/'motion.json')
                positions={b['id']:b['position'] for b in first['bones'] if b['name']=='J_Bip_C_Hips' or b['name'].endswith(('UpperLeg','LowerLeg','Foot'))}
                import math
                error=max(math.dist(b['position'],positions[b['id']]) for b in last['bones'] if b['id'] in positions)
                assert error<1e-5,('Frozen body drift',error)
                for i,image in enumerate(motion['images']):shutil.copy2(image['path'],folder/('frame-%02d.png'%i))
                shutil.copy2(motion['manifest_path'],folder/'motion.json')
                results.append({'fraction':fraction,'freeze':freeze,'body_drift_m':error,'reference':reference,'motion':motion['summary']})
        finally:
            await call('set_wear_animation',{'expected_wear':token,'playing':False});await call('select_wear_preview_clip',{'expected_wear':token,'clip_id':None})
        tools=len((await client.list_tools()).tools)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==saved['sha256']
    (out/'acceptance.json').write_text(json.dumps({'passed':True,'source_unchanged':True,'tools':tools,'results':results},ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'passed':True,'tools':tools,'fixed_poses':len(results),'body_drift_m':[r['body_drift_m'] for r in results]}),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--record',type=Path,default=ROOT/'projects/whale-maid/sleeve-cuff-v01/final-wear/refined-wear-acceptance.json')
    p.add_argument('--out',type=Path,required=True);p.add_argument('--fractions',type=float,nargs='+',default=[0,.25,.5,.75]);a=p.parse_args()
    assert all(0<=f<1 for f in a.fractions);asyncio.run(main(a))
