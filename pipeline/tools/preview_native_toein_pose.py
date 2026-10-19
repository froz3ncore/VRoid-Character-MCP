"""Actual native Photo Booth toe-in capability demo; session-only, no model saves."""
import argparse, asyncio, base64, hashlib, json, math
from pathlib import Path
import clean_native_clothing as native

ROOT=Path(__file__).resolve().parents[1]
def write(path,value):
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2)
def multiply(a,b):
    x,y,z,w=a;X,Y,Z,W=b
    return [w*X+x*W+y*Z-z*Y,w*Y-x*Z+y*W+z*X,w*Z+x*Y-y*X+z*W,w*W-x*X-y*Y-z*Z]

async def main(a):
    out=a.out.resolve();assert out.is_relative_to(ROOT/'projects/whale-maid');out.mkdir(exist_ok=False);native.OUT=out
    source=json.loads((ROOT/'projects/whale-maid/accessory-refinement-v02/tripo-shoe-rigid-v12/high-heel-base-record.json').read_text(encoding='utf8'))['save']
    assert hashlib.sha256(Path(source['path']).read_bytes()).hexdigest()==source['sha256']
    async with native.client_for(Path(source['path']),'native-toein-demo') as (client,call):
        token=(await call('list_face_params'))['model_token'];await asyncio.sleep(10)
        await call('set_preview_mode',{'expected_model':token,'mode':'photo'})
        try:
            before=await call('list_parameters',{'domain':'photo','limit':500});assert not before.get('next_offset')
            pose=next(p for p in before['parameters'] if p['id']=='photo/pose')
            await call('set_parameters',{'expected_model':token,'domain':'photo','changes':[{'id':pose['id'],'value':pose['value']}]})
            before=await call('list_parameters',{'domain':'photo','limit':500});write(out/'before-parameters.json',before)
            controls=before['parameters'];camera={'expected_model':token,'position':[0,1.0,2.5],'target':[0,.25,0]}
            await call('set_photo_camera',camera)
            async def capture(label):
                result=await client.call_tool('screenshot',{'expected_model':token,'view':'photo','size':1024,'quality':'high'})
                assert not result.isError,result
                images=[c for c in result.content if c.type=='image'];assert len(images)==1
                path=out/(label+'.png');path.write_bytes(base64.b64decode(images[0].data))
                return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
            baseline=await capture('native-base-straight-feet')
            await call('set_photo_camera',{'expected_model':token,'position':[1.6,1.0,2.2],'target':[0,.25,0]})
            baseline_angled=await capture('native-base-straight-three-quarter')
            await call('set_photo_camera',camera)
            changes=[]
            for side,sign in [('left',1),('right',-1)]:
                control=next(p for p in controls if p['label']==side+'FootIK CurrentFootRotation')
                angle=math.radians(a.degrees*sign)/2
                target=multiply([0,math.sin(angle),0,math.cos(angle)],control['value'])
                changes.append({'id':control['id'],'value':target})
            result=await call('set_parameters',{'expected_model':token,'domain':'photo','changes':changes});write(out/'applied.json',result)
            after=await call('list_parameters',{'domain':'photo','limit':500});write(out/'after-parameters.json',after)
            actual={p['id']:p for p in after['parameters']}
            for c in changes:
                assert max(abs(x-y) for x,y in zip(actual[c['id']]['value'],c['value']))<1e-5
            posed=await capture('native-base-toein-feet')
            await call('set_photo_camera',{'expected_model':token,'position':[1.6,1.0,2.2],'target':[0,.25,0]})
            angled=await capture('native-base-toein-three-quarter')
            originals={p['id']:p['value'] for p in controls}
            await call('set_parameters',{'expected_model':token,'domain':'photo','changes':[{'id':c['id'],'value':originals[c['id']]} for c in changes]})
            restored=await call('list_parameters',{'domain':'photo','limit':500});actual={p['id']:p['value'] for p in restored['parameters']}
            assert all(max(abs(x-y) for x,y in zip(actual[c['id']],originals[c['id']]))<1e-5 for c in changes)
            write(out/'native-toein-controls.json',{'source_model_sha256':source['sha256'],'requested_yaw_degrees_each_foot':a.degrees,'controls':[{'label':next(p['label'] for p in controls if p['id']==c['id']),'id_in_tested_build':c['id'],'type':'quaternion','value':c['value']} for c in changes],'format':'MCP Photo Booth parameter replay, not a .vroidpose file','persistent_in_vroid':False})
        finally:
            await call('set_preview_mode',{'expected_model':token,'mode':'edit'})
    assert hashlib.sha256(Path(source['path']).read_bytes()).hexdigest()==source['sha256']
    write(out/'acceptance.json',{'passed':True,'source':source,'native_rotation_readback_passed':True,'pose_restored':True,'model_source_unchanged':True,'photo_only':True,'xwear_assembly_modified':False,'vrm_or_godot_validated':False,'degrees':a.degrees,'images':[baseline,baseline_angled,posed,angled],'visual_review':'pending','scope':'Native high-heel base posing capability. The Tripo outfit was not loaded; this does not repair shoe-to-foot relative heading in v14.'})
    print(json.dumps({'passed':True,'out':str(out),'degrees':a.degrees,'source_unchanged':True}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--degrees',type=float,default=8)
    a=p.parse_args();assert 0<a.degrees<=12;asyncio.run(main(a))
