"""Trace captured rear-skirt intersections to source vertices and spring chains.

Read-only on the Blender source. This is nearest-normal screening, not exact
cloth contact. Every native sample is checked against source positions, UVs,
weights and reconstructed skinning before attribution.
"""
import argparse
from collections import Counter, defaultdict
import importlib.util
import json
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('garment_fit', ROOT/'blender-addons/vroid_xwear_direct/fit.py')
fit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fit)
COORD = Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1)))


def diagnose(path, obj):
    data = json.loads(path.read_text(encoding='utf8'))
    assert data['pose_source'] == 'native_preview'
    garment = next(g for g in data['garments'] if g['name'] == obj.name)
    mapping, uvs = fit.export_map(obj, COORD)
    assert len(mapping) == len(garment['positions'])
    transform = COORD @ obj.matrix_world
    selected = {i for i,p in enumerate(garment['source_positions']) if -.8 < p[2] < -.05 and .3 < p[1] < .93}
    source_error = max((transform@obj.data.vertices[mapping[i]].co-Vector(garment['source_positions'][i])).length for i in selected)
    assert source_error < 2e-6, source_error
    assert max(abs(a-b) for uv,raw in zip(uvs,garment['uv0']) for a,b in zip(uv,raw)) < 1e-6
    bone_names = [data['bones'][i]['name'] for i in garment['bone_ids']]
    matrices = [Matrix(data['bones'][i]['world_matrix'])@Matrix(bind) for i,bind in zip(garment['bone_ids'],garment['bindposes'])]
    world = Matrix(garment['world_matrix'])
    posed = [world@Vector(p) for p in garment['positions']]
    influences = []
    reconstruction = 0.
    for i,weights in enumerate(garment['weights']):
        named = defaultdict(float)
        reconstructed = Vector()
        for bone,weight in zip(weights['indices'],weights['weights']):
            if weight > 1e-7:
                named[bone_names[bone]] += weight
                reconstructed += (matrices[bone]@Vector(garment['source_positions'][i]))*weight
        influences.append(dict(named))
        if i in selected:
            expected = {obj.vertex_groups[g.group].name:g.weight for g in obj.data.vertices[mapping[i]].groups if g.weight > 1e-7}
            assert expected.keys() == named.keys() and all(abs(expected[k]-named[k]) < 1e-5 for k in expected)
            reconstruction = max(reconstruction,(reconstructed-posed[i]).length)
    assert reconstruction < 2e-5, reconstruction
    surface = fit.Surface(data['body'])
    def hit(point):
        normal,signed,distance = surface.nearest(point)
        return -signed if signed < -.003 and distance < .12 else 0.
    bad = {}
    for i in selected:
        depth = hit(posed[i])
        if depth:
            bad[i] = {'export_vertex':i,'source_vertex':mapping[i],'source_position':garment['source_positions'][i],
                      'posed_position':list(posed[i]),'depth_m':depth,'weights':influences[i]}
    faces = [tuple(garment['triangles'][k:k+3]) for k in range(0,len(garment['triangles']),3)]
    faces = [t for t in faces if all(i in selected for i in t)]
    edges = {tuple(sorted((a,b))) for t in faces for a,b in zip(t,t[1:]+t[:1])}
    bad_faces = []
    bad_edges = []
    for target,samples in ((bad_faces,faces),(bad_edges,edges)):
        for ids in samples:
            depth = hit(sum((posed[i] for i in ids),Vector())/len(ids))
            if depth:
                target.append({'export_vertices':ids,'source_vertices':[mapping[i] for i in ids],
                    'depth_m':depth,'inside_vertex_count':sum(i in bad for i in ids),
                    'max_source_span_m':max((Vector(garment['source_positions'][a])-Vector(garment['source_positions'][b])).length for a in ids for b in ids)})
    chain_totals = Counter()
    non_spring = Counter()
    for row in bad.values():
        for name,weight in row['weights'].items():
            if name.startswith('WM_Skirt_'):
                chain_totals['_'.join(name.split('_')[:3])] += weight
            else:
                non_spring[name] += weight
    controls = {b['name']:b for b in data.get('spring_bones',[]) if b['name'].startswith('WM_Skirt_')}
    colliders = [c for c in data.get('colliders',[]) if c['name'].startswith('WM_XWearCollider_')]
    clearances = []
    for name,bone in controls.items():
        if not name.startswith(tuple('WM_Skirt_%02d_'%i for i in range(4,9))):
            continue
        point = Vector(bone['position'])
        values = []
        for collider in colliders:
            a,b = Vector(collider['world_offset']),Vector(collider['world_tail'])
            kind = next(v['value'] for v in collider['type_fields'] if v['name']=='ColliderType')
            t = max(0,min(1,(point-a).dot(b-a)/max((b-a).length_squared,1e-12))) if kind=='Capsule' else 0
            values.append({'collider':collider['name'],'clearance_to_surface_m':(point-(a+(b-a)*t)).length-collider['radius']})
        clearances.append({'bone':name,'position':list(point),'nearest_collider':min(values,key=lambda v:v['clearance_to_surface_m'])})
    return {'reference':str(path),'frame':data['frame'],'source_error_m':source_error,'skin_reconstruction_error_m':reconstruction,
        'selected_export_vertices':len(selected),'selected_source_vertices':len({mapping[i] for i in selected}),
        'screening':{'vertices':len(bad),'face_centres':len(bad_faces),'edge_midpoints':len(bad_edges)},
        'bad_unique_source_vertices':len({mapping[i] for i in bad}),
        'weighted_chain_totals':dict(chain_totals),'weighted_non_spring_totals':dict(non_spring),
        'inside_faces_with_all_corners_outside':sum(r['inside_vertex_count']==0 for r in bad_faces),
        'inside_edges_with_both_ends_outside':sum(r['inside_vertex_count']==0 for r in bad_edges),
        'worst_vertices':sorted(bad.values(),key=lambda r:-r['depth_m'])[:40],
        'bad_vertices':list(bad.values()),'bad_faces':bad_faces,'bad_edges':bad_edges,
        'rear_controls':clearances,'colliders':colliders}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reference',type=Path,action='append',required=True)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    assert not args.out.exists()
    source = Path(bpy.data.filepath)
    original_hash = fit.digest(source)
    obj = next(o for o in bpy.data.objects if o.name.startswith('FIT_T001'))
    rig = obj.modifiers[0].object
    spring = rig.data.vrm_addon_extension.spring_bone1
    config = [{'name':s.vrm_name,'groups':[g.collider_group_uuid for g in s.collider_groups],
        'joints':[{'bone':j.node.bone_name,'radius':j.hit_radius,'stiffness':j.stiffness,'drag':j.drag_force,
            'gravity':j.gravity_power,'rest_head':list(COORD@rig.matrix_world@rig.data.bones[j.node.bone_name].head_local)} for j in s.joints]}
        for s in spring.springs]
    results = [diagnose(p,obj) for p in args.reference]
    report = {'source':str(source),'source_sha256':original_hash,'spring_config':config,'results':results,
        'scope':'Verified source/native correspondence; nearest-normal screening only; no full motion or exact contact proof'}
    fit.write_new(args.out,report)
    assert fit.digest(source)==original_hash
    for r in results:
        print(json.dumps({k:r[k] for k in ('reference','screening','bad_unique_source_vertices','weighted_chain_totals','weighted_non_spring_totals','inside_faces_with_all_corners_outside','inside_edges_with_both_ends_outside')},ensure_ascii=False))


if __name__=='__main__':
    main()
