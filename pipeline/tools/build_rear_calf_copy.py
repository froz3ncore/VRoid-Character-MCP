"""Two-chain/two-calf contact experiment, preserving baseline dynamics and skin."""
import importlib.util,json
from pathlib import Path
import bpy
from mathutils import Matrix,Vector
ROOT=Path(__file__).resolve().parents[1]

def build(source,out):
    source,out=Path(source).resolve(),Path(out).resolve()
    assert Path(bpy.data.filepath).resolve()==source and not bpy.data.is_dirty and not out.exists()
    assert out.is_relative_to(ROOT/'projects/whale-maid')
    spec=importlib.util.spec_from_file_location('fit',ROOT/'blender-addons/vroid_xwear_direct/fit.py');fit=importlib.util.module_from_spec(spec);spec.loader.exec_module(fit)
    spec=importlib.util.spec_from_file_location('xwear',ROOT/'blender-addons/vroid_xwear_direct/__init__.py');exporter=importlib.util.module_from_spec(spec);spec.loader.exec_module(exporter)
    original=fit.digest(source);fingerprints={o.name:fit.fingerprint(o) for o in bpy.data.objects if o.type=='MESH'}
    rig=bpy.data.objects['WM_TargetVRoidRig_v01'];sb=rig.data.vrm_addon_extension.spring_bone1
    assert len(sb.colliders)==5
    original_ids=[c.uuid for c in sb.colliders];guards=[]
    for side in ('L','R'):
        start,end=rig.data.bones['J_Bip_'+side+'_LowerLeg'],rig.data.bones['J_Bip_'+side+'_Foot']
        inverse=start.matrix_local.inverted();shift=Vector((-.01,0,0))
        c=sb.add_collider(bpy.context,rig);c.node.bone_name=start.name
        c.shape_type=c.SHAPE_TYPE_CAPSULE.identifier;c.reset_bpy_object(bpy.context,rig)
        c.shape.capsule.offset=inverse@(start.head_local+shift);c.shape.capsule.tail=inverse@(end.head_local+shift);c.shape.capsule.radius=.06
        c.bpy_object.name='REAR_CALF_'+side;c.bpy_object.hide_render=True
        for child in c.bpy_object.children:child.hide_render=True
        guards.append(c.uuid)
    group=sb.add_collider_group();group.vrm_name='Rear lower contact only'
    for uuid in original_ids+guards:group.add_collider().collider_uuid=uuid
    changes=[]
    for spring in sb.springs:
        if spring.vrm_name not in ('Skirt_05','Skirt_07'):continue
        before=[g.collider_group_uuid for g in spring.collider_groups]
        spring.collider_groups.clear();spring.add_collider_group().collider_group_uuid=group.uuid
        joints=[]
        for i,joint in enumerate(spring.joints):
            if i in (2,3):
                joints.append({'bone':joint.node.bone_name,'old':joint.hit_radius,'new':.012});joint.hit_radius=.012
        changes.append({'spring':spring.vrm_name,'previous_groups':before,'joint_radii':joints})
    sb.fixup();assert len(changes)==2 and len(sb.colliders)==7
    assert fingerprints=={o.name:fit.fingerprint(o) for o in bpy.data.objects if o.type=='MESH'}
    out.mkdir(parents=True,exist_ok=False);target=out/'whale_maid_rear_calf_v03.blend'
    old=bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version=0
        assert 'FINISHED' in bpy.ops.wm.save_as_mainfile(filepath=str(target),copy=True,relative_remap=False,compress=True)
    finally:bpy.context.preferences.filepaths.save_version=old
    meshes=[o for o in bpy.data.collections['FITTED_服装工作副本'].all_objects if o.type=='MESH'];assert len(meshes)==69
    enabled=sb.enable_animation;poses={p.name:p.matrix_basis.copy() for p in rig.pose.bones}
    try:
        sb.enable_animation=False
        for pose in rig.pose.bones:pose.matrix_basis.identity()
        bpy.context.view_layer.update();package=out/'whale_maid_rear_calf_v03.xwear'
        manifest=exporter.export_xwear(package,rig,meshes,item_name='Rear calf local experiment',author='Local test asset',coordinate_matrix=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1))))
        manifest.update(source_blend=str(target),source_sha256=fit.digest(target),experimental=True)
        fit.write_new(package.with_suffix('.xwear.json'),manifest)
    finally:
        for pose in rig.pose.bones:pose.matrix_basis=poses[pose.name]
        sb.enable_animation=enabled
    report={'source':str(source),'source_sha256':original,'copy':str(target),'copy_sha256':fit.digest(target),
        'changes':changes,'all_meshes_unchanged':True,'colliders':7,'package':str(package),'native_acceptance':False,'adopted':False}
    fit.write_new(out/'build.json',report);assert fit.digest(source)==original
    return report
