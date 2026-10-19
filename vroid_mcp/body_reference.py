"""Validate captured body geometry before publishing a fitting reference."""
from __future__ import annotations
import math

def _number(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError('Body reference contains a non-finite or non-numeric value')
    return value

def validate_body_reference(data: dict, expected_model: str) -> dict:
    if data.get('schema')!='vroid-body-reference-v1' or data.get('model_token')!=expected_model:
        raise ValueError('Body reference schema/model identity mismatch')
    height=_number(data.get('height_cm'))
    if not 50<height<300:raise ValueError('Unexpected reference height')
    nodes=data.get('nodes',[]);meshes=data.get('meshes',[])
    if not 1<=len(nodes)<=4096 or not 1<=len(meshes)<=16:raise ValueError('Reference size limit')
    by_id={n['id']:n for n in nodes}
    if len(by_id)!=len(nodes) or any(type(i) is not int or i<0 for i in by_id):raise ValueError('Invalid or duplicate node identity')
    def matrix(value):
        if len(value)!=4 or any(len(row)!=4 for row in value):raise ValueError('Invalid reference matrix')
        for row in value:
            for x in row:_number(x)
        if max(abs(a-b) for a,b in zip(value[3],[0,0,0,1]))>1e-5:raise ValueError('Non-affine reference matrix')
    for n in nodes:
        matrix(n['world_matrix']);seen={n['id']};parent=n['parent']
        while parent is not None:
            if parent not in by_id or parent in seen:raise ValueError('Missing ancestor or cyclic reference skeleton')
            seen.add(parent);parent=by_id[parent]['parent']
    names=[m['name'] for m in meshes]
    if len(set(names))!=len(names) or not {'Body','Face','Hand','Foot'}<=set(names):raise ValueError('Missing or duplicated body renderers')
    total_vertices=0;total_triangles=0
    for mesh in meshes:
        count=len(mesh['positions']);total_vertices+=count
        if not 1<=count<=100000 or mesh['node_id'] not in by_id:raise ValueError('Invalid mesh identity/count')
        matrix(mesh['world_matrix'])
        if len(mesh['weights'])!=count or len(mesh['uv0']) not in (0,count):raise ValueError('Reference stream count mismatch')
        for p in mesh['positions']:
            if len(p)!=3:raise ValueError('Invalid position')
            for x in p:_number(x)
        for uv in mesh['uv0']:
            if len(uv)!=2:raise ValueError('Invalid UV')
            for x in uv:_number(x)
        indices=mesh['triangles']
        if len(indices)%3 or any(type(i) is not int or not 0<=i<count for i in indices):raise ValueError('Triangle index outside mesh')
        total_triangles+=len(indices)//3
        bones=mesh['bone_nodes']
        if not bones or any(b not in by_id for b in bones):raise ValueError('Unknown skin bone')
        for w in mesh['weights']:
            if len(w['indices'])!=4 or len(w['weights'])!=4:raise ValueError('Expected four skin influence slots')
            if any(type(i) is not int or not 0<=i<len(bones) for i in w['indices']):raise ValueError('Skin bone index outside map')
            weights=[_number(x) for x in w['weights']]
            if min(weights)<0 or max(weights)>1 or abs(sum(weights)-1)>1e-3:raise ValueError('Invalid/non-normalized skin weights')
    return {'schema':data['schema'],'model_token':data['model_token'],'height_cm':height,
            'mesh_names':names,'meshes':len(meshes),'skeleton_nodes':len(nodes),
            'vertices':total_vertices,'triangles':total_triangles}
