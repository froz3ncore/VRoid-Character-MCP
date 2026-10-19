"""Native close-ups and bounded motion samples of a saved accessory assembly."""
import argparse,asyncio,hashlib,json,math,re,shutil,struct
from pathlib import Path
import clean_native_clothing as native

ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path,data):
    with path.open('x',encoding='utf8') as f:json.dump(data,f,ensure_ascii=False,indent=2)


async def main(a):
    out=a.out.resolve();assert out.is_relative_to(ROOT/'projects/whale-maid')
    out.mkdir(parents=True,exist_ok=False);native.OUT=out
    record=json.loads(a.record.read_text(encoding='utf8'));saved=record['save']
    assert record['cold_reopen_passed'] and digest(saved['path'])==saved['sha256']
    base_record=Path(record.get('base_record',ROOT/'projects/whale-maid/clean-wear-v01/clean-base-acceptance.json'))
    base=json.loads(base_record.read_text(encoding='utf8'))['save']
    build=json.loads((a.record.parent/'build.json').read_text(encoding='utf8'))
    rows=[];exported=None
    if a.export_vrm_stem:assert re.fullmatch(r'[a-z][a-z0-9_]{1,63}',a.export_vrm_stem)
    async with native.client_for(Path(base['path']),'accessory-review') as (_,call):
        await asyncio.sleep(5)
        state=await call('get_wear_status')
        state=await call('open_wear_project',{'filename':Path(saved['path']).name,'expected_wear':state['wear_token'],'discard_unsaved':True})
        token=state['wear_token'];snapshot=await call('get_wear_snapshot',{'expected_wear':token})
        assert len(snapshot['items'])==1
        item=snapshot['items'][0]
        names=[r['name'] for instance in item['instances'] for r in instance['renderers'] if r['name'].startswith('FIT_ACCESSORY_')]
        expected_count=len(build['added_meshes'])
        assert len(names)==expected_count
        review=await call('capture_wear_review',{'expected_wear':token,
            'views':a.views,
            'quality':'high','size':1024})
        write(out/'close-ups.json',review)
        if a.mount_reference:
            mount_names=[r['name'] for instance in item['instances'] for r in instance['renderers']
                         if r['name'].startswith(('FIT_T001','FIT_NEW_Bow','FIT_ACCESSORY_WhaleTail_','FIT_ACCESSORY_Shoe_'))]
            mount=await call('capture_wear_reference',{'expected_wear':token,'item_id':item['id'],'mesh_names':mount_names,'preview':False})
            shutil.copy2(mount['path'],out/'actual-mount-reference.json')
        await call('set_wear_animation',{'expected_wear':token,'playing':True})
        await call('set_wear_animation',{'expected_wear':token,'playing':False})
        clips=(await call('list_wear_preview_clips',{'expected_wear':token}))['clips']
        write(out/'clips.json',clips)
        try:
            for label,name,view,count in [('walk','WALK00_F',a.walk_view,8),('sit','shot_sitting','body_three_quarter_right',6)]:
                clip=next(c for c in clips if c['name']==name)
                await call('select_wear_preview_clip',{'expected_wear':token,'clip_id':clip['id']})
                await call('set_wear_animation',{'expected_wear':token,'playing':True})
                folder=out/label;folder.mkdir()
                motion=await call('capture_wear_motion',{'expected_wear':token,'samples':count,
                    'interval_seconds':.15,'view':view,'size':768,'quality':'high'})
                shutil.copy2(motion['manifest_path'],folder/'motion.json')
                for index,row in enumerate(motion['images']):shutil.copy2(row['path'],folder/('frame-%02d.png'%index))
                reference=await call('capture_wear_reference',{'expected_wear':token,'item_id':item['id'],'mesh_names':names,'preview':True})
                shutil.copy2(reference['path'],folder/'reference.json')
                data=json.loads((folder/'reference.json').read_text(encoding='utf8'))
                assert len(data['garments'])==expected_count
                bindings=[]
                for garment in data['garments']:
                    expected=build.get('binding_map',{}).get(garment['name'],'J_Bip_C_Head' if '_Head_' in garment['name'] else 'J_Bip_C_Hips')
                    bones=[data['bones'][i]['name'] for i in garment['bone_ids']]
                    assert all(bones[slot]==expected for entry in garment['weights']
                               for slot,weight in zip(entry['indices'],entry['weights']) if weight>1e-7)
                    assert all(math.isfinite(c) for point in garment['positions'] for c in point)
                    bindings.append({'mesh':garment['name'],'bone':expected,'vertices':len(garment['positions'])})
                rows.append({'case':label,'samples':count,'bindings':bindings,'summary':motion['summary']})
                await call('set_wear_animation',{'expected_wear':token,'playing':False})
        finally:
            state=await call('get_wear_status')
            if state['animation_playing']:await call('set_wear_animation',{'expected_wear':token,'playing':False})
            await call('select_wear_preview_clip',{'expected_wear':token,'clip_id':None})
        write(out/'snapshot.json',snapshot)
        if a.export_vrm_stem:
            exported=await call('export_wear_vrm',{'expected_wear':token,
                'filename':a.export_vrm_stem+'-native.vrm','title':a.export_vrm_stem+' appearance review',
                'author':'Local creator','version':'appearance-review'})
            target=out/(a.export_vrm_stem+'.vrm');assert not target.exists()
            shutil.copy2(exported['path'],target)
            assert digest(target)==exported['sha256']
            raw=target.read_bytes();assert raw[:4]==b'glTF'
            document=json.loads(raw[20:20+struct.unpack_from('<I',raw,12)[0]])
            accessory_names=[n.get('name','') for n in document['nodes'] if n.get('name','').startswith('FIT_ACCESSORY_')]
            assert len(set(accessory_names))>=expected_count,accessory_names
            write(out/'vrm-export.json',{'native':exported,'delivered':str(target),
                'accessory_node_names':accessory_names,'actual_accessory_nodes_checked':True,'godot_runtime_validated':False})
    assert digest(saved['path'])==saved['sha256']
    write(out/'acceptance.json',{'native_capture_completed':True,'saved_source_unchanged':True,
        'close_up_views':len(a.views),'cases':rows,'vrm_export_completed':exported is not None,
        'tail_spring_simulation_added':False,'collision_free_certified':False,
        'scope':'Native accessory presence, binding, close-ups and finite walk/sit samples. Existing clothing collision remains paused.'})
    print(json.dumps({'native_capture_completed':True,'out':str(out),'cases':['walk','sit']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--record',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--export-vrm-stem')
    p.add_argument('--views',nargs='+',default=['head_front','head_back','head_right','body_back','body_three_quarter_right'])
    p.add_argument('--walk-view',default='back')
    p.add_argument('--mount-reference',action='store_true')
    asyncio.run(main(p.parse_args()))
