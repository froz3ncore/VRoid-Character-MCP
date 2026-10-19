"""Verify actual captured pose deltas, shoe following, stability and restoration."""
import argparse,hashlib,json,math,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'VRoid-MCP'))
from vroid_mcp.wear_fit import world

def load(p):return json.loads(Path(p).read_text(encoding='utf8'))
def rot(degrees):
    a=math.radians(degrees);c,s=math.cos(a),math.sin(a)
    return np.array([[c,0,s],[0,1,0],[-s,0,c]])
def bones(d):
    body=next(m for m in d['base_meshes'] if m['name']=='Body')
    return {d['bones'][i]['name']:np.array(d['bones'][i]['world_matrix']) for i in body['bone_ids']}
def meshes(d):return {m['name']:m for m in d['garments']}
def maximum(a,b):return float(np.max(np.linalg.norm(np.array(a)-np.array(b),axis=-1)))
def local(points,m):
    p=np.array(points);return (np.c_[p,np.ones(len(p))]@np.linalg.inv(m).T)[:,:3]
def main(a):
    record=load(a.folder/'acceptance.json');profile=load(a.folder/'native-toein-profile.json');rows=[]
    assert record['capture_completed'] and not record['model_or_vrm_saved']
    for case in record['cases']:
        data={label:load(case[label]['path']) for label in ('before','posed','stable','repeated','restored')}
        for label,d in data.items():
            assert d['pose_source']=='native_preview' and d['base_native_shoes']['triangle_count']==0
            assert hashlib.sha256(Path(case[label]['path']).read_bytes()).hexdigest()==case[label]['sha256']
        before,posed=data['before'],data['posed'];bb,pb=bones(before),bones(posed)
        headings=[];shoe_rows=[];checks={}
        for side,sign in [('L',1),('R',-1)]:
            for part,degrees in [('UpperLeg',profile['upper_leg_inward_degrees']),('Foot',profile['foot_inward_degrees'])]:
                name=f'J_Bip_{side}_{part}';expected=rot(degrees*sign)@bb[name][:3,:3]
                error=float(np.max(np.abs(pb[name][:3,:3]-expected)));assert error<2e-5,(case['case'],name,error)
                relative=pb[name][:3,:3]@np.linalg.inv(bb[name][:3,:3]);yaw=math.degrees(math.atan2(relative[0,2],relative[2,2]))
                headings.append(dict(bone=name,actual_world_y_delta_degrees=yaw,rotation_matrix_max_error=error))
            for part in ('UpperLeg','LowerLeg','Foot','ToeBase'):
                name=f'J_Bip_{side}_{part}';dy=abs(pb[name][1,3]-bb[name][1,3]);assert dy<2e-6,(name,dy)
            for name,mesh in meshes(posed).items():
                if not name.startswith(f'FIT_ACCESSORY_Shoe_{side}_'):continue
                old=meshes(before)[name];foot=f'J_Bip_{side}_Foot'
                error=maximum(local(world(mesh),pb[foot]),local(world(old),bb[foot]));assert error<5e-6,(name,error)
                height=abs(float(np.array(world(mesh))[:,1].min()-np.array(world(old))[:,1].min()));assert height<3e-6,(name,height)
                shoe_rows.append(dict(mesh=name,maximum_foot_relative_drift_mm=error*1000,lowest_y_change_mm=height*1000))
        assert len(shoe_rows)==8
        for label in ('stable','repeated','restored'):
            target=before if label=='restored' else posed
            error=max(maximum(world(meshes(d)[name]),world(mesh)) for name,mesh in meshes(target).items() for d in [data[label]])
            body_error=maximum(world(next(m for m in target['base_meshes'] if m['name']=='Body')),world(next(m for m in data[label]['base_meshes'] if m['name']=='Body')))
            assert max(error,body_error)<5e-6,(case['case'],label,error,body_error)
            checks[label]=dict(garment_max_delta_mm=error*1000,body_max_delta_mm=body_error*1000)
        foot_positions={side:dict(ankle_shift_mm=((pb[f'J_Bip_{side}_Foot'][:3,3]-bb[f'J_Bip_{side}_Foot'][:3,3])*1000).tolist(),knee_shift_mm=((pb[f'J_Bip_{side}_LowerLeg'][:3,3]-bb[f'J_Bip_{side}_LowerLeg'][:3,3])*1000).tolist()) for side in ('L','R')}
        rows.append(dict(case=case['case'],seconds=case['seconds'],actual_bone_yaw=headings,shoes=shoe_rows,stability_repeat_restore=checks,leg_displacements=foot_positions))
    result=dict(passed=True,cases=rows,source_unchanged=record['source_unchanged'],continuous_animation=False,saved_pose_or_animation_asset=False,godot_validated=False,scope='Actual native preview BakeMesh/bones at six frozen idle/walk samples; verifies prescribed yaw, original shoe following, stable/repeated poses and restoration. Not IK foot locking or full collision acceptance.')
    with (a.folder/'geometry-verification.json').open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(dict(passed=True,cases=len(rows),maximum_shoe_drift_mm=max(r['maximum_foot_relative_drift_mm'] for c in rows for r in c['shoes']),maximum_restore_drift_mm=max(max(c['stability_repeat_restore']['restored'].values()) for c in rows))))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',type=Path,required=True);main(p.parse_args())
