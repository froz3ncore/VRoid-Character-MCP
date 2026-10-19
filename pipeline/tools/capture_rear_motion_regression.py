"""Record native motion and held-pose recovery in saved baseline/candidate copies."""
import argparse, asyncio, hashlib, json, math, re, shutil
from pathlib import Path
import clean_native_clothing as native

ROOT = Path(__file__).resolve().parents[1]

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(path, data):
    with path.open('x', encoding='utf8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def rear_quaternions(sample):
    return {b['name']: b['local_rotation'] for b in sample['bones']
            if b['name'].startswith('WM_Skirt_') and
            int(b['name'].split('_')[2]) in (4, 5, 6, 7, 8, 12, 13, 14, 15)}

def angle(a, b):
    norm = math.sqrt(sum(v*v for v in a)*sum(v*v for v in b))
    return math.degrees(2*math.acos(min(1., abs(sum(x*y for x,y in zip(a,b)))/norm)))

async def main(a):
    assert re.fullmatch(r'[a-z0-9][a-z0-9-]{0,47}', a.candidate_label)
    out=a.out.resolve()
    assert out.is_relative_to(ROOT/'projects/whale-maid')
    out.mkdir(parents=True, exist_ok=False)
    native.OUT=out
    records={
        'baseline': ROOT/'projects/whale-maid/sleeve-cuff-v01/final-wear/refined-wear-acceptance.json',
        'candidate': a.candidate_record.resolve(),
    }
    saves={k:json.loads(p.read_text(encoding='utf8'))['save'] for k,p in records.items()}
    assert all(digest(v['path'])==v['sha256'] for v in saves.values())
    base=json.loads((ROOT/'projects/whale-maid/clean-wear-v01/clean-base-acceptance.json').read_text(encoding='utf8'))['save']
    results={}
    async with native.client_for(Path(base['path']), 'rear-motion-regression') as (_,call):
        for label,saved in saves.items():
            folder=out/label; folder.mkdir()
            state=await call('get_wear_status')
            opened=await call('open_wear_project', {'filename':Path(saved['path']).name,
                'expected_wear':state['wear_token'], 'discard_unsaved':True})
            token=opened['wear_token']
            snapshot=await call('get_wear_snapshot', {'expected_wear':token})
            assert len(snapshot['items'])==1
            item=snapshot['items'][0]
            names=[r['name'] for i in item['instances'] for r in i['renderers'] if r['name'].startswith('FIT_T001')]
            assert len(names)==1
            write(folder/'snapshot.json',snapshot)
            await call('set_wear_animation', {'expected_wear':token,'playing':True})
            await call('set_wear_animation', {'expected_wear':token,'playing':False})
            clips=(await call('list_wear_preview_clips', {'expected_wear':token}))['clips']
            write(folder/'clips.json',clips)
            rows=[]

            async def motion(case, samples=16, interval=.15):
                dest=folder/case; dest.mkdir()
                result=await call('capture_wear_motion', {'expected_wear':token,'samples':samples,
                    'interval_seconds':interval,'view':'legs_three_quarter_right','size':768,'quality':'high'})
                shutil.copy2(result['manifest_path'],dest/'motion.json')
                for i,img in enumerate(result['images']):
                    shutil.copy2(img['path'],dest/('frame-%02d.png'%i))
                data=json.loads((dest/'motion.json').read_text(encoding='utf8'))
                ref=await call('capture_wear_reference', {'expected_wear':token,'item_id':item['id'],
                    'mesh_names':names,'preview':True})
                shutil.copy2(ref['path'],dest/'reference.json')
                rows.append({'case':case,'motion_summary':data['summary'],
                    'sampled_seconds':data['samples'][-1]['elapsed_seconds']})
                return data

            try:
                for case,name in [('walk','WALK00_F'),('sit','shot_sitting')]:
                    clip=next(c for c in clips if c['name']==name)
                    await call('select_wear_preview_clip', {'expected_wear':token,'clip_id':clip['id']})
                    await call('set_wear_animation', {'expected_wear':token,'playing':True})
                    await motion(case)
                    await call('set_wear_animation', {'expected_wear':token,'playing':False})

                walk=next(c for c in clips if c['name']=='WALK00_F')
                await call('select_wear_preview_clip', {'expected_wear':token,'clip_id':walk['id']})
                await call('set_wear_animation', {'expected_wear':token,'playing':True})
                for i in range(25):
                    await call('hold_wear_preview_pose', {'expected_wear':token,'clip_id':walk['id'],
                        'seconds':walk['duration_seconds']*.75*i/24})
                    await asyncio.sleep(.025)
                await motion('held-contact',3,.15)
                await call('hold_wear_preview_pose', {'expected_wear':token,'clip_id':walk['id'],'seconds':0.})
                recovery=await motion('held-recovery',16,.15)
                qs=[rear_quaternions(s) for s in recovery['samples']]
                common=set(qs[0]).intersection(*(set(q) for q in qs))
                assert common
                distances=[sum(angle(q[n],qs[-1][n]) for n in common)/len(common) for q in qs]
                final=max(angle(qs[-2][n],qs[-1][n]) for n in common)
                rows[-1]['rear_rotation_to_final_degrees']=distances
                rows[-1]['final_step_max_degrees']=final
                rows[-1]['recovery_scope']='Observed solver motion and settling; does not prove contact response or collision freedom'
            finally:
                state=await call('get_wear_status')
                if state['animation_playing']:
                    await call('set_wear_animation', {'expected_wear':token,'playing':False})
                await call('select_wear_preview_clip', {'expected_wear':token,'clip_id':None})

            if label=='candidate':
                exported=await call('export_wear_vrm', {'expected_wear':token,
                    'filename':a.candidate_label+'-native-'+out.name+'.vrm',
                    'title':'Whale maid '+a.candidate_label+' local validation', 'author':'Local test asset','version':'test-only'})
                shutil.copy2(exported['path'],folder/('whale_maid_'+a.candidate_label+'.vrm'))
                write(folder/'vrm-export.json',exported)
            results[label]=rows
            write(folder/'capture.json',rows)
    assert all(digest(v['path'])==v['sha256'] for v in saves.values())
    write(out/'acceptance.json', {'native_capture_passed':True,'source_files_unchanged':True,
        'candidate_label':a.candidate_label,'candidate_record':str(a.candidate_record.resolve()),
        'collision_free':False,'turn_animation_validated':False,
        'results':results,'scope':'Finite built-in walk/sit and held-pose recovery samples; candidate remains experimental'})
    print(json.dumps({'native_capture_passed':True,'out':str(out)},ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--candidate-record',type=Path,required=True)
    p.add_argument('--candidate-label',required=True,help='Explicit lowercase candidate identity used in VRM filename and metadata')
    p.add_argument('--out',type=Path,required=True)
    asyncio.run(main(p.parse_args()))
