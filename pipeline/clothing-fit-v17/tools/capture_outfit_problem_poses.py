"""Read-only full outfit edit/sit/walk captures for targeted fit repair."""
import argparse,asyncio,hashlib,json,shutil
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1]
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):
    with p.open('x',encoding='utf8') as f:json.dump(d,f,ensure_ascii=False,indent=2)
async def main(a):
    if a.lab_root:
        lab=a.lab_root.resolve();assert lab.is_relative_to(ROOT) and (lab/'app/VRoidStudio.exe').is_file() and lab.name.startswith('lab-clothing-');native.LAB=lab
    if a.server_root:
        server=a.server_root.resolve();assert server.is_relative_to(ROOT/'work') and (server/'SOURCE_ISOLATION.json').is_file();native.PROJECT=server
    record=json.loads(a.record.read_text(encoding='utf8'));saved=record['save'];assert record['cold_reopen_passed'] and digest(saved['path'])==saved['sha256']
    out=a.out.resolve();assert not out.exists() and out.is_relative_to(ROOT/'projects/whale-maid');out.mkdir();native.OUT=out
    base=json.loads(Path(record['base_record']).read_text(encoding='utf8'))['save'];rows=[];motions=[];exported=None
    async with native.client_for(Path(base['path']),'problem-poses') as (_,call):
        await call('list_face_params');await asyncio.sleep(10)
        state=await call('get_wear_status');state=await call('open_wear_project',{'expected_wear':state['wear_token'],'filename':Path(saved['path']).name,'discard_unsaved':True})
        token=state['wear_token'];snap=await call('get_wear_snapshot',{'expected_wear':token});write(out/'snapshot.json',snap)
        item=snap['items'][0];names=[r['name'] for inst in item['instances'] for r in inst['renderers'] if r['name'].startswith('FIT_')];assert len(names)==a.expected_meshes
        async def ref(label,preview):
            r=await call('capture_wear_reference',{'expected_wear':token,'item_id':item['id'],'mesh_names':names,'preview':preview,'include_base_meshes':True,'base_mesh_names':['Body','Foot']})
            target=out/(label+'-reference.json');shutil.copy2(r['path'],target);assert digest(target)==r['sha256'];return {'path':str(target),'sha256':r['sha256']}
        static=await ref('edit',False)
        await call('capture_wear_review',{'expected_wear':token,'views':['upper_left','upper_right','upper_three_quarter_right','front'],'size':1024,'quality':'high'})
        await call('set_wear_animation',{'expected_wear':token,'playing':True});await call('set_wear_animation',{'expected_wear':token,'playing':False})
        clips=(await call('list_wear_preview_clips',{'expected_wear':token}))['clips'];write(out/'clips.json',clips)
        try:
            for label,name,fraction in [('sitting','shot_sitting',0),('walk25','WALK00_F',.25),('walk75','WALK00_F',.75)]:
                clip=next(c for c in clips if c['name']==name)
                await call('select_wear_preview_clip',{'expected_wear':token,'clip_id':clip['id']});await call('set_wear_animation',{'expected_wear':token,'playing':True})
                held=await call('hold_wear_preview_pose',{'expected_wear':token,'clip_id':clip['id'],'seconds':clip['duration_seconds']*fraction})
                await asyncio.sleep(1);r=await ref(label,True)
                for view in (['front','body_left','body_right','back'] if label=='sitting' else ['front','body_right']):
                    c=await call('capture_wear_motion',{'expected_wear':token,'samples':3,'interval_seconds':.1,'view':view,'size':1024,'quality':'high'})
                    shutil.copy2(c['images'][0]['path'],out/(label+'-'+view+'.png'))
                rows.append({'label':label,'clip':clip,'held':held,'reference':r});write(out/(label+'.json'),rows[-1])
                await call('set_wear_animation',{'expected_wear':token,'playing':False})
            if a.motion:
                for label,name,view,count,interval in [('walk-front','WALK00_F','front',12,.15),('walk-side','WALK00_F','body_right',12,.15),('walk-back','WALK00_F','back',12,.15),('run-side','RUN00_F','body_right',8,.15),('jump-front','JUMP00B','front',10,.25)]:
                    clip=next(c for c in clips if c['name']==name)
                    await call('select_wear_preview_clip',{'expected_wear':token,'clip_id':clip['id']});await call('set_wear_animation',{'expected_wear':token,'playing':True})
                    motion=await call('capture_wear_motion',{'expected_wear':token,'samples':count,'interval_seconds':interval,'view':view,'size':768,'quality':'high'})
                    folder=out/label;folder.mkdir();shutil.copy2(motion['manifest_path'],folder/'motion.json')
                    for i,img in enumerate(motion['images']):shutil.copy2(img['path'],folder/f'frame-{i:02d}.png')
                    assert motion['summary']['frames_advanced'] and motion['summary']['native_bone_motion_observed'] and motion['summary']['finite_transforms']
                    motions.append({'label':label,'clip':clip,'samples':count,'summary':motion['summary']});write(out/(label+'-completed.json'),motions[-1])
                    await call('set_wear_animation',{'expected_wear':token,'playing':False})
        finally:
            state=await call('get_wear_status')
            if state['animation_playing']:await call('set_wear_animation',{'expected_wear':token,'playing':False})
            await call('select_wear_preview_clip',{'expected_wear':token,'clip_id':None})
        if a.export_stem:
            assert a.export_stem.replace('-','').isalnum() and a.export_stem.isascii()
            exported=await call('export_wear_vrm',{'expected_wear':token,'filename':a.export_stem+'-native.vrm','title':'Whale maid outfit candidate','author':'Local creator','version':a.export_stem})
            target=out/(a.export_stem+'.vrm');shutil.copy2(exported['path'],target);assert digest(target)==exported['sha256'];write(out/'vrm-export.json',{'native':exported,'delivered':str(target)})
    assert digest(saved['path'])==saved['sha256'];write(out/'acceptance.json',{'passed':True,'saved':saved,'source_unchanged':True,'edit':static,'cases':rows,'all_meshes':len(names),'sitting_is_static_pose':True,'motions':motions,'vrm_exported':exported is not None})
    print(json.dumps({'captured':True,'out':str(out),'all_meshes':len(names),'cases':3}),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--record',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--motion',action='store_true');p.add_argument('--export-stem');p.add_argument('--server-root',type=Path);p.add_argument('--lab-root',type=Path);p.add_argument('--expected-meshes',type=int,default=97);asyncio.run(main(p.parse_args()))
