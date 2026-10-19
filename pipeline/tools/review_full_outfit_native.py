"""Read-only saved-assembly review with native images and bounded motion evidence."""
import argparse, asyncio, hashlib, json, shutil
from pathlib import Path
import clean_native_clothing as native

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


async def main(a):
    record = json.loads(a.record.read_text(encoding='utf8'))
    saved = record['save']
    assert record['cold_reopen_passed'] and digest(saved['path']) == saved['sha256']
    base = record.get('startup_base') or json.loads(Path(record['base_record']).read_text(encoding='utf8'))['save']
    out = a.out.resolve()
    assert out.is_relative_to(ROOT/'projects/whale-maid')
    out.mkdir(exist_ok=False)
    native.OUT = out
    rows = []
    async with native.client_for(Path(base['path']), 'full-outfit') as (client, call):
        await call('list_face_params')
        await asyncio.sleep(10)
        state = await call('get_wear_status')
        state = await call('open_wear_project', {'expected_wear': state['wear_token'], 'filename': Path(saved['path']).name, 'discard_unsaved': True})
        token = state['wear_token']
        mask = await call('inspect_wear_body_occlusion', {'expected_wear': token})
        assert mask['hidden_vertices'] == record['body_occlusion_cold_reopen']['hidden_vertices']
        shoe = await call('inspect_wear_native_shoes', {'expected_wear': token})
        assert not shoe['visible'] and shoe['current_triangle_count'] == 0
        snapshot = await call('get_wear_snapshot', {'expected_wear': token})
        assert len(snapshot['items']) == 1
        item = snapshot['items'][0]
        names = [r['name'] for inst in item['instances'] for r in inst['renderers'] if r['name'].startswith(('FIT_ACCESSORY_Shoe_', 'FIT_NEW_WhiteStocking_'))]
        assert len(names) == 10
        write(out/'snapshot.json', snapshot)
        if a.full_static_reference:
            all_names = [r['name'] for inst in item['instances'] for r in inst['renderers'] if r['name'].startswith('FIT_')]
            assert len(all_names)==97
            ref = await call('capture_wear_reference', {'expected_wear':token,'item_id':item['id'],'mesh_names':all_names,'include_base_meshes':True,'base_mesh_names':['Body','Foot']})
            shutil.copy2(ref['path'],out/'full-static-reference.json')
        views = ['front', 'back', 'body_left', 'body_right', 'body_three_quarter_left', 'body_three_quarter_right', 'upper_front', 'upper_back', 'legs_front', 'head_front', 'head_back']
        if a.shoe_closeups:
            views += ['feet_front','feet_back','feet_left','feet_right','feet_three_quarter_left','feet_three_quarter_right']
        reviews = []
        for start in range(0, len(views), 6):
            reviews.append(await call('capture_wear_review', {'expected_wear': token, 'views': views[start:start+6], 'size': 1024, 'quality': 'high'}))
        write(out/'views.json', reviews)
        await call('set_wear_animation', {'expected_wear': token, 'playing': True})
        await call('set_wear_animation', {'expected_wear': token, 'playing': False})
        clips = (await call('list_wear_preview_clips', {'expected_wear': token}))['clips']
        write(out/'clips.json', clips)
        cases = [('walk-front', 'WALK00_F', 'front', 12, .15), ('walk-side', 'WALK00_F', 'body_right', 12, .15), ('walk-back', 'WALK00_F', 'back', 12, .15), ('run-side', 'RUN00_F', 'body_right', 8, .15), ('jump-front', 'JUMP00B', 'front', 10, .25)]
        try:
            for label, name, view, count, interval in cases:
                clip = next(c for c in clips if c['name'] == name)
                await call('select_wear_preview_clip', {'expected_wear': token, 'clip_id': clip['id']})
                await call('set_wear_animation', {'expected_wear': token, 'playing': True})
                folder = out/label
                folder.mkdir()
                motion = await call('capture_wear_motion', {'expected_wear': token, 'samples': count, 'interval_seconds': interval, 'view': view, 'size': 768, 'quality': 'high'})
                shutil.copy2(motion['manifest_path'], folder/'motion.json')
                for i, image in enumerate(motion['images']):
                    shutil.copy2(image['path'], folder/f'frame-{i:02d}.png')
                assert motion['summary']['frames_advanced'] and motion['summary']['finite_transforms'] and motion['summary']['native_bone_motion_observed'], motion['summary']
                ref = await call('capture_wear_reference', {'expected_wear': token, 'item_id': item['id'], 'mesh_names': names, 'include_base_meshes': True, 'base_mesh_names': ['Body', 'Foot'], 'preview': True})
                shutil.copy2(ref['path'], folder/'shoe-stocking-reference.json')
                data = json.loads(Path(ref['path']).read_text(encoding='utf8'))
                assert data['base_native_shoes']['triangle_count'] == 0
                rows.append({'case': label, 'clip': clip, 'summary': motion['summary'], 'requested_sample_span_seconds': (count-1)*interval, 'reference_frame': data['frame']})
                write(out/f'{label}-completed.json', rows[-1])
                print(json.dumps({'completed': label, 'summary': motion['summary']}), flush=True)
                await call('set_wear_animation', {'expected_wear': token, 'playing': False})
            sitting = next(c for c in clips if c['name'] == 'shot_sitting')
            await call('select_wear_preview_clip', {'expected_wear': token, 'clip_id': sitting['id']})
            await call('set_wear_animation', {'expected_wear': token, 'playing': True})
            held = await call('hold_wear_preview_pose', {'expected_wear': token, 'clip_id': sitting['id'], 'seconds': 0})
            captures = []
            for view in ['front', 'body_right', 'back']:
                capture = await call('capture_wear_motion', {'expected_wear': token, 'samples': 3, 'interval_seconds': .1, 'view': view, 'size': 1024, 'quality': 'high'})
                shutil.copy2(capture['images'][0]['path'], out/('sitting-'+view+'.png'))
                captures.append(capture)
            write(out/'sitting.json', {'clip': sitting, 'held': held, 'captures': captures, 'scope': 'Native zero-duration sitting pose, not continuous sitting animation'})
        finally:
            state = await call('get_wear_status')
            if state['animation_playing']:
                await call('set_wear_animation', {'expected_wear': token, 'playing': False})
            await call('select_wear_preview_clip', {'expected_wear': token, 'clip_id': None})
        if a.export_stem:
            assert all(c.isalnum() or c in '-_' for c in a.export_stem)
            exported=await call('export_wear_vrm',{'expected_wear':token,'filename':a.export_stem+'-native.vrm','title':'Whale maid height registration review','author':'Local creator','version':a.export_stem})
            target=out/(a.export_stem+'.vrm')
            shutil.copy2(exported['path'],target)
            assert digest(target)==exported['sha256']
            write(out/'vrm-export.json',{'native':exported,'delivered':str(target),'godot_validated':False})
    assert digest(saved['path']) == saved['sha256']
    write(out/'acceptance.json', {'passed': True, 'saved_source': saved, 'saved_source_unchanged': True, 'views': views, 'motion_cases': rows, 'sitting_is_static_pose': True, 'turning_animation_available': any('turn' in c['name'].lower() for c in clips), 'camera_angles_are_not_turning_animation': True, 'collision_free_certified': False, 'godot_validated': False, 'visual_review': 'pending'})
    print(json.dumps({'passed': True, 'out': str(out), 'motion_cases': len(rows)}), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--record', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--full-static-reference',action='store_true')
    p.add_argument('--export-stem')
    p.add_argument('--shoe-closeups',action='store_true')
    asyncio.run(main(p.parse_args()))
