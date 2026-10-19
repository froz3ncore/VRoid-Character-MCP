"""Discover real native body/photo controls without saving or changing mesh assets."""
import argparse, asyncio, hashlib, json
from pathlib import Path
import clean_native_clothing as native

ROOT=Path(__file__).resolve().parents[1]

def write(path,value):
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2)

async def main(a):
    out=a.out.resolve();assert out.is_relative_to(ROOT/'projects/whale-maid');out.mkdir(exist_ok=False);native.OUT=out
    base=json.loads((ROOT/'projects/whale-maid/accessory-refinement-v02/tripo-shoe-rigid-v12/high-heel-base-record.json').read_text(encoding='utf8'))['save']
    assert hashlib.sha256(Path(base['path']).read_bytes()).hexdigest()==base['sha256']
    async with native.client_for(Path(base['path']),'toein-pose-discovery') as (_,call):
        identity=await call('list_face_params');token=identity['model_token'];await asyncio.sleep(10)
        body=await call('list_parameters',{'domain':'body','limit':500});assert not body.get('next_offset');write(out/'body-parameters.json',body)
        await call('set_preview_mode',{'expected_model':token,'mode':'photo'})
        try:
            photo=await call('list_parameters',{'domain':'photo','limit':500});assert not photo.get('next_offset');write(out/'photo-parameters.json',photo)
            pose=next(p for p in photo['parameters'] if p['id']=='photo/pose');print(json.dumps({'native_pose_options':pose.get('options')},ensure_ascii=False),flush=True)
            # Select an existing real preset to instantiate its native controls.
            result=await call('set_parameters',{'expected_model':token,'domain':'photo','changes':[{'id':pose['id'],'value':pose['value']}]});write(out/'preset-selected.json',result)
            photo=await call('list_parameters',{'domain':'photo','limit':500});write(out/'manual-photo-parameters.json',photo)
            controls=[p for p in photo['parameters'] if p['id'].startswith('photo/pose_controls/')]
            write(out/'pose-controls.json',controls)
            print(json.dumps({'controls':controls},ensure_ascii=False),flush=True)
        finally:
            await call('set_preview_mode',{'expected_model':token,'mode':'edit'})
    assert hashlib.sha256(Path(base['path']).read_bytes()).hexdigest()==base['sha256']
    write(out/'acceptance.json',{'passed':True,'source_unchanged':True,'native_base':base,'photo_controls_discovered':len(controls),'pose_changes_saved_to_model':False,'xwear_assembly_modified':False})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);asyncio.run(main(p.parse_args()))
