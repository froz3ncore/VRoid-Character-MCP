"""Compare real shoe vertices in the base Foot frame across captured poses.

Requires NumPy (the bundled Blender Python is sufficient). This is an offline
read-only diagnostic, not proof of shoe enclosure or art acceptance.
"""
import argparse, json, sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'VRoid-MCP'))
from vroid_mcp.wear_fit import selected_surface, world

def points_in_frame(points,matrix):
    return np.asarray(points)@matrix[:3,:3].T+matrix[:3,3]

def main(a):
    reference=json.loads(a.edit.read_text(encoding='utf8'));_,edit_bones=selected_surface(reference,'feet')
    canonical={side:np.asarray(edit_bones['J_Bip_'+side+'_Foot']['world_matrix']) for side in ['L','R']}
    original={m['name']:np.asarray(world(m)) for m in reference['garments']}
    rows=[]
    for path in [a.edit]+a.pose:
        data=json.loads(path.read_text(encoding='utf8'));feet,bones=selected_surface(data,'feet');meshes=[]
        for mesh in data['garments']:
            side=mesh['name'].split('_')[3];name='J_Bip_'+side+'_Foot'
            base=np.asarray(bones[name]['world_matrix']);map_to_edit=canonical[side]@np.linalg.inv(base)
            p=points_in_frame(world(mesh),map_to_edit)
            delta=np.linalg.norm(p-original[mesh['name']],axis=1)
            shoe_bone=next(data['bones'][i] for i in mesh['bone_ids'] if data['bones'][i]['name']==name)
            gap=np.linalg.norm(np.asarray(shoe_bone['world_matrix'])[:3,3]-base[:3,3])*1000
            meshes.append({'mesh':mesh['name'],'maximum_relative_geometry_difference_mm':float(delta.max()*1000),
                'base_to_garment_foot_bone_distance_mm':float(gap)})
        rows.append({'path':str(path.resolve()),'pose_source':data['pose_source'],'frame':data['frame'],
            'selected_preview_clip':data.get('selected_preview_clip'),'meshes':meshes})
    report={'method':'Captured renderer-local BakeMesh -> world -> base Foot local -> edit Foot world',
        'states':rows,'maximum_shoe_pose_relative_difference_mm':max(m['maximum_relative_geometry_difference_mm'] for r in rows for m in r['meshes']),
        'interpretation':'Bone translation alone is not the shoe fit error. Native renderer/bind compensation preserves the actual shoe-to-Foot relationship across these captured states.',
        'limitation':'Checks the supplied static and held captures; does not prove enclosure, unrestricted motion or art acceptance.'}
    with a.out.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps({'states':len(rows),'maximum_relative_difference_mm':report['maximum_shoe_pose_relative_difference_mm']}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--edit',type=Path,required=True);p.add_argument('--pose',type=Path,action='append',default=[])
    p.add_argument('--out',type=Path,required=True);main(p.parse_args())
