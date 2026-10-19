"""Compare a new XWear to the accepted baseline at identical native walk poses."""
import argparse,asyncio,hashlib,json,math,shutil
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1]

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,data):
    with path.open('x',encoding='utf8') as f:json.dump(data,f,ensure_ascii=False,indent=2)

async def capture(call,token,folder,fractions,approach_steps):
    snapshot=await call('get_wear_snapshot',{'expected_wear':token});assert len(snapshot['items'])==1
    item=snapshot['items'][0]
    names=[r['name'] for inst in item['instances'] for r in inst['renderers'] if r['name'].startswith('FIT_T001')];assert len(names)==1
    await call('set_wear_animation',{'expected_wear':token,'playing':True})
    await call('set_wear_animation',{'expected_wear':token,'playing':False})
    clips=(await call('list_wear_preview_clips',{'expected_wear':token}))['clips']
    clip=next(c for c in clips if c['name']=='WALK00_F')
    write(folder/'clips.json',clips)
    await call('select_wear_preview_clip',{'expected_wear':token,'clip_id':clip['id']})
    await call('set_wear_animation',{'expected_wear':token,'playing':True})
    rows=[];previous=0.
    try:
        for i,fraction in enumerate(fractions):
            out=folder/('pose-%02d'%i);out.mkdir()
            approach=[]
            if approach_steps:
                for step in range(approach_steps+1):
                    value=previous+(fraction-previous)*step/approach_steps
                    held=await call('hold_wear_preview_pose',{'expected_wear':token,'clip_id':clip['id'],'seconds':clip['duration_seconds']*value})
                    approach.append(held)
                    await asyncio.sleep(.025)
            freeze=await call('hold_wear_preview_pose',{'expected_wear':token,'clip_id':clip['id'],'seconds':clip['duration_seconds']*fraction})
            await asyncio.sleep(1)
            ref=await call('capture_wear_reference',{'expected_wear':token,'item_id':item['id'],'mesh_names':names,'preview':True})
            shutil.copy2(ref['path'],out/'reference.json')
            motion=await call('capture_wear_motion',{'expected_wear':token,'samples':3,'interval_seconds':.15,'view':'legs_three_quarter_right','size':768,'quality':'high'})
            data=json.loads(Path(motion['manifest_path']).read_text(encoding='utf8'))
            first,last=data['samples'][0],data['samples'][-1]
            bones={b['id']:b['position'] for b in first['bones'] if b['name']=='J_Bip_C_Hips' or b['name'].endswith(('UpperLeg','LowerLeg','Foot'))}
            drift=max(math.dist(b['position'],bones[b['id']]) for b in last['bones'] if b['id'] in bones)
            assert drift<1e-5,drift
            shutil.copy2(motion['manifest_path'],out/'motion.json')
            for j,image in enumerate(motion['images']):shutil.copy2(image['path'],out/('frame-%02d.png'%j))
            row={'fraction':fraction,'freeze':freeze,'body_drift_m':drift,'reference_sha256':digest(out/'reference.json'),'approach':approach}
            write(out/'capture.json',row);rows.append(row)
            previous=fraction
    finally:
        await call('set_wear_animation',{'expected_wear':token,'playing':False})
        await call('select_wear_preview_clip',{'expected_wear':token,'clip_id':None})
    write(folder/'snapshot.json',snapshot)
    return rows

async def main(a):
    out=a.out.resolve();assert out.is_relative_to(ROOT/'projects/whale-maid');out.mkdir(parents=True,exist_ok=False);native.OUT=out
    base=json.loads((ROOT/'projects/whale-maid/clean-wear-v01/clean-base-acceptance.json').read_text(encoding='utf8'))['save']
    baseline=json.loads((ROOT/'projects/whale-maid/sleeve-cuff-v01/final-wear/refined-wear-acceptance.json').read_text(encoding='utf8'))['save']
    assert digest(base['path'])==base['sha256'] and digest(baseline['path'])==baseline['sha256']
    package=a.package.resolve();package_hash=digest(package)
    staged=native.LAB/'saves'/('rear-support-'+package_hash[:12]+'.xwear')
    if not staged.exists():shutil.copy2(package,staged)
    assert digest(staged)==package_hash
    write(out/'inputs.json',{'base':base,'baseline':baseline,'package':str(package),'package_sha256':package_hash,'staged':str(staged)})
    results={}
    async with native.client_for(Path(base['path']),'rear-support-compare') as (client,call):
        if a.initial_settle_seconds:
            write(out/'initial-status.json',await call('get_wear_status'))
            await asyncio.sleep(a.initial_settle_seconds)
        for label in (['baseline','candidate'] if not a.candidate_only else ['candidate']):
            folder=out/label;folder.mkdir()
            state=await call('get_wear_status')
            filename=Path(baseline['path']).name if label=='baseline' else Path(base['path']).name
            state=await call('open_wear_project',{'filename':filename,'expected_wear':state['wear_token'],'discard_unsaved':True})
            if label=='candidate':state=await call('import_xwear',{'filename':staged.name,'expected_wear':state['wear_token']})
            write(folder/'opened.json',state)
            results[label]=await capture(call,state['wear_token'],folder,a.fractions,a.approach_steps)
            write(folder/'captured.json',results[label])
        tools=len((await client.list_tools()).tools)
    assert digest(base['path'])==base['sha256'] and digest(baseline['path'])==baseline['sha256'] and digest(package)==package_hash
    write(out/'acceptance.json',{'native_capture_passed':True,'source_files_unchanged':True,'saved_candidate':False,'tools':tools,'results':results})
    print(json.dumps({'native_capture_passed':True,'tools':tools,'out':str(out),'cases':list(results)},ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--package',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--fractions',type=float,nargs='+',default=[.25,.75]);p.add_argument('--candidate-only',action='store_true')
    p.add_argument('--approach-steps',type=int,default=0)
    p.add_argument('--initial-settle-seconds',type=float,default=0.)
    a=p.parse_args();assert all(0<=f<1 for f in a.fractions) and 0<=a.approach_steps<=100 and 0<=a.initial_settle_seconds<=10;asyncio.run(main(a))
