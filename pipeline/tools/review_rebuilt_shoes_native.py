"""One native session: actual 3D shoe context, close-ups, held poses and VRM."""
import argparse,asyncio,hashlib,json,math,shutil,struct,sys
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'VRoid-MCP'))
from vroid_mcp.wear_fit import transform
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):
    with p.open('x',encoding='utf8') as f:json.dump(d,f,ensure_ascii=False,indent=2)
def skin_error(data):
    maximum=0.
    for mesh in data['garments']:
        for i,(source,weights) in enumerate(zip(mesh['source_positions'],mesh['weights'])):
            predicted=[0.,0.,0.]
            for slot,w in zip(weights['indices'],weights['weights']):
                if w<=1e-7:continue
                bone=data['bones'][mesh['bone_ids'][slot]]
                allowed={'J_Bip_L_Foot','J_Bip_R_Foot'}
                if mesh['name'].startswith('FIT_NEW_WhiteStocking_'):
                    allowed|={'J_Bip_C_Hips',*(f'J_Bip_{s}_{part}' for s in ['L','R'] for part in ['UpperLeg','LowerLeg','ToeBase'])}
                assert bone['name'] in allowed
                p=transform(transform(source,mesh['bindposes'][slot]),bone['world_matrix'])
                for k in range(3):predicted[k]+=p[k]*w
            actual=transform(mesh['positions'][i],mesh['world_matrix']);maximum=max(maximum,math.dist(predicted,actual))
    assert maximum<1e-5,maximum;return maximum
async def main(a):
    out=a.out.resolve();assert out.is_relative_to(ROOT/'projects/whale-maid');out.mkdir(exist_ok=False);native.OUT=out
    record=json.loads(a.record.read_text(encoding='utf8'));save=record['save'];base=record.get('startup_base') or json.loads(Path(record['base_record']).read_text(encoding='utf8'))['save'];assert (record.get('cold_reopen_passed') or record.get('native_shoe_hidden_cold_passed')) and digest(save['path'])==save['sha256']
    poses=[]
    async with native.client_for(Path(base['path']),'rebuilt-shoe-review') as (client,call):
        tool_count=len((await client.list_tools()).tools)
        await call('list_face_params')
        await asyncio.sleep(10);status=await call('get_wear_status');status=await call('open_wear_project',{'expected_wear':status['wear_token'],'filename':Path(save['path']).name,'discard_unsaved':True});token=status['wear_token']
        mask=await call('inspect_wear_body_occlusion',{'expected_wear':token});assert mask['hidden_vertices']==record.get('body_occlusion_cold_reopen',{}).get('hidden_vertices',[]);write(out/'body-mask.json',mask)
        if record.get('native_shoe_hidden_cold_passed'):
            shoe_state=await call('inspect_wear_native_shoes',{'expected_wear':token});assert not shoe_state['visible'] and shoe_state['current_triangle_count']==0;write(out/'native-shoes-hidden.json',shoe_state)
        snapshot=await call('get_wear_snapshot',{'expected_wear':token});item=snapshot['items'][0];names=[r['name'] for instance in item['instances'] for r in instance['renderers'] if r['name'].startswith('FIT_ACCESSORY_Shoe_')];assert len(names)==8
        if a.include_stockings:
            extra=[r['name'] for instance in item['instances'] for r in instance['renderers'] if r['name'].startswith('FIT_NEW_WhiteStocking_')]
            assert len(extra)==2;names+=extra
        if a.raw_static:
            from vroid_mcp.wear_fit import selected_surface,world,triangles,glb
            captured=await call('capture_wear_reference',{'expected_wear':token,'item_id':item['id'],'mesh_names':names,'include_base_meshes':True,'base_mesh_names':['Body','Foot']})
            data=json.loads(Path(captured['path']).read_text(encoding='utf8'));feet,_=selected_surface(data,'feet')
            diagnostic=[('target_'+side,region['triangles'],'body') for side,region in feet.items()]
            if a.include_stockings:diagnostic=[(m['name'],triangles(m,world(m)),'body') for m in data['base_meshes'] if m['name']=='Body']
            diagnostic.extend((m['name'],triangles(m,world(m)),'garment') for m in data['garments'])
            debug=out/'shoes.glb';debug.write_bytes(glb(diagnostic))
            report={'schema':'native-shoe-raw-review-v1','pose_source':data['pose_source'],'frame':data['frame'],
                'base_body_occlusion':data['base_body_occlusion'],'base_native_shoes':data.get('base_native_shoes'),
                'raw_reference':captured,'debug_glb':{'path':str(debug),'sha256':digest(debug)},
                'scope':'Actual static captured geometry and diagnostic GLB; no unsigned distance/thickness summary computed.'}
            write(out/'shoes.json',report);report['report_path']=str(out/'shoes.json')
        elif a.static_report:
            report=json.loads(a.static_report.read_text(encoding='utf8'))
            assert report['pose_source']=='native_edit' and report['base_body_occlusion']['hidden_vertex_count']==len(mask['hidden_vertices'])
            for artifact in [report['raw_reference'],report['debug_glb']]:assert digest(artifact['path'])==artifact['sha256']
            # A completed read-only report may survive a client timeout. Prove
            # the current saved assembly has the same actual static surfaces
            # before reusing that evidence in this new review session.
            fresh=await call('capture_wear_reference',{'expected_wear':token,'item_id':item['id'],'mesh_names':names,'include_base_meshes':True,'base_mesh_names':['Body','Foot']})
            from accept_hidden_native_heel import compare_geometry
            compare_geometry(json.loads(Path(report['raw_reference']['path']).read_text(encoding='utf8')),json.loads(Path(fresh['path']).read_text(encoding='utf8')))
            shutil.copy2(fresh['path'],out/'fresh-static-check.json')
            write(out/'static-report-reuse.json',{'report':str(a.static_report.resolve()),'report_sha256':digest(a.static_report),'fresh_reference':fresh,'geometry_tolerance_m':1e-6,'saved_assembly':save})
            report['report_path']=str(a.static_report.resolve())
        else:
            report=await call('inspect_wear_fit_context',{'expected_wear':token,'item_id':item['id'],'mesh_names':names,'region':'feet','sample_limit':128})
        assert report['base_body_occlusion']['hidden_vertex_count']==len(mask['hidden_vertices'])
        for source,target in [(report['report_path'],out/'shoes.json'),(report['raw_reference']['path'],out/'shoes-raw-reference.json'),(report['debug_glb']['path'],out/'shoes.glb')]:
            if Path(source).resolve()!=target.resolve():shutil.copy2(source,target)
        review=await call('capture_wear_review',{'expected_wear':token,'views':['feet_front','feet_right','feet_back'],'quality':'high','size':1024});write(out/'close-ups.json',review)
        await call('set_wear_animation',{'expected_wear':token,'playing':True});await call('set_wear_animation',{'expected_wear':token,'playing':False});clips=(await call('list_wear_preview_clips',{'expected_wear':token}))['clips']
        try:
            for label,clip_name,fraction in [('walk25','WALK00_F',.25),('walk75','WALK00_F',.75),('sit50','shot_sitting',.50)]:
                clip=next(c for c in clips if c['name']==clip_name);await call('select_wear_preview_clip',{'expected_wear':token,'clip_id':clip['id']});await call('set_wear_animation',{'expected_wear':token,'playing':True})
                held=await call('hold_wear_preview_pose',{'expected_wear':token,'clip_id':clip['id'],'seconds':clip['duration_seconds']*fraction})
                ref=await call('capture_wear_reference',{'expected_wear':token,'item_id':item['id'],'mesh_names':names,'preview':True,'include_base_meshes':True,'base_mesh_names':['Body','Foot']});target=out/(label+'-reference.json');shutil.copy2(ref['path'],target)
                data=json.loads(target.read_text(encoding='utf8'));error=skin_error(data)
                if record.get('native_shoe_hidden_cold_passed'):assert data.get('base_native_shoes',{}).get('triangle_count')==0,'Native shoe surfaces reappeared in animation preview'
                poses.append({'pose':label,'held':held,'reference':str(target),'shoe_skin_reconstruction_error_m':error,'base_body_occlusion':data['base_body_occlusion'],'base_native_shoes':data.get('base_native_shoes')});await call('set_wear_animation',{'expected_wear':token,'playing':False})
        finally:
            status=await call('get_wear_status')
            if status['animation_playing']:await call('set_wear_animation',{'expected_wear':token,'playing':False})
            await call('select_wear_preview_clip',{'expected_wear':token,'clip_id':None})
        write(out/'pose-bindings.json',poses)
        exported=await call('export_wear_vrm',{'expected_wear':token,'filename':a.export_stem+'-native.vrm','title':'Whale maid Mary Jane shoe review','author':'Local creator','version':a.export_stem})
        vrm=out/(a.export_stem+'.vrm');shutil.copy2(exported['path'],vrm);assert digest(vrm)==exported['sha256'];raw=vrm.read_bytes();document=json.loads(raw[20:20+struct.unpack_from('<I',raw,12)[0]])
        bodies=[]
        for node in document['nodes']:
            if node.get('name')=='Body' and 'mesh' in node:
                mesh=document['meshes'][node['mesh']];count=sum(document['accessors'][p['indices']]['count']//3 for p in mesh['primitives']);bodies.append({'node':'Body','triangles':count})
        assert bodies and sum(b['triangles'] for b in bodies)==mask['current_triangle_count'],(bodies,mask['current_triangle_count'])
        if record.get('native_shoe_hidden_cold_passed'):
            shoe_primitives=[p for mesh in document['meshes'] for p in mesh['primitives'] if '_Shoes_' in document['materials'][p['material']].get('name','') and document['accessors'][p['indices']]['count']>0];assert not shoe_primitives,'Hidden native shoe triangles reappeared in VRM'
        write(out/'vrm-export.json',{'native':exported,'delivered':str(vrm),'body_meshes':bodies,'body_mask_persisted':True,'godot_validated':False})
    assert digest(save['path'])==save['sha256'];write(out/'acceptance.json',{'passed':True,'source_unchanged':True,'saved_source':save,'native_tools':tool_count,'static_3d_report':str(out/'shoes.json'),'close_up_views':3,'poses':poses,'vrm_body_mask_persisted':True,'collision_free_certified':False,'visual_art_acceptance':'pending review of native close-ups','godot_validated':False})
    print(json.dumps({'passed':True,'out':str(out),'poses':len(poses),'vrm_body_mask_persisted':True}),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--record',type=Path,required=True);p.add_argument('--out',type=Path,required=True);mode=p.add_mutually_exclusive_group();mode.add_argument('--static-report',type=Path,help='Completed read-only report to reuse after fresh native geometry equality check');mode.add_argument('--raw-static',action='store_true',help='Capture actual geometry and GLB without optional distance/thickness summaries');p.add_argument('--include-stockings',action='store_true',help='Also capture and verify the two native-body-derived stocking surfaces');p.add_argument('--export-stem',default='whale-maid-maryjane-v09');a=p.parse_args();assert all(c.isalnum() or c in '-_' for c in a.export_stem);asyncio.run(main(a))
