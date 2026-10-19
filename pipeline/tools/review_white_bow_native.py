"""Actual native assembled bow views, one walking clip and three held poses."""
import argparse, asyncio, hashlib, json, shutil
from pathlib import Path
import clean_native_clothing as native

ROOT=Path(__file__).resolve().parents[1]
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):
    with p.open('x',encoding='utf8') as f:json.dump(d,f,ensure_ascii=False,indent=2)

async def main(a):
    record=json.loads(a.record.read_text(encoding='utf8'));saved=record['save']
    assert record['passed'] and record['cold_reopen_passed'] and digest(saved['path'])==saved['sha256']
    base=json.loads(Path(record['base_record']).read_text(encoding='utf8'))['save']
    out=a.out.resolve();assert out.is_relative_to(ROOT/'projects/whale-maid') and not out.exists()
    out.mkdir();native.OUT=out;poses=[]
    async with native.client_for(Path(base['path']),'white-bow-review') as (_,call):
        await call('list_face_params');await asyncio.sleep(10)
        state=await call('get_wear_status')
        state=await call('open_wear_project',{'expected_wear':state['wear_token'],'filename':Path(saved['path']).name,'discard_unsaved':True})
        token=state['wear_token'];snap=await call('get_wear_snapshot',{'expected_wear':token})
        write(out/'snapshot.json',snap)
        mask=await call('inspect_wear_body_occlusion',{'expected_wear':token});shoes=await call('inspect_wear_native_shoes',{'expected_wear':token})
        assert mask['hidden_vertices']==record['body_occlusion_cold_reopen']['hidden_vertices'] and not shoes['visible'] and shoes['current_triangle_count']==0
        item=snap['items'][0];all_names=[r['name'] for inst in item['instances'] for r in inst['renderers']]
        bows=sorted(n for n in all_names if n.startswith('FIT_NEW_Bow'));assert len(bows)==5
        main_mesh=next(n for n in all_names if n.startswith('FIT_T001'))
        selected=[main_mesh]+bows+[n for n in all_names if n.startswith('FIT_ACCESSORY_WhaleTail_')]
        async def reference(label,preview=False):
            r=await call('capture_wear_reference',{'expected_wear':token,'item_id':item['id'],'mesh_names':selected,
                'include_base_meshes':True,'base_mesh_names':['Body','Foot'],'preview':preview})
            target=out/(label+'-reference.json');shutil.copy2(r['path'],target);assert digest(target)==r['sha256']
            return {'path':str(target),'sha256':r['sha256']}
        static=await reference('static')
        views=await call('capture_wear_review',{'expected_wear':token,'views':['front','back','upper_back','body_right','body_three_quarter_right'],'size':1024,'quality':'high'})
        write(out/'static-views.json',views)
        fit=await call('inspect_wear_fit_context',{'expected_wear':token,'item_id':item['id'],'mesh_names':[main_mesh]+bows,
            'region':'waist_back','target_mesh_name':main_mesh,'sample_limit':128})
        for source,destination in [(fit['report_path'],'mount-context.json'),(fit['raw_reference']['path'],'mount-raw-reference.json'),(fit['debug_glb']['path'],'mount-context.glb')]:shutil.copy2(source,out/destination)
        await call('set_wear_animation',{'expected_wear':token,'playing':True})
        await call('set_wear_animation',{'expected_wear':token,'playing':False})
        clips=(await call('list_wear_preview_clips',{'expected_wear':token}))['clips'];write(out/'clips.json',clips)
        walk=next(c for c in clips if c['name']=='WALK00_F')
        try:
            await call('select_wear_preview_clip',{'expected_wear':token,'clip_id':walk['id']})
            await call('set_wear_animation',{'expected_wear':token,'playing':True})
            motion=await call('capture_wear_motion',{'expected_wear':token,'samples':12,'interval_seconds':.15,'view':'back','size':1024,'quality':'high'})
            folder=out/'walk-back';folder.mkdir()
            shutil.copy2(motion['manifest_path'],folder/'motion.json')
            for i,r in enumerate(motion['images']):shutil.copy2(r['path'],folder/f'frame-{i:02d}.png')
            assert motion['summary']['frames_advanced'] and motion['summary']['finite_transforms'] and motion['summary']['native_bone_motion_observed']
            await call('set_wear_animation',{'expected_wear':token,'playing':False})
            sitting=next(c for c in clips if c['name']=='shot_sitting')
            for label,clip,t in [('walk25',walk,walk['duration_seconds']*.25),('walk75',walk,walk['duration_seconds']*.75),('sitting',sitting,0)]:
                await call('select_wear_preview_clip',{'expected_wear':token,'clip_id':clip['id']})
                await call('set_wear_animation',{'expected_wear':token,'playing':True})
                held=await call('hold_wear_preview_pose',{'expected_wear':token,'clip_id':clip['id'],'seconds':t})
                ref=await reference(label,True)
                captures=[]
                for view in ['back','body_right']:
                    capture=await call('capture_wear_motion',{'expected_wear':token,'samples':3,'interval_seconds':.1,'view':view,'size':1024,'quality':'high'})
                    shutil.copy2(capture['images'][0]['path'],out/(label+'-'+view+'.png'));captures.append(capture)
                poses.append({'label':label,'clip':clip,'held':held,'reference':ref,'captures':captures})
                write(out/(label+'.json'),poses[-1])
                await call('set_wear_animation',{'expected_wear':token,'playing':False})
        finally:
            state=await call('get_wear_status')
            if state['animation_playing']:await call('set_wear_animation',{'expected_wear':token,'playing':False})
            await call('select_wear_preview_clip',{'expected_wear':token,'clip_id':None})
        exported=await call('export_wear_vrm',{'expected_wear':token,'filename':a.label+'-native.vrm','title':'Whale maid white waist bow','author':'Local creator','version':a.label})
        target=out/(a.label+'.vrm');assert not target.exists();shutil.copy2(exported['path'],target);assert digest(target)==exported['sha256']
        write(out/'vrm-export.json',{'native':exported,'delivered':str(target)})
    assert digest(saved['path'])==saved['sha256']
    write(out/'acceptance.json',{'passed':True,'saved':saved,'source_unchanged':True,'static_reference':static,
        'bow_meshes':bows,'walk_motion_summary':motion['summary'],'held_poses':[{k:v for k,v in r.items() if k!='captures'} for r in poses],
        'body_mask_preserved':True,'native_shoes_hidden':True,'sitting_scope':'zero-duration static pose',
        'vrm':str(target),'vrm_sha256':digest(target),'all_motion_collision_free':False,'godot_validated':False,'visual_review':'pending'})
    print(json.dumps({'passed':True,'out':str(out),'bow_meshes':5,'motion_images':12,'held_poses':3}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--record',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--label',default='whale-maid-white-bow-v16')
    asyncio.run(main(p.parse_args()))
