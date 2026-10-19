"""Actual native rear-skirt screening and control-point/capsule contact distances."""
import argparse,json,math,sys
from pathlib import Path
from mathutils import Matrix,Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import barycentric_transform

def analyze(path,hit_radius):
    data=json.loads(path.read_text(encoding='utf8'));body=data['body'];world=Matrix(body['world_matrix'])
    points=[world@Vector(p) for p in body['positions']];nm=world.to_3x3().inverted().transposed()
    normals=[(nm@Vector(n)).normalized() for n in body['normals']]
    faces=[tuple(body['triangles'][i:i+3]) for i in range(0,len(body['triangles']),3)]
    tree=BVHTree.FromPolygons(points,faces,all_triangles=True)
    def signed(point):
        q,_,index,distance=tree.find_nearest(point);a,b,c=faces[index]
        normal=barycentric_transform(q,points[a],points[b],points[c],normals[a],normals[b],normals[c]).normalized()
        return (point-q).dot(normal),distance
    garment=data['garments'][0];posed=[Matrix(garment['world_matrix'])@Vector(p) for p in garment['positions']]
    selected={i for i,p in enumerate(garment['source_positions']) if -.8<p[2]<-.05 and .3<p[1]<.93}
    triangles=[tuple(garment['triangles'][i:i+3]) for i in range(0,len(garment['triangles']),3)]
    triangles=[t for t in triangles if all(i in selected for i in t)]
    edges={tuple(sorted((a,b))) for t in triangles for a,b in zip(t,t[1:]+t[:1])}
    screening={}
    for name,samples in [('vertices',[posed[i] for i in selected]),
        ('face_centres',[sum((posed[i] for i in t),Vector())/3 for t in triangles]),
        ('edge_midpoints',[(posed[a]+posed[b])*.5 for a,b in edges])]:
        bad=[]
        for p in samples:
            depth,distance=signed(p)
            if depth<-.003 and distance<.12:bad.append(-depth)
        screening[name]={'samples':len(samples),'inside':len(bad),'max_depth_m':max(bad,default=0)}
    colliders=[c for c in data.get('colliders',[]) if c['name'].startswith('WM_XWearCollider_')]
    controls=[]
    for bone in data.get('spring_bones',[]):
        name=bone['name']
        if not name.startswith(tuple('WM_Skirt_%02d_'%i for i in range(4,9))) or name.endswith('_00'):continue
        point=Vector(bone['position']);clearances=[]
        for collider in colliders:
            kind=next(v['value'] for v in collider['type_fields'] if v['name']=='ColliderType')
            a=Vector(collider['world_offset']);b=Vector(collider['world_tail'])
            t=max(0,min(1,(point-a).dot(b-a)/max((b-a).length_squared,1e-12))) if kind=='Capsule' else 0
            clearances.append({'collider':collider['name'],'clearance_m':(point-(a+(b-a)*t)).length-collider['radius']-hit_radius})
        controls.append({'bone':name,'position':bone['position'],'minimum_clearance':min(clearances,key=lambda c:c['clearance_m'])})
    hips=next(b for b in data['bones'] if b['name']=='J_Bip_C_Hips')['world_matrix'][2][3]
    hem=sorted(posed[i].z-hips for i in selected if garment['source_positions'][i][1]<.55)
    result={'path':str(path),'screening':screening,'rear_hem_z_relative_hips_m':{'min':min(hem),'median':hem[len(hem)//2],'max':max(hem)},
        'colliders':len(colliders),'rear_controls':controls,'scope':'One native fixed pose; nearest-normal screening; no all-animation collision proof'}
    target=path.with_suffix('.rear-contact.json');assert not target.exists();target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='rear_controls'},ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--hit-radius',type=float,default=.0062);p.add_argument('paths',nargs='+',type=Path)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);assert .001<=a.hit_radius<=.04
    for path in a.paths:analyze(path,a.hit_radius)
