"""Calibrate saved outfit bind geometry to the actual Dress-up base skeleton.

The editable/native VRoid surfaces use different poses and shoe-height offsets.
This uses actual captured Body bone matrices, updates bind geometry by linear
skinning, and preserves topology, UVs, weights and physical settings.
"""
import argparse,hashlib,importlib.util,json,math,sys
from pathlib import Path
import bpy
from mathutils import Matrix,Vector
ROOT=Path(__file__).resolve().parents[1]
C=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1)));CI=C.inverted();RIG='WM_TargetVRoidRig_v01'
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):
    with p.open('x',encoding='utf8') as f:json.dump(d,f,ensure_ascii=False,indent=2)
def build(a):
    source=Path(bpy.data.filepath).resolve();source_sha=digest(source);out=a.out.resolve()
    previous=json.loads((source.parent/'build.json').read_text(encoding='utf8'));assert previous['copy_sha256']==source_sha and not bpy.data.is_dirty
    assert not out.exists() and out.is_relative_to(ROOT/'projects/whale-maid')
    data=json.loads(a.reference.read_text(encoding='utf8'));assert data['pose_source']=='native_edit'
    base=data['base_meshes'];assert any(m['name']=='Body' for m in base)
    target={}
    for mesh in base:
        for i in mesh['bone_ids']:
            b=data['bones'][i];matrix=Matrix(b['world_matrix'])
            assert max(abs(s-1) for s in matrix.to_scale())<2e-4,(b['name'],list(matrix.to_scale()))
            if b['name'] in target:assert max(abs(a-b) for ra,rb in zip(matrix,target[b['name']]) for a,b in zip(ra,rb))<1e-5
            target[b['name']]=matrix
    rig=bpy.data.objects[RIG];verifier=load('rebase_verify',ROOT/'tools/verify_rear_mirror_sources.py');before=verifier.read()
    old={b.name:C@rig.matrix_world@b.matrix_local@CI for b in rig.data.bones};new={}
    main=next(m for m in data['garments'] if m['name'].startswith('FIT_T001'))
    current={data['bones'][i]['name']:Matrix(data['bones'][i]['world_matrix']) for i in main['bone_ids']}
    bind={data['bones'][i]['name']:Matrix(m) for i,m in zip(main['bone_ids'],main['bindposes'])}
    assert set(old)<=set(current)
    # Prove that the source-to-native pose map reconstructs actual captured
    # BakeMesh vertices before applying any target-base positional changes.
    reconstruction=0.
    for i in range(0,len(main['positions']),max(1,len(main['positions'])//500)):
        p=Vector(main['source_positions'][i]);weight=main['weights'][i];predicted=Vector()
        for slot,w in zip(weight['indices'],weight['weights']):
            if w>1e-7:
                name=data['bones'][main['bone_ids'][slot]]['name'];predicted+=(current[name]@bind[name]@p)*w
        reconstruction=max(reconstruction,(predicted-Vector(main['positions'][i])).length)
    assert reconstruction<1e-5,reconstruction
    def resolve(b):
        if b.name in new:return new[b.name]
        if b.name in target:
            # Use the actual garment's native T-pose axes, NOT the differently
            # normalized base-avatar axes. Its current skin map was proven above.
            matrix=current[b.name].copy();matrix.translation=target[b.name].translation
        elif b.parent:matrix=resolve(b.parent)@current[b.parent.name].inverted()@current[b.name]
        else:matrix=current[b.name]
        new[b.name]=matrix;return matrix
    for bone in rig.data.bones:resolve(bone)
    transforms={n:new[n]@old[n].inverted() for n in old}
    fitted=bpy.data.collections['FITTED_服装工作副本'];objects=[o for o in bpy.data.objects if o.type=='MESH' and (o.name in fitted.all_objects or o.name.startswith('REF_VRoid_'))]
    # Correct the knot's bottom to follow the same actual skirt surface before
    # rebasing; keep the blue tail root beneath its layered fabric.
    mounts=load('mounts',ROOT/'tools/fit_accessory_mounts.py');tree=mounts.back_surface();knot=bpy.data.objects['FIT_NEW_BowKnot']
    points=[C@knot.matrix_world@v.co for v in knot.data.vertices];front=max(p.z for p in points);inverse=(C@knot.matrix_world).inverted()
    for v,p in zip(knot.data.vertices,points):
        q=p.copy();q.z=mounts.rear_z(tree,p.x,p.y)-.014+(p.z-front);v.co=inverse@q
    knot.data.update()
    max_displacements={}
    for obj in objects:
        to_world=C@obj.matrix_world;inverse=to_world.inverted();maximum=0.
        for vertex in obj.data.vertices:
            p=to_world@vertex.co;influences=[(obj.vertex_groups[g.group].name,g.weight) for g in vertex.groups if g.weight>1e-7]
            assert influences and all(n in transforms for n,w in influences),obj.name
            total=sum(w for n,w in influences);q=sum(((transforms[n]@p)*(w/total) for n,w in influences),Vector())
            maximum=max(maximum,(q-p).length);vertex.co=inverse@q
        obj.data.update();max_displacements[obj.name]=maximum
    selected=list(bpy.context.selected_objects);active=bpy.context.view_layer.objects.active
    for obj in selected:obj.select_set(False)
    rig.select_set(True);bpy.context.view_layer.objects.active=rig;bpy.ops.object.mode_set(mode='EDIT')
    try:
        for bone in rig.data.edit_bones:
            length=bone.length;matrix=rig.matrix_world.inverted()@CI@new[bone.name]@C
            bone.matrix=matrix;bone.length=length
    finally:bpy.ops.object.mode_set(mode='OBJECT')
    for obj in bpy.context.selected_objects:obj.select_set(False)
    for obj in selected:obj.select_set(True)
    bpy.context.view_layer.objects.active=active
    bpy.context.view_layer.update()
    # The addon derives collider-local offsets from helper-object world matrices.
    # Move those helpers with the calibrated bones while preserving shape values.
    sb=rig.data.vrm_addon_extension.spring_bone1
    for collider,record in zip(sb.colliders,before['collider_parameters']):
        shape=collider.shape.sphere if collider.shape_type=='Sphere' else collider.shape.capsule
        values=record['sphere'] if collider.shape_type=='Sphere' else record['capsule']
        shape.offset=values['offset'];shape.radius=values['radius']
        if collider.shape_type=='Capsule':shape.tail=values['tail']
    bpy.context.view_layer.update()
    after=verifier.read()
    def equivalent(a,b):
        if isinstance(a,dict):return a.keys()==b.keys() and all(equivalent(a[k],b[k]) for k in a)
        if isinstance(a,list):return len(a)==len(b) and all(equivalent(x,y) for x,y in zip(a,b))
        if isinstance(a,float):return math.isclose(a,b,abs_tol=2e-6,rel_tol=0.)
        return a==b
    for key in before:
        if key=='bones':
            assert set(before[key])==set(after[key])
            assert all(after[key][n]['parent']==b['parent'] and after[key][n]['deform']==b['deform'] for n,b in before[key].items())
        elif key=='meshes':
            for name,b in before[key].items():
                assert {k:v for k,v in b.items() if k!='co'}=={k:v for k,v in after[key][name].items() if k!='co'},name
                if name not in max_displacements:assert b==after[key][name],name
        elif key=='collider_parameters':assert equivalent(before[key],after[key]),key
        else:assert before[key]==after[key],key
    out.mkdir(parents=True);stem='whale_maid_shoes_tights_mounts_v05';target_path=out/(stem+'.blend')
    preference=bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(target_path),copy=True,relative_remap=False,compress=True)
    finally:bpy.context.preferences.filepaths.save_version=preference
    bpy.ops.wm.open_mainfile(filepath=str(target_path));assert verifier.read()==after
    rig=bpy.data.objects[RIG];sb=rig.data.vrm_addon_extension.spring_bone1;enabled=sb.enable_animation;poses={p.name:p.matrix_basis.copy() for p in rig.pose.bones}
    try:
        sb.enable_animation=False
        for pose in rig.pose.bones:pose.matrix_basis.identity()
        bpy.context.view_layer.update();meshes=[o for o in bpy.data.collections['FITTED_服装工作副本'].all_objects if o.type=='MESH']
        exporter=load('rebase_export',ROOT/'blender-addons/vroid_xwear_direct/__init__.py');package=out/(stem+'.xwear')
        result=exporter.export_xwear(package,rig,meshes,item_name='Whale maid white tights and fitted Mary Janes v05',author='Local creator',coordinate_matrix=C);write(package.with_suffix('.xwear.json'),result)
        review=load('rebase_review',ROOT/'tools/review_target_cloth.py');review.OUT=out
        for view in ('front','side','back'):review.render_pose('calibrated_v05',view)
    finally:
        for pose in rig.pose.bones:pose.matrix_basis=poses[pose.name]
        sb.enable_animation=enabled
    assert digest(source)==source_sha
    old_sha=digest(a.reference)
    report={**previous,'source':str(source),'source_sha256':source_sha,'copy':str(target_path),'copy_sha256':digest(target_path),'package':str(package),'package_sha256':digest(package),'native_acceptance':False,'native_base_reference':str(a.reference),'native_base_reference_sha256':old_sha,'native_base_foot_source':data['base_foot_source'],'calibration':'Proven native garment T-pose skin map; base joint positions; garment axes retained','native_skin_reconstruction_error_m':reconstruction,'calibrated_mesh_max_delta_m':max_displacements,'native_matched_bones':sorted(set(target)&set(old)),'bones_before':{n:[list(r) for r in m] for n,m in old.items()},'bones_after':{n:[list(r) for r in m] for n,m in new.items()},'knot_depth_conformed_before_calibration':True,'original_topology_uv_weights_materials_images_bones_springs_colliders_preserved':False,'topology_uv_weights_materials_images_spring_parameters_collider_parameters_preserved':True,'note':'Native garment pose reconstructed before positional rebinding. Bone bind transforms explicitly calibrated. Source Tripo geometry retained unchanged. Not collision tuning.'}
    write(out/'build.json',report)
    print(json.dumps({'built':True,'out':str(out),'matched_bones':len(report['native_matched_bones']),'foot_before':[list(old[n].translation) for n in ['J_Bip_L_Foot','J_Bip_R_Foot']],'foot_after':[list(new[n].translation) for n in ['J_Bip_L_Foot','J_Bip_R_Foot']]}),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--reference',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    build(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
