"""Structural guards for native wearable skin references used by inverse fitting."""
import math

def validate_wear_reference(data):
    if data.get('schema')!='vroid-wear-reference-v1':raise ValueError('Unexpected wear reference schema')
    bones=data['bones']
    if not bones or len(bones)>32768 or {b['id'] for b in bones}!=set(range(len(bones))):raise ValueError('Invalid bone table')
    def matrix(m):
        if len(m)!=4 or any(len(r)!=4 for r in m) or not all(math.isfinite(v) for r in m for v in r):raise ValueError('Invalid skin matrix')
        if any(abs(m[3][i]-(1 if i==3 else 0))>1e-4 for i in range(4)):raise ValueError('Non-affine skin matrix')
    for b in bones:matrix(b['world_matrix'])
    def vector(v):
        if len(v)!=3 or not all(math.isfinite(x) for x in v):raise ValueError('Invalid collision vector')
    for collider in data.get('colliders',[]):
        matrix(collider['world_matrix'])
        if not math.isfinite(collider['radius']) or not 0<=collider['radius']<=2:raise ValueError('Invalid collider radius')
        for key in ('offset','tail','world_offset','world_tail'):vector(collider[key])
        for local,world in (('offset','world_offset'),('tail','world_tail')):
            expected=[sum(a*b for a,b in zip(row,collider[local]+[1])) for row in collider['world_matrix'][:3]]
            if max(abs(a-b) for a,b in zip(expected,collider[world]))>1e-5:raise ValueError('Collider world/local mismatch')
    for bone in data.get('spring_bones',[]):
        matrix(bone['world_matrix']);vector(bone['position'])
        if max(abs(bone['position'][i]-bone['world_matrix'][i][3]) for i in range(3))>1e-5:raise ValueError('Spring position/matrix mismatch')
    garments=data['garments']
    if not garments or len(garments)>128 or len({g['name'] for g in garments})!=len(garments):raise ValueError('Invalid wearable mesh list')
    total=0
    base_meshes=data.get('base_meshes',[])
    if len(base_meshes)>4 or len({m['name'] for m in base_meshes})!=len(base_meshes) or any(m['name'] not in ('Body','Foot','Face','Hair') for m in base_meshes):raise ValueError('Invalid base mesh list')
    for mesh in [data['body'],*garments,*base_meshes]:
        positions=mesh['positions'];n=len(positions);total+=n
        if n<1 or any(len(p)!=3 or not all(math.isfinite(v) for v in p) for p in positions):raise ValueError('Invalid baked positions')
        normals=mesh['normals']
        if len(normals)!=n or any(len(p)!=3 or not all(math.isfinite(v) for v in p) for p in normals):raise ValueError('Invalid baked normals')
        matrix(mesh['world_matrix'])
        triangles=mesh['triangles']
        if len(triangles)%3 or any(type(i) is not int or not 0<=i<n for i in triangles):raise ValueError('Invalid wearable triangles')
        if mesh is data['body']:continue
        if len(mesh['source_positions'])!=n or len(mesh['uv0'])!=n or len(mesh['weights'])!=n:raise ValueError('Skin stream count mismatch')
        for p in mesh['source_positions']:
            if len(p)!=3 or not all(math.isfinite(v) for v in p):raise ValueError('Invalid source positions')
        for uv in mesh['uv0']:
            if len(uv)!=2 or not all(math.isfinite(v) for v in uv):raise ValueError('Invalid wearable UV')
        ids=mesh['bone_ids'];bindposes=mesh['bindposes']
        if len(ids)!=len(bindposes) or not ids or any(type(i) is not int or not 0<=i<len(bones) for i in ids):raise ValueError('Invalid mesh bone table')
        for m in bindposes:matrix(m)
        for w in mesh['weights']:
            if len(w['indices'])!=4 or len(w['weights'])!=4:raise ValueError('Expected four skin slots')
            if not all(math.isfinite(v) and v>=0 for v in w['weights']) or abs(sum(w['weights'])-1)>1e-3:raise ValueError('Invalid skin weights')
            if any(type(i) is not int or not 0<=i<len(ids) for i in w['indices']):raise ValueError('Invalid skin indices')
    if total>300000:raise ValueError('Wearable reference too large')
