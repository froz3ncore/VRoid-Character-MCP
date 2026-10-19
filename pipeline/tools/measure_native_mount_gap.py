"""Measure static native accessory-to-garment back gaps in captured world space."""
import argparse,json
from pathlib import Path
import numpy as np
def world(mesh):
    p=np.asarray(mesh['positions']);m=np.asarray(mesh['world_matrix']);return p@m[:3,:3].T+m[:3,3]
def measure(path):
    d=json.loads(path.read_text(encoding='utf8'));meshes={m['name']:m for m in d['garments']}
    main=next(m for n,m in meshes.items() if n.startswith('FIT_T001'))
    triangles=world(main)[np.asarray(main['triangles']).reshape(-1,3)]
    def back(x,y):
        a=triangles[:,0];u=triangles[:,1]-a;v=triangles[:,2]-a
        delta=np.array([x,y])-a[:,:2];den=u[:,0]*v[:,1]-u[:,1]*v[:,0]
        good=abs(den)>1e-12;den=np.where(good,den,1.)
        s=(delta[:,0]*v[:,1]-delta[:,1]*v[:,0])/den;t=(u[:,0]*delta[:,1]-u[:,1]*delta[:,0])/den
        good&=(s>=-1e-6)&(t>=-1e-6)&(s+t<=1.000001)
        z=a[:,2]+s*u[:,2]+t*v[:,2];z=z[good]
        return float(z.min()) if len(z) else None
    rows=[]
    for name,m in meshes.items():
        if not name.startswith(('FIT_NEW_Bow','FIT_ACCESSORY_WhaleTail_Body')):continue
        src=np.asarray(m['source_positions']);p=world(m)
        if 'WhaleTail_Body' in name:mask=src[:,1]>src[:,1].max()-1e-5
        elif 'BowTail' in name:mask=src[:,1]>src[:,1].max()-.007
        elif 'BowWing' in name:mask=abs(src[:,0])<.028
        else:mask=np.ones(len(p),dtype=bool)
        values=[1000*(z-q[2]) for q in p[mask] for z in [back(q[0],q[1])] if z is not None]
        assert values,(name,'missing garment ray hits')
        rows.append({'mesh':name,'anchor_samples':int(mask.sum()),'valid_back_rays':len(values),'minimum_depth_gap_mm':min(values),'median_depth_gap_mm':float(np.median(values)),'maximum_depth_gap_mm':max(values)})
    return {'reference':str(path),'pose_source':d.get('pose_source'),'coordinate_handling':'renderer-local BakeMesh transformed by world_matrix','method':'Exact vertical XY barycentric ray intersections with main garment back; positive Z-axis gap means accessory behind dress','mounts':rows,'scope':'Static attachment depth gaps only; not an all-pose body/garment collision verdict'}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--reference',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    r=measure(a.reference)
    with a.out.open('x',encoding='utf8') as f:json.dump(r,f,ensure_ascii=False,indent=2)
    print(json.dumps(r,ensure_ascii=False),flush=True)
