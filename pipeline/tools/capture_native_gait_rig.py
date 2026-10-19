"""Sample a bounded full native gait cycle through MCP, without saving model assets."""
import argparse,asyncio,hashlib,json
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1]
def write(p,d):
    with p.open('x',encoding='utf8') as f:json.dump(d,f,ensure_ascii=False,indent=2)
async def main(a):
    record=json.loads(a.record.read_text(encoding='utf8'));saved=record['save'];out=a.out.resolve()
    assert out.is_relative_to(ROOT/'projects/whale-maid');out.mkdir(exist_ok=False);native.OUT=out
    assert hashlib.sha256(Path(saved['path']).read_bytes()).hexdigest()==saved['sha256']
    async with native.client_for(a.startup_model,'gait-rig') as (client,call):
        await call('list_face_params');await asyncio.sleep(10)
        s=await call('get_wear_status');s=await call('open_wear_project',dict(expected_wear=s['wear_token'],filename=Path(saved['path']).name,discard_unsaved=True));token=s['wear_token']
        await call('set_wear_animation',dict(expected_wear=token,playing=True));await call('set_wear_animation',dict(expected_wear=token,playing=False))
        clips=(await call('list_wear_preview_clips',dict(expected_wear=token)))['clips'];rows=[]
        try:
            for name in ['WALK00_F','Hub_Idle02']:
                # The loaded Hub clip can have multiple versions; keep exact identity/duration.
                clip=next(c for c in clips if c['name']==name);frames=[]
                await call('select_wear_preview_clip',dict(expected_wear=token,clip_id=clip['id']));await call('set_wear_animation',dict(expected_wear=token,playing=True))
                count=a.samples if name=='WALK00_F' else 31
                duration=clip['duration_seconds'] if name=='WALK00_F' else min(clip['duration_seconds'],4)
                for i in range(count):
                    seconds=duration*i/(count-1)
                    held=await call('hold_wear_preview_pose',dict(expected_wear=token,clip_id=clip['id'],seconds=seconds))
                    rig=await call('sample_wear_preview_rig',dict(expected_wear=token));assert rig['selected_preview_clip']['id']==clip['id']
                    frames.append(dict(seconds=seconds,held=held,rig=rig))
                    if i%10==0:print(json.dumps(dict(clip=name,sampled=i+1,total=count)),flush=True)
                row=dict(clip=clip,sample_span_seconds=duration,frames=frames);write(out/(name+'.json'),row);rows.append(dict(clip=clip,samples=count,span_seconds=duration))
                await call('set_wear_animation',dict(expected_wear=token,playing=False))
        finally:
            if (await call('get_wear_status'))['animation_playing']:await call('set_wear_animation',dict(expected_wear=token,playing=False))
            await call('select_wear_preview_clip',dict(expected_wear=token,clip_id=None))
        tools=await client.list_tools()
    assert hashlib.sha256(Path(saved['path']).read_bytes()).hexdigest()==saved['sha256']
    write(out/'acceptance.json',dict(passed=True,saved_source=saved,source_unchanged=True,native_tools=len(tools.tools),captures=rows,model_saved=False,animation_exported=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--record',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--samples',type=int,default=61)
    p.add_argument('--startup-model',type=Path,default=ROOT/'lab-test/saves/whale-maid-clean-base-2e252e42f6644d0dafa5bbb53dff3d2c.vroid');a=p.parse_args();assert 21<=a.samples<=121;asyncio.run(main(a))
