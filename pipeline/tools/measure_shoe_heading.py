"""Actual foot anatomy and shoe longitudinal headings; rest-pose diagnostic."""
import argparse, json, math, sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'VRoid-MCP'))
from vroid_mcp.wear_fit import world

def angle(vector):return math.degrees(math.atan2(float(vector[0]),float(vector[1])))

def axes(points):
    # Remove UV/normal split duplicates before estimating an axis.
    points=np.unique(np.round(np.asarray(points),7),axis=0)
    projected=points[:,[0,2]]
    values,vectors=np.linalg.eigh(np.cov(projected.T));axis=vectors[:,-1]
    if axis[1]<0:axis=-axis
    lower,upper=np.quantile(projected[:,1],[.2,.8])
    heel=np.mean(projected[projected[:,1]<=lower],axis=0)
    toe=np.mean(projected[projected[:,1]>=upper],axis=0)
    return {'pca_degrees_from_forward':angle(axis),'longitudinal_variance_ratio':float(values[-1]/values[0]),'heel_to_toe_band_degrees':angle(toe-heel),'heel_center_xz':heel.tolist(),'toe_center_xz':toe.tolist(),'unique_vertices':len(points)}

def main(a):
    data=json.loads(a.reference.read_text(encoding='utf8'));assert data['pose_source']=='native_edit'
    body=next(m for m in data['base_meshes'] if m['name']=='Body');points=np.asarray(world(body))
    names=[data['bones'][i]['name'] for i in body['bone_ids']]
    bones={data['bones'][i]['name']:np.array(data['bones'][i]['world_matrix']) for i in body['bone_ids']}
    rows=[]
    for side,suffix in [('L','005'),('R','004')]:
        foot='J_Bip_'+side+'_Foot';toe='J_Bip_'+side+'_ToeBase'
        ankle=bones[foot][:3,3];tip=bones[toe][:3,3]
        ids=[i for i,w in enumerate(body['weights']) if sum(v for slot,v in zip(w['indices'],w['weights']) if names[slot] in (foot,toe))>=.35 and points[i,1]<=ankle[1]+.005]
        shoe=next(m for m in data['garments'] if m['name']=='FIT_ACCESSORY_Shoe_'+side+'_T'+suffix)
        body_axis=axes(points[ids]);shoe_axis=axes(world(shoe))
        bone_angle=angle((tip-ankle)[[0,2]])
        rows.append({'side':side,'foot_bone_degrees_from_forward':bone_angle,'foot_anatomy_axis':body_axis,'shoe_axis':shoe_axis,'shoe_minus_foot_pca_degrees':shoe_axis['pca_degrees_from_forward']-body_axis['pca_degrees_from_forward'],'shoe_minus_bone_degrees':shoe_axis['pca_degrees_from_forward']-bone_angle})
    report={'reference':str(a.reference.resolve()),'frame':data['frame'],'rows':rows,'convention':'Unity world +Z forward, atan2(dx,dz). Left native foot at negative X: positive angle is inward. Right foot at positive X: negative angle is inward.','scope':'Static horizontal heading estimates, not sole enclosure or full pose acceptance. PCA is affected by asymmetric geometry, so bone and toe/heel-band estimates are also reported.'}
    with a.out.open('x',encoding='utf8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
    print(json.dumps(rows),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--reference',type=Path,required=True);p.add_argument('--out',type=Path,required=True);main(p.parse_args())
