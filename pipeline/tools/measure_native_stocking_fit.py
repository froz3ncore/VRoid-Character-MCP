"""Same-frame stocking-to-original-body vertex correspondence after native skinning."""
import argparse,json,sys,struct,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'VRoid-MCP'))
from vroid_mcp.wear_fit import world,selected_surface

def transformed(points,matrix):
    matrix=np.asarray(matrix);return np.asarray(points)@matrix[:3,:3].T+matrix[:3,3]

def main(a):
    build=json.loads(a.build.read_text(encoding='utf8'));baseline=json.loads(Path(build['native_reference']).read_text(encoding='utf8'))
    source=next(m for m in baseline['base_meshes'] if m['name']=='Body');original=np.asarray(world(source))
    edit=json.loads(a.reference[0].read_text(encoding='utf8'));assert edit['pose_source']=='native_edit','Supply the actual static native_edit reference first'
    _,edit_bones=selected_surface(edit,'feet')
    normals=np.asarray(source['normals'])@np.linalg.inv(np.asarray(source['world_matrix'])[:3,:3]);normals/=np.linalg.norm(normals,axis=1)[:,None]
    expected=original+normals*.00035;states=[]
    for path in a.reference:
        data=json.loads(path.read_text(encoding='utf8'));body=next(m for m in data['base_meshes'] if m['name']=='Body')
        hidden=set(data['base_body_occlusion']['hidden_original_vertex_indices']);kept=[i for i in range(len(original)) if i not in hidden]
        assert len(body['positions'])==len(kept)
        source_error=np.max(np.linalg.norm(np.asarray(source['source_positions'])[kept]-np.asarray(body['source_positions']),axis=1));assert source_error<1e-6,source_error
        actual_body=np.asarray(world(body));body_normals=np.asarray(body['normals'])@np.linalg.inv(np.asarray(body['world_matrix'])[:3,:3]);body_normals/=np.linalg.norm(body_normals,axis=1)[:,None]
        current={original:i for i,original in enumerate(kept)};rows=[]
        for row in build['stockings']:
            mesh=next(m for m in data['garments'] if m['name']==row['mesh']);ids=np.asarray(row['original_body_indices']);source_points=np.asarray(mesh['source_positions'])
            distances=np.sum((source_points[:,None,:]-expected[ids][None,:,:])**2,axis=2);nearest=np.argmin(distances,axis=1)
            match=np.sqrt(np.min(distances,axis=1));assert match.max()<1e-6,(row['mesh'],'source correspondence',match.max())
            native_ids=np.asarray([current[int(i)] for i in ids[nearest]]);delta=np.asarray(world(mesh))-actual_body[native_ids];spans=np.linalg.norm(delta,axis=1)*1000;signed=np.sum(delta*body_normals[native_ids],axis=1)*1000
            result={'mesh':row['mesh'],'vertices':len(source_points),'source_correspondence_max_error_mm':float(match.max()*1000),'surface_offset_min_mm':float(spans.min()),'surface_offset_median_mm':float(np.median(spans)),'surface_offset_p95_mm':float(np.percentile(spans,95)),'surface_offset_max_mm':float(spans.max()),'signed_outward_min_mm':float(signed.min())}
            result['passed']=result['surface_offset_max_mm']<2.0 and result['signed_outward_min_mm']>.08
            rows.append(result)
        feet,bones=selected_surface(data,'feet');heel=[]
        for side in ['L','R']:
            name='J_Bip_'+side+'_Foot';matrix=np.asarray(edit_bones[name]['world_matrix'])@np.linalg.inv(np.asarray(bones[name]['world_matrix']))
            shoe=next(m for m in data['garments'] if m['name']=='FIT_ACCESSORY_Shoe_'+side+('_T005' if side=='L' else '_T004'))
            stocking=next(m for m in data['garments'] if m['name']=='FIT_NEW_WhiteStocking_'+side)
            points=world(stocking);foot_points=[p for p,w in zip(points,stocking['weights']) if sum(v for slot,v in zip(w['indices'],w['weights']) if data['bones'][stocking['bone_ids'][slot]]['name'] in (name,'J_Bip_'+side+'_ToeBase'))>=.35]
            shoe_rear=transformed(world(shoe),matrix)[:,2].min()
            heel.append({'side':side,'posterior_body_foot_bbox_margin_mm':float((transformed(feet[side]['points'],matrix)[:,2].min()-shoe_rear)*1000),'posterior_stocking_foot_bbox_margin_mm':float((transformed(foot_points,matrix)[:,2].min()-shoe_rear)*1000)})
        states.append({'reference':str(path.resolve()),'pose_source':data['pose_source'],'frame':data['frame'],'body_source_correspondence_error_mm':float(source_error*1000),'rows':rows,'heel_bounds_in_static_foot_frame':heel})
    report={'passed':all(r['passed'] for s in states for r in s['rows']),'build':str(a.build.resolve()),'states':states,'method':'Match native garment source vertices to captured body+normal offset and original Body indices; compare both actual BakeMesh surfaces in the same frame. Signed offset detects inversion. Heel bounds use the same base Foot coordinate frame across poses.','scope':'Current captures and model only. Positive bounding-box margins do not prove closed heel/sole coverage. Does not certify unrestricted animation or closed material volume.'}
    with a.out.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps({'passed':report['passed'],'maximum_offset_mm':max(r['surface_offset_max_mm'] for s in states for r in s['rows']),'minimum_outward_mm':min(r['signed_outward_min_mm'] for s in states for r in s['rows'])}),flush=True)
    assert report['passed'],'Stocking-to-body fit drift/inversion; do not adopt'

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--reference',type=Path,action='append',required=True);p.add_argument('--out',type=Path,required=True);main(p.parse_args())
