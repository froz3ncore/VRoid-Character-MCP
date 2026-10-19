"""Cross-check smooth-normal screening against face normals and ray parity."""
import bpy,json,sys
from pathlib import Path
from mathutils import Matrix,Vector
from mathutils.bvhtree import BVHTree
ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'projects/whale-maid/rear-skirt-contact-v03-20261017/skinning-diagnosis.json'
d=json.loads(path.read_text(encoding='utf8'));results=[]
for record in d['results'][:2]:
    ref=json.loads((ROOT/record['reference']).read_text(encoding='utf8'));body=ref['body'];m=Matrix(body['world_matrix'])
    pts=[m@Vector(p) for p in body['positions']];faces=[tuple(body['triangles'][k:k+3]) for k in range(0,len(body['triangles']),3)]
    tree=BVHTree.FromPolygons(pts,faces,all_triangles=True)
    rows=[]
    for row in record['bad_vertices']:
        p=Vector(row['posed_position']);q,n,idx,dist=tree.find_nearest(p)
        parity=[]
        for direction in [Vector((1,.123,.071)).normalized(),Vector((.137,1,.093)).normalized(),Vector((.173,.137,1)).normalized()]:
            origin=p.copy();count=0
            for _ in range(100):
                hit,normal,face,distance=tree.ray_cast(origin,direction,5)
                if hit is None:break
                count+=1;origin=hit+direction*1e-5
            parity.append(count%2)
        rows.append({'source_vertex':row['source_vertex'],'smooth_depth':row['depth_m'],'face_signed':(p-q).dot(n),
            'nearest_body_point':list(q),'distance':dist,'parity_inside_votes':sum(parity)})
    results.append({'reference':record['reference'],'vertices':rows,'all_three_rays_inside':sum(r['parity_inside_votes']==3 for r in rows),
        'all_three_rays_outside':sum(r['parity_inside_votes']==0 for r in rows),'mixed_votes':sum(0<r['parity_inside_votes']<3 for r in rows)})
out=path.with_name('surface-sign-check.json');assert not out.exists();out.write_text(json.dumps(results,indent=2),encoding='utf8')
for r in results:print(json.dumps({k:v for k,v in r.items() if k!='vertices'}));print(r['vertices'][:4])
