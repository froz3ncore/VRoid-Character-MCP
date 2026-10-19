"""Propose a bounded native Body mask under the existing shoe arch.

Uses the same-frame actual shoe/Foot geometry. It never writes to VRoid.
Side/downward rays locate low arch leakage. The legacy side-profile mode is
retained for reproducing the inadequate two-vertex diagnostic proposal.
New mask boundaries and nearest-shoe distances must be reviewed independently.
"""
import argparse, json, sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'VRoid-MCP'))
from vroid_mcp.wear_fit import world, triangles, Surface
from vroid_mcp.wear_occlusion import geometry_hash

def main(a):
    data=json.loads(a.reference.read_text(encoding='utf8'));state=json.loads(a.mask_state.read_text(encoding='utf8'))
    assert data['pose_source']=='native_edit' and not state['hidden_vertices']
    body=next(m for m in data['base_meshes'] if m['name']=='Body');positions=np.asarray(world(body))
    assert len(positions)==state['default_vertex_count']
    assert geometry_hash(body['source_positions'],body['triangles'])==state['source_geometry_sha256']
    faces=np.asarray(body['triangles']).reshape(-1,3);selected=[];rows=[]
    for side in ['L','R']:
        shoe=next(m for m in data['garments'] if m['name']=='FIT_ACCESSORY_Shoe_'+side+('_T005' if side=='L' else '_T004'))
        surface=np.asarray(triangles(shoe,world(shoe)));foot='J_Bip_'+side+'_Foot';samples=[]
        tree=Surface(surface.tolist())
        for i,(p,weight) in enumerate(zip(positions,body['weights'])):
            mass=sum(w for b,w in zip(weight['indices'],weight['weights']) if data['bones'][body['bone_ids'][b]]['name']==foot)
            if mass<.9 or p[1]>.085:continue
            if a.method=='visible-arch':
                normal=np.asarray(body['normals'][i]);matrix=np.asarray(body['world_matrix'])[:3,:3]
                normal=np.linalg.inv(matrix).T@normal;length=np.linalg.norm(normal)
                if length<1e-12:continue
                normal/=length
                if p[1]>.060 or not -.070<p[2]<.035 or normal[1]>.4:continue
                direction=(1 if normal[0]>=0 else -1,0,0) if abs(normal[0])>.35 else (0,-1,0)
                distance=tree.distance(p)
                if tree.ray(p,direction) is None and distance<.008:
                    selected.append(i);samples.append({'index':i,'position_world_m':p.tolist(),'outward_test_direction':list(direction),'nearest_shoe_distance_mm':distance*1000})
                continue
            # Intersect shoe triangles with the transverse z plane. The lower
            # projected silhouette is an explicit side-view arch threshold.
            points=[]
            for j in range(3):
                start=surface[:,j,:];end=surface[:,(j+1)%3,:];den=end[:,2]-start[:,2]
                hit=(np.minimum(start[:,2],end[:,2])<=p[2])&(np.maximum(start[:,2],end[:,2])>=p[2])&(np.abs(den)>1e-10)
                t=(p[2]-start[hit,2])/den[hit]
                points.extend((start[hit,1]+t*(end[hit,1]-start[hit,1])).tolist())
            if points and p[1]<min(points)+.002:
                # An arch gap must be above the sole ground plane; do not
                # turn this into a general foot/ankle or toe-top mask.
                if min(points)<surface[:,:,1].min()+.012:continue
                selected.append(i);samples.append({'index':i,'position_world_m':p.tolist(),'profile_floor_y_m':min(points)})
        rows.append({'side':side,'vertices':samples})
    # UV seams can duplicate one physical body point. Hide all coincident
    # copies of a selected point so an adjacent seam triangle cannot remain.
    if a.method=='visible-arch':
        assert selected,'No eligible low-arch surface points in this capture'
        points=positions[selected]
        selected=sorted(set(selected)|{i for i,p in enumerate(positions) if np.min(np.linalg.norm(points-p,axis=1))<1e-7})
    selected=sorted(selected);assert selected and len(selected)<=64,len(selected)
    removed=np.any(np.isin(faces,selected),axis=1)
    def edges(fs):
        result={}
        for f in fs:
            for x,y in zip(f,np.roll(f,-1)):
                edge=tuple(sorted((int(x),int(y))));result[edge]=result.get(edge,0)+1
        return result
    old_edges=edges(faces);kept_edges=edges(faces[~removed]);new=[e for e,n in kept_edges.items() if n==1 and old_edges[e]>1]
    shoe_surface=Surface([tri for m in data['garments'] for tri in triangles(m,world(m))]);boundary=[]
    for x,y in new:
        ps=[positions[x],positions[y],(positions[x]+positions[y])*.5]
        boundary.append({'edge':[x,y],'maximum_nearest_shoe_distance_mm':max(shoe_surface.distance(p) for p in ps)*1000})
    result={'source_geometry_sha256':state['source_geometry_sha256'],'default_vertex_count':state['default_vertex_count'],
        'hidden_vertices':selected,'reference':str(a.reference.resolve()),'reference_frame':data['frame'],
        'method':a.method,
        'selection':('Foot-weight >=0.9; y<=60mm; -70<z<35mm; normal.y<=0.4; side/downward ray has no shoe hit; nearest shoe <8mm; include coincident UV copies' if a.method=='visible-arch' else 'Foot-weight >=0.9, below 85mm, below actual main-shoe side arch floor +2mm; elevated arch only'),
        'selected_by_side':rows,'removed_body_triangles':int(removed.sum()),'new_boundary_edges':boundary,
        'maximum_boundary_shoe_distance_mm':max(r['maximum_nearest_shoe_distance_mm'] for r in boundary),
        'applied':False,'native_cold_reopen_passed':False,'scope':'Explicit independent Body occlusion proposal. Hiding is not geometric enclosure or unrestricted motion proof.'}
    with a.out.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({'vertices':len(selected),'removed_triangles':int(removed.sum()),'maximum_boundary_distance_mm':result['maximum_boundary_shoe_distance_mm']}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--reference',type=Path,required=True);p.add_argument('--mask-state',type=Path,required=True)
    p.add_argument('--method',choices=['side-profile','visible-arch'],default='visible-arch')
    p.add_argument('--out',type=Path,required=True);main(p.parse_args())
