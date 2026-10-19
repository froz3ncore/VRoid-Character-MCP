"""Native MCP-only sampled toe-in poses on a saved outfit; never saves model/VRM."""
import argparse,asyncio,hashlib,json,shutil
from pathlib import Path
import clean_native_clothing as native

ROOT=Path(__file__).resolve().parents[1]
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2)

async def main(a):
    record=json.loads(a.record.read_text(encoding='utf8'));saved=record['save']
    assert record['cold_reopen_passed'] and digest(saved['path'])==saved['sha256']
    out=a.out.resolve();assert out.is_relative_to(ROOT/'projects/whale-maid');out.mkdir(exist_ok=False);native.OUT=out
    startup=a.startup_model.resolve();assert startup.is_file();rows=[]
    async with native.client_for(startup,'outfit-toein') as (client,call):
        catalog=await client.list_tools();assert 'pose_wear_preview_legs' in [t.name for t in catalog.tools]
        await call('list_face_params');await asyncio.sleep(10)
        state=await call('get_wear_status')
        state=await call('open_wear_project',dict(expected_wear=state['wear_token'],filename=Path(saved['path']).name,discard_unsaved=True))
        token=state['wear_token'];snapshot=await call('get_wear_snapshot',{'expected_wear':token});write(out/'snapshot.json',snapshot)
        assert len(snapshot['items'])==1;item=snapshot['items'][0]
        names=[r['name'] for inst in item['instances'] for r in inst['renderers'] if r['name'].startswith(('FIT_ACCESSORY_Shoe_','FIT_NEW_WhiteStocking_'))];assert len(names)==10
        await call('set_wear_animation',dict(expected_wear=token,playing=True));await call('set_wear_animation',dict(expected_wear=token,playing=False))
        clips=(await call('list_wear_preview_clips',{'expected_wear':token}))['clips'];write(out/'clips.json',clips)
        async def reference(folder,label):
            ref=await call('capture_wear_reference',dict(expected_wear=token,item_id=item['id'],mesh_names=names,include_base_meshes=True,base_mesh_names=['Body','Foot'],preview=True))
            path=folder/(label+'.json');shutil.copy2(ref['path'],path)
            return {'path':str(path),'sha256':digest(path),'frame':ref['frame']}
        try:
            cases=[('idle-start','WAIT00',0),('idle-middle','WAIT00',.5),('walk-00','WALK00_F',0),('walk-25','WALK00_F',.25),('walk-50','WALK00_F',.5),('walk-75','WALK00_F',.75)]
            if a.closeups_only:cases=cases[:1]
            for label,name,fraction in cases:
                clip=next(c for c in clips if c['name']==name);folder=out/label;folder.mkdir()
                await call('select_wear_preview_clip',dict(expected_wear=token,clip_id=clip['id']))
                await call('set_wear_animation',dict(expected_wear=token,playing=True))
                seconds=fraction*clip['duration_seconds']
                await call('hold_wear_preview_pose',dict(expected_wear=token,clip_id=clip['id'],seconds=seconds))
                before=await reference(folder,'neutral-reference')
                posed=await call('pose_wear_preview_legs',dict(expected_wear=token,clip_id=clip['id'],seconds=seconds,upper_leg_inward_degrees=a.upper_degrees,foot_inward_degrees=a.foot_degrees));write(folder/'posed.json',posed)
                after=await reference(folder,'toein-reference')
                captures=[]
                for view in (['front','feet_front','feet_right','feet_three_quarter_right'] if label=='idle-start' else ['legs_front']):
                    capture=await call('capture_wear_motion',dict(expected_wear=token,samples=3,interval_seconds=.15,view=view,size=1024,quality='high'))
                    shutil.copy2(capture['images'][0]['path'],folder/(view+'.png'));captures.append(capture)
                write(folder/'captures.json',captures)
                stable=await reference(folder,'stable-reference')
                # Re-evaluation must undo offsets; applying the same request must not accumulate.
                again=await call('pose_wear_preview_legs',dict(expected_wear=token,clip_id=clip['id'],seconds=seconds,upper_leg_inward_degrees=a.upper_degrees,foot_inward_degrees=a.foot_degrees));write(folder/'reapplied.json',again)
                repeated=await reference(folder,'reapplied-reference')
                await call('hold_wear_preview_pose',dict(expected_wear=token,clip_id=clip['id'],seconds=seconds))
                restored=await reference(folder,'restored-reference')
                row=dict(case=label,clip=clip,seconds=seconds,before=before,posed=after,stable=stable,repeated=repeated,restored=restored)
                rows.append(row);write(folder/'case.json',row)
                await call('set_wear_animation',dict(expected_wear=token,playing=False))
                print(json.dumps({'completed':label,'seconds':seconds,'frames':[before['frame'],after['frame'],stable['frame']]}),flush=True)
        finally:
            status=await call('get_wear_status')
            if status['animation_playing']:await call('set_wear_animation',dict(expected_wear=token,playing=False))
            await call('select_wear_preview_clip',dict(expected_wear=token,clip_id=None))
    assert digest(saved['path'])==saved['sha256']
    write(out/'native-toein-profile.json',dict(schema='vroid-native-sampled-leg-pose-v1',source=saved,upper_leg_inward_degrees=a.upper_degrees,foot_inward_degrees=a.foot_degrees,tool='pose_wear_preview_legs',session_only=True,continuous_animation=False,format='MCP preview replay, not .vroidpose or animation asset'))
    write(out/'acceptance.json',dict(capture_completed=True,source_unchanged=True,saved_source=saved,native_tools=len(catalog.tools),cases=rows,geometry_verification='pending',visual_review='pending',continuous_animation=False,model_or_vrm_saved=False,godot_validated=False))
    print(json.dumps({'captured_cases':len(rows),'out':str(out)}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--record',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--upper-degrees',type=float,default=3);p.add_argument('--foot-degrees',type=float,default=8)
    p.add_argument('--startup-model',type=Path,default=ROOT/'lab-test/saves/whale-maid-clean-base-2e252e42f6644d0dafa5bbb53dff3d2c.vroid')
    p.add_argument('--closeups-only',action='store_true')
    a=p.parse_args();assert 0<=a.upper_degrees<=6 and a.upper_degrees<=a.foot_degrees<=12;asyncio.run(main(a))
