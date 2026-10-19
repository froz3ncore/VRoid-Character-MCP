"""Compare actual old/new native surfaces and torso bone registration."""
import argparse, json, sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'VRoid-MCP'))
from vroid_mcp.wear_fit import world


def main(a):
    old=json.loads(a.before.read_text(encoding='utf8'))
    new=json.loads(a.after.read_text(encoding='utf8'))
    assert old['pose_source']==new['pose_source']=='native_edit'
    body=next(m for m in new['base_meshes'] if m['name']=='Body')
    original=next(m for m in old['base_meshes'] if m['name']=='Body')
    error=float(np.max(np.linalg.norm(np.array(world(body))-np.array(world(original)),axis=1)))
    assert error<1e-6
    def bones(d,mesh):
        return {d['bones'][i]['name']:np.array(d['bones'][i]['world_matrix'])[:3,3] for i in mesh['bone_ids']}
    shoe=next(m for m in new['garments'] if m['name'].startswith('FIT_ACCESSORY_Shoe_'))
    base,garment=bones(new,body),bones(new,shoe)
    gaps=[{'bone':n,'distance_mm':float(np.linalg.norm(base[n]-garment[n])*1000)} for n in sorted(set(base)&set(garment)) if n.startswith('J_')]
    assert len(gaps)>50 and max(r['distance_mm'] for r in gaps)<.005
    originals={m['name']:m for m in old['garments']}
    rows=[]
    for mesh in new['garments']:
        if mesh['name'] not in originals:
            continue
        before=originals[mesh['name']]
        p,q=np.array(world(mesh)),np.array(world(before))
        assert p.shape==q.shape,mesh['name']
        maximum=float(np.max(np.linalg.norm(p-q,axis=1))*1000)
        assert maximum<.005,(mesh['name'],maximum)
        rows.append({'mesh':mesh['name'],'maximum_actual_world_geometry_delta_mm':maximum})
    assert len(rows)==10
    motion=[]
    old_body_bones={old['bones'][i]['name']:np.array(old['bones'][i]['world_matrix']) for i in original['bone_ids']}
    for path in a.pose:
        pose=json.loads(path.read_text(encoding='utf8'))
        pose_body=next(m for m in pose['base_meshes'] if m['name']=='Body')
        pose_bones={pose['bones'][i]['name']:np.array(pose['bones'][i]['world_matrix']) for i in pose_body['bone_ids']}
        shoe_rows=[]
        for mesh in pose['garments']:
            if not mesh['name'].startswith('FIT_ACCESSORY_Shoe_'):
                continue
            side=mesh['name'].split('_')[3]
            bone='J_Bip_'+side+'_Foot'
            matrix=old_body_bones[bone]@np.linalg.inv(pose_bones[bone])
            points=np.array(world(mesh))@matrix[:3,:3].T+matrix[:3,3]
            maximum=float(np.max(np.linalg.norm(points-np.array(world(originals[mesh['name']])),axis=1))*1000)
            assert maximum<.01,(path,mesh['name'],maximum)
            shoe_rows.append({'mesh':mesh['name'],'maximum_foot_relative_geometry_delta_mm':maximum})
        assert len(shoe_rows)==8
        motion.append({'reference':str(path.resolve()),'frame':pose['frame'],'shoe_geometry':shoe_rows})
    report={'passed':True,'old_reference':str(a.before.resolve()),'new_reference':str(a.after.resolve()),'body_world_geometry_delta_mm':error*1000,'matched_bones':gaps,'protected_shoe_stocking_surfaces':rows,'shoe_motion':motion,'scope':'Actual edit-pose native Body and all ten shoe/stocking surfaces preserved; shared skeleton height gap removed. Optional real sampled shoe surfaces compared in the base Foot frame. No shoe enclosure or unrestricted-animation certificate.'}
    with a.out.open('x',encoding='utf8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2)
    print(json.dumps({'passed':True,'max_bone_gap_mm':max(r['distance_mm'] for r in gaps),'max_shoe_stocking_delta_mm':max(r['maximum_actual_world_geometry_delta_mm'] for r in rows)}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--before',type=Path,required=True)
    p.add_argument('--after',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--pose',type=Path,action='append',default=[])
    main(p.parse_args())
