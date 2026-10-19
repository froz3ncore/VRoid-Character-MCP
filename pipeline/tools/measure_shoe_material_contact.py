"""Exact visible-foot contact against independently verified closed shoe solids."""
import argparse,json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'VRoid-MCP'))
from vroid_mcp.wear_fit import selected_surface,world,triangles,Surface
from measure_exact_contact import winding_number,tri_tri_intersect
def measure(reference,check):
    data=json.loads(reference.read_text(encoding='utf8'));source=json.loads(check.read_text(encoding='utf8'));assert source['passed'];feet,_=selected_surface(data,'feet');rows=[]
    for solid in source['closed_main_shoes']:
        mesh=next(m for m in data['garments'] if m['name']==solid['mesh']);side=mesh['name'].split('_')[3];faces=np.asarray(triangles(mesh,world(mesh)));assert len(faces)==solid['triangles'];points=np.asarray(feet[side]['points']);body_faces=np.asarray(feet[side]['triangles']);surface=Surface(faces.tolist())
        w=winding_number(points,faces,chunk=32);inside=np.flatnonzero(abs(w)>.5);distances=[surface.distance(points[i]) for i in inside];deep=[(int(i),d) for i,d in zip(inside,distances) if d>.0001]
        low=faces.min(axis=1);high=faces.max(axis=1);hits=[]
        for i,tri in enumerate(body_faces):
            candidates=np.flatnonzero(np.all(high>=tri.min(axis=0)-1e-8,axis=1)&np.all(low<=tri.max(axis=0)+1e-8,axis=1))
            hits.extend((i,int(j)) for j in candidates if tri_tri_intersect(tri,faces[j]))
        rows.append({'side':side,'mesh':mesh['name'],'visible_foot_vertices':len(points),'visible_foot_triangles':len(body_faces),'inside_shoe_material_over_0_1mm':len(deep),'maximum_material_depth_mm':max((d*1000 for _,d in deep),default=0.),'intersecting_visible_foot_triangles':len({i for i,j in hits}),'intersecting_shoe_triangles':len({j for i,j in hits}),'inside_points_world_m':[points[i].tolist() for i,d in deep]})
    return {'reference':str(reference),'frame':data['frame'],'base_body_occlusion':data.get('base_body_occlusion'),'results':rows,'method':'Generalized winding and exact distance against cold-verified closed leather/outsole material solids, plus exact triangle intersections of the actual visible Foot/Toe-weighted skin. The instep cavity is outside the leather solid.','scope':'Only current visible skinned foot versus two main shoe solids in this pose; excluded skin, strap/gold contacts, seam appearance, all-animation collision and Godot are not certified.'}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--reference',type=Path,required=True);p.add_argument('--source-check',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();result=measure(a.reference,a.source_check)
    with a.out.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({'results':result['results']},ensure_ascii=False),flush=True)
