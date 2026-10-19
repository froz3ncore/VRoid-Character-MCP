"""Build a rear-only dynamics experiment and its XWear without replacing sources."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import bpy
from mathutils import Matrix

ROOT=Path(__file__).resolve().parents[1]


def build(source,out,stiffness=.9,gravity=.035):
    source,out=Path(source).resolve(),Path(out).resolve()
    assert Path(bpy.data.filepath).resolve()==source and not bpy.data.is_dirty
    assert out.is_relative_to(ROOT/'projects/whale-maid') and not out.exists()
    assert 0<stiffness<=2 and 0<=gravity<=.3
    spec=importlib.util.spec_from_file_location('fit',ROOT/'blender-addons/vroid_xwear_direct/fit.py')
    fit=importlib.util.module_from_spec(spec);spec.loader.exec_module(fit)
    spec=importlib.util.spec_from_file_location('xwear',ROOT/'blender-addons/vroid_xwear_direct/__init__.py')
    exporter=importlib.util.module_from_spec(spec);spec.loader.exec_module(exporter)
    original_hash=fit.digest(source)
    fingerprints={o.name:fit.fingerprint(o) for o in bpy.data.objects if o.type=='MESH'}
    rig=bpy.data.objects['WM_TargetVRoidRig_v01'];sb=rig.data.vrm_addon_extension.spring_bone1
    changes=[]
    for spring in sb.springs:
        if spring.vrm_name not in {'Skirt_%02d'%i for i in range(4,9)}:continue
        for index,joint in enumerate(spring.joints):
            if index<2:continue
            before={'stiffness':joint.stiffness,'gravity':joint.gravity_power,'drag':joint.drag_force,'radius':joint.hit_radius}
            joint.stiffness=stiffness;joint.gravity_power=gravity
            changes.append({'spring':spring.vrm_name,'bone':joint.node.bone_name,'before':before,
                'after':{'stiffness':joint.stiffness,'gravity':joint.gravity_power,'drag':joint.drag_force,'radius':joint.hit_radius}})
    assert len(changes)==15
    assert fingerprints=={o.name:fit.fingerprint(o) for o in bpy.data.objects if o.type=='MESH'}
    out.mkdir(parents=True,exist_ok=False)
    target=out/'whale_maid_rear_support_v03.blend'
    old=bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version=0
        result=bpy.ops.wm.save_as_mainfile(filepath=str(target),copy=True,relative_remap=False,compress=True)
        assert 'FINISHED' in result
    finally:bpy.context.preferences.filepaths.save_version=old
    meshes=[o for o in bpy.data.collections['FITTED_服装工作副本'].all_objects if o.type=='MESH'];assert len(meshes)==69
    enabled=sb.enable_animation;poses={p.name:p.matrix_basis.copy() for p in rig.pose.bones}
    try:
        sb.enable_animation=False
        for pose in rig.pose.bones:pose.matrix_basis.identity()
        bpy.context.view_layer.update()
        package=out/'whale_maid_rear_support_v03.xwear'
        manifest=exporter.export_xwear(package,rig,meshes,item_name='Whale maid rear support experiment v03',author='Local creator',
            coordinate_matrix=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1))))
        manifest.update(source_blend=str(target),source_sha256=fit.digest(target),experimental=True)
        fit.write_new(package.with_suffix('.xwear.json'),manifest)
    finally:
        for pose in rig.pose.bones:pose.matrix_basis=poses[pose.name]
        sb.enable_animation=enabled
    report={'source':str(source),'source_sha256':original_hash,'copy':str(target),'copy_sha256':fit.digest(target),
        'changes':changes,'mesh_fingerprints':fingerprints,'all_meshes_unchanged':True,'textures_and_colliders_unchanged':True,
        'package':str(package),'package_sha256':fit.digest(package),'native_acceptance':False,'adopted':False}
    fit.write_new(out/'build.json',report)
    assert fit.digest(source)==original_hash
    return {'copy':str(target),'package':str(package),'changed_joints':len(changes),'source_unchanged':True,'adopted':False}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--stiffness',type=float,default=.9);p.add_argument('--gravity',type=float,default=.035)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);print(json.dumps(build(a.source,a.out,a.stiffness,a.gravity),ensure_ascii=False))
