"""Measure native skin deformation and fit corrections back to editable Blender meshes."""
import bpy,bmesh,json,math,hashlib
from pathlib import Path
from mathutils import Matrix,Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import barycentric_transform
ROOT=Path('D:/vroidmcp');OUT=ROOT/'projects/whale-maid/target-fit-v02'
REF=ROOT/'projects/whale-maid/clean-wear-v01/actual_worn_fit_reference_v02.json'
C=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1)))

def context():
    data=json.loads(REF.read_text(encoding='utf8'))
    body=data['body'];world=Matrix(body['world_matrix']);normal=world.to_3x3().inverted().transposed()
    points=[world@Vector(p) for p in body['positions']]
    normals=[(normal@Vector(n)).normalized() for n in body['normals']]
    faces=[tuple(body['triangles'][i:i+3]) for i in range(0,len(body['triangles']),3)]
    bvh=BVHTree.FromPolygons(points,faces,all_triangles=True)
    def nearest(p):
        q,_,index,dist=bvh.find_nearest(p)
        if q is None:raise ValueError('Native body BVH lookup failed')
        a,b,c=faces[index]
        n=barycentric_transform(q,points[a],points[b],points[c],normals[a],normals[b],normals[c]).normalized()
        return q,n,(p-q).dot(n)
    return data,nearest

def export_vertex_map(obj):
    mesh=obj.data;mesh.calc_loop_triangles();cache={};indices=[];uvs=[]
    normal=(C@obj.matrix_world).to_3x3().inverted().transposed()
    for tri in mesh.loop_triangles:
        if tri.area<=1e-12:continue
        loops=list(tri.loops)
        if (C@obj.matrix_world).to_3x3().determinant()<0:loops.reverse()
        for loop_index in loops:
            loop=mesh.loops[loop_index];uv=tuple(mesh.uv_layers.active.data[loop_index].uv)
            n=tuple((normal@mesh.corner_normals[loop_index].vector).normalized());key=(loop.vertex_index,uv,n)
            if key not in cache:cache[key]=len(indices);indices.append(loop.vertex_index);uvs.append(uv)
    return indices,uvs

def analyze():
    data,nearest=context();records=[]
    for garment in data['garments']:
        obj=bpy.data.objects[garment['name']];mapping,uvs=export_vertex_map(obj)
        assert len(mapping)==len(garment['positions']),(obj.name,len(mapping),len(garment['positions']))
        assert max(abs(a-b) for a_uv,b_uv in zip(uvs,garment['uv0']) for a,b in zip(a_uv,b_uv))<1e-6,'Export/native vertex order differs'
        bones=[Matrix(data['bones'][i]['world_matrix'])@Matrix(bind) for i,bind in zip(garment['bone_ids'],garment['bindposes'])]
        world=Matrix(garment['world_matrix']);bad=[];max_reconstruction=0;max_source=0;skin_matrices=[]
        for i,(raw,baked,weights) in enumerate(zip(garment['source_positions'],garment['positions'],garment['weights'])):
            skin=Matrix(((0,0,0,0),)*4)
            for bone,w in zip(weights['indices'],weights['weights']):
                if w:skin+=bones[bone]*w
            actual=world@Vector(baked);predicted=skin@Vector(raw)
            max_reconstruction=max(max_reconstruction,(actual-predicted).length)
            original=C@obj.matrix_world@obj.data.vertices[mapping[i]].co
            max_source=max(max_source,(original-Vector(raw)).length)
            q,n,signed=nearest(actual)
            if signed<-.002:bad.append({'native_vertex':i,'blender_vertex':mapping[i],'signed_m':signed,'world_position':list(actual)})
        face_bad=[];edge_bad=set();posed=[world@Vector(p) for p in garment['positions']]
        for offset in range(0,len(garment['triangles']),3):
            ids=garment['triangles'][offset:offset+3];p=sum((posed[i] for i in ids),Vector())/3
            q,n,signed=nearest(p)
            if signed<-.002:face_bad.append({'triangle':offset//3,'blender_vertices':[mapping[i] for i in ids],'signed_m':signed})
            for a,b in zip(ids,ids[1:]+ids[:1]):
                if nearest((posed[a]+posed[b])*.5)[2]<-.002:edge_bad.add(tuple(sorted((mapping[a],mapping[b]))))
        records.append({'name':obj.name,'native_vertices':len(mapping),'inside_vertices':len(bad),
            'deepest_m':min((b['signed_m'] for b in bad),default=0),
            'max_skin_reconstruction_error_m':max_reconstruction,'max_source_position_error_m':max_source,
            'inside_face_centers':len(face_bad),'inside_edge_midpoints':len(edge_bad),
            'deepest_face_m':min((f['signed_m'] for f in face_bad),default=0),
            'bad_vertices':bad,'bad_faces':face_bad,'bad_edges':[list(e) for e in edge_bad]})
    OUT.mkdir(exist_ok=True)
    (OUT/'native-fit-diagnosis.json').write_text(json.dumps({'records':records,'scope':'Actual native stopped pose; not continuous animation'},ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps([{k:v for k,v in r.items() if k not in ('bad_vertices','bad_faces','bad_edges')} for r in records],ensure_ascii=False))

def refine():
    expected=ROOT/'projects/whale-maid/target-fit-v01/whale_maid_target_fit_v01.blend'
    destination=OUT/'whale_maid_target_fit_v02.blend'
    if Path(bpy.data.filepath)!=expected or destination.exists():raise ValueError('Expected preserved v01 input and a new v02 output')
    data,nearest=context();OUT.mkdir(exist_ok=True)
    body_hash=lambda:hashlib.sha256(json.dumps({o.name:[list(v.co) for v in o.data.vertices] for o in bpy.data.objects if o.name.startswith('REF_VRoid_')},sort_keys=True).encode()).hexdigest()
    before_body=body_hash()
    old=bpy.context.preferences.filepaths.save_version
    rig=bpy.data.objects['WM_TargetVRoidRig_v01'];rig.data.vrm_addon_extension.spring_bone1.enable_animation=False
    for pb in rig.pose.bones:pb.matrix_basis.identity()
    try:
        bpy.context.preferences.filepaths.save_version=0
        bpy.ops.wm.save_as_mainfile(filepath=str(destination),relative_remap=False,compress=True)
        records=[]
        for g in data['garments']:
            obj=bpy.data.objects[g['name']];mesh=obj.data
            native={data['bones'][i]['name']:Matrix(data['bones'][i]['world_matrix'])@Matrix(bind) for i,bind in zip(g['bone_ids'],g['bindposes'])}
            if len(native)!=len(g['bone_ids']):raise ValueError('Ambiguous native skin bone names')
            def skin(v):
                m=Matrix(((0,0,0,0),)*4)
                for group in v.groups:
                    name=obj.vertex_groups[group.group].name
                    if name in native and group.weight>0:m+=native[name]*group.weight
                return m
            def posed(v):return skin(v) @ (C@obj.matrix_world@v.co)
            before_vertices=len(mesh.vertices);before_triangles=len(mesh.loop_triangles);steps=[];maximum=0;changed=set()
            for iteration in range(4):
                points=[posed(v) for v in mesh.vertices]
                mesh.calc_loop_triangles();split=set()
                for edge in mesh.edges:
                    a,b=edge.vertices
                    if (points[a]-points[b]).length>.009 and nearest((points[a]+points[b])*.5)[2]<.003:
                        split.add(tuple(sorted((a,b))))
                for tri in mesh.loop_triangles:
                    ids=list(tri.vertices)
                    if nearest(sum((points[i] for i in ids),Vector())/3)[2]<.002:
                        split.update(tuple(sorted((a,b))) for a,b in zip(ids,ids[1:]+ids[:1]))
                if split:
                    bm=bmesh.new();bm.from_mesh(mesh);bm.verts.ensure_lookup_table();bm.edges.ensure_lookup_table()
                    edges=[e for e in bm.edges if tuple(sorted(v.index for v in e.verts)) in split]
                    bmesh.ops.subdivide_edges(bm,edges=edges,cuts=1,use_grid_fill=True)
                    bm.to_mesh(mesh);bm.free();mesh.update()
                # Interpolated deform layers can gain more than four influences.
                for v in mesh.vertices:
                    groups=[(x.group,x.weight) for x in v.groups if obj.vertex_groups[x.group].name in native and x.weight>1e-8]
                    groups.sort(key=lambda p:-p[1]);keep=groups[:4];total=sum(w for _,w in keep)
                    if total<=0:raise ValueError('Unweighted refined vertex')
                    for index,_ in groups:obj.vertex_groups[index].remove([v.index])
                    for index,w in keep:obj.vertex_groups[index].add([v.index],w/total,'REPLACE')
                moved=0
                for v in mesh.vertices:
                    m=skin(v);p=m@(C@obj.matrix_world@v.co);q,n,signed=nearest(p)
                    if signed>=.006:continue
                    target=q+n*.008;delta=target-p
                    if delta.length>.025:continue
                    raw=m.inverted()@target;v.co=obj.matrix_world.inverted()@C.inverted()@raw
                    maximum=max(maximum,delta.length);moved+=1;changed.add(v.index)
                mesh.update();steps.append({'split_edges':len(split),'moved_vertices':moved})
                if not split and not moved:break
            mesh.calc_loop_triangles();points=[posed(v) for v in mesh.vertices]
            bad_v=sum(nearest(p)[2]<-.002 for p in points)
            bad_faces=sum(nearest(sum((points[i] for i in t.vertices),Vector())/3)[2]<-.002 for t in mesh.loop_triangles)
            records.append({'name':obj.name,'vertices_before':before_vertices,'vertices_after':len(mesh.vertices),
                'triangles_before':before_triangles,'triangles_after':len(mesh.loop_triangles),'steps':steps,
                'moved_vertices':len(changed),'max_single_step_world_delta_m':maximum,'inside_vertices_after':bad_v,'inside_face_centers_after':bad_faces})
        assert body_hash()==before_body,'Body geometry changed'
        rig.data.vrm_addon_extension.spring_bone1.enable_animation=True
        bpy.ops.wm.save_as_mainfile(filepath=str(destination),relative_remap=False,compress=True)
    finally:bpy.context.preferences.filepaths.save_version=old
    report={'file':str(destination),'reference_sha256':hashlib.sha256(REF.read_bytes()).hexdigest(),
        'body_unchanged':True,'source_v01_preserved':True,'records':records,
        'scope':'Inverse fitting from actual native stopped T pose; native reimport and animation separate'}
    (OUT/'native-fit-refinement.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False))
