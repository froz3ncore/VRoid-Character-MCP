"""Apply the measured per-foot rigid heading fit to all original shoe pieces."""
import argparse,hashlib,importlib.util,json,sys
from pathlib import Path
import bpy
from mathutils import Matrix,Vector

ROOT=Path(__file__).resolve().parents[1]
C=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1)))
SHA='f375986e0d59c0c68c97bfc25307867eb342ac948cb86bb3ffed0fbc98d9f55e'
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2)

def check(before,after,transforms):
    maximum=0.
    for key,value in before.items():
        if key!='meshes':assert after[key]==value,key;continue
        assert value.keys()==after[key].keys()
        for name,row in value.items():
            actual=after[key][name]
            if name not in transforms:assert row==actual,name;continue
            assert {k:v for k,v in row.items() if k!='co'}=={k:v for k,v in actual.items() if k!='co'},name
            matrix=C@bpy.data.objects[name].matrix_world
            for p,q in zip(row['co'],actual['co']):maximum=max(maximum,(matrix@Vector(q)-transforms[name]@matrix@Vector(p)).length)
    assert maximum<3e-7,maximum
    return maximum

def normals(names):
    return {n:{'custom':bpy.data.objects[n].data.has_custom_normals,'values':[v.vector.copy() for v in bpy.data.objects[n].data.corner_normals]} for n in names}

def check_normals(before,after,transforms):
    maximum=0.
    for name,row in before.items():
        if not row['custom']:continue
        assert after[name]['custom']
        matrix=C@bpy.data.objects[name].matrix_world
        rotation=(matrix.inverted()@transforms[name]@matrix).to_3x3().inverted().transposed()
        assert len(row['values'])==len(after[name]['values'])
        for old,new in zip(row['values'],after[name]['values']):maximum=max(maximum,((rotation@old).normalized()-new).length)
    assert maximum<.0005,maximum
    return maximum

def main(a):
    current=Path(bpy.data.filepath).resolve();assert not bpy.data.is_dirty
    scope=load('heading_scope',ROOT/'tools/verify_rear_mirror_sources.py')
    if a.verify:
        build=json.loads((current.parent/'build.json').read_text(encoding='utf8'));assert digest(current)==build['copy_sha256']
        after=scope.read();matrices={o.name:[list(r) for r in o.matrix_world] for o in bpy.data.objects};after_normals=normals(build['native_transforms'])
        bpy.ops.wm.open_mainfile(filepath=build['source']);before=scope.read();transforms={n:Matrix(m) for n,m in build['native_transforms'].items()}
        maximum=check(before,after,transforms)
        normal_error=check_normals(normals(transforms),after_normals,transforms)
        assert all([list(r) for r in bpy.data.objects[n].matrix_world]==m for n,m in matrices.items())
        assert digest(build['source'])==build['source_sha256'] and digest(build['package'])==build['package_sha256']
        write(current.parent/'cold-source-check.json',{'passed':True,'candidate':str(current),'sha256':build['copy_sha256'],'source_unchanged':True,'shoe_rigid_transform_max_error_mm':maximum*1000,'custom_normal_max_vector_error':normal_error,'custom_normal_meshes':sum(r['custom'] for r in after_normals.values()),'shoe_topology_uv_materials_weights_preserved':True,'other_89_fitted_meshes_and_original_sources_unchanged':True,'object_transforms_rig_bones_images_springs_colliders_preserved':True})
        print(json.dumps({'cold_check_passed':True,'max_error_mm':maximum*1000}),flush=True);return
    assert digest(current)==SHA
    plan=json.loads(a.plan.read_text(encoding='utf8'));assert digest(plan['reference'])==plan['reference_sha256']
    out=a.out.resolve();assert not out.exists() and out.is_relative_to(ROOT/'projects/whale-maid')
    before=scope.read();matrices={o.name:[list(r) for r in o.matrix_world] for o in bpy.data.objects}
    meshes=[o for o in bpy.data.collections['FITTED_服装工作副本'].all_objects if o.type=='MESH'];assert len(meshes)==97
    transforms={};normal_before=normals([o.name for o in meshes if o.name.startswith('FIT_ACCESSORY_Shoe_')])
    for row in plan['rows']:
        transform=Matrix(row['chosen']['native_transform'])
        selected=[o for o in meshes if o.name.startswith('FIT_ACCESSORY_Shoe_'+row['side']+'_')];assert len(selected)==4
        for obj in selected:
            matrix=C@obj.matrix_world;inverse=matrix.inverted();transforms[obj.name]=transform
            for vertex in obj.data.vertices:vertex.co=inverse@transform@matrix@vertex.co
            obj.data.update()
            if normal_before[obj.name]['custom']:
                rotation=(inverse@transform@matrix).to_3x3().inverted().transposed()
                obj.data.normals_split_custom_set([(rotation@n).normalized() for n in normal_before[obj.name]['values']])
    bpy.context.view_layer.update();after=scope.read();maximum=check(before,after,transforms)
    assert len(transforms)==8 and all([list(r) for r in bpy.data.objects[n].matrix_world]==m for n,m in matrices.items())
    normal_error=check_normals(normal_before,normals(transforms),transforms)
    out.mkdir();stem='whale_maid_shoe_heading_v15';target=out/(stem+'.blend')
    pref=bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(target),copy=True,compress=True,relative_remap=False)
    finally:bpy.context.preferences.filepaths.save_version=pref
    bpy.ops.wm.open_mainfile(filepath=str(target));assert scope.read()==after
    rig=bpy.data.objects['WM_TargetVRoidRig_v01'];sb=rig.data.vrm_addon_extension.spring_bone1;enabled=sb.enable_animation;poses={p.name:p.matrix_basis.copy() for p in rig.pose.bones}
    try:
        sb.enable_animation=False
        for pose in rig.pose.bones:pose.matrix_basis.identity()
        bpy.context.view_layer.update();export=load('heading_export',ROOT/'blender-addons/vroid_xwear_direct/__init__.py');package=out/(stem+'.xwear')
        result=export.export_xwear(package,rig,[o for o in bpy.data.collections['FITTED_服装工作副本'].all_objects if o.type=='MESH'],item_name='Whale maid original shoes heading fit v15',author='Local creator',coordinate_matrix=C)
        write(package.with_suffix('.xwear.json'),result)
    finally:
        for pose in rig.pose.bones:pose.matrix_basis=poses[pose.name]
        sb.enable_animation=enabled
    assert digest(current)==SHA
    write(out/'heading-plan.json',plan)
    write(out/'build.json',{'source':str(current),'source_sha256':SHA,'copy':str(target),'copy_sha256':digest(target),'package':str(package),'package_sha256':digest(package),'native_transforms':{n:[list(r) for r in m] for n,m in transforms.items()},'heading_plan':str(out/'heading-plan.json'),'heading_plan_sha256':digest(out/'heading-plan.json'),'source_scope_check_passed':True,'rigid_max_error_mm':maximum*1000,'custom_normal_max_vector_error':normal_error,'native_acceptance':False,'adopted':False,'shoe_fit_complete':False,'scope':'Only 8 original shoe/strap/buckle coordinate streams and their 6 custom corner-normal streams rotate by per-side shared rigid transforms. No shape scaling/remodeling, topology/UV/material/weight/object/rig/stocking/physics or body-mask changes.'})
    print(json.dumps({'built':True,'out':str(out),'shoe_parts':len(transforms),'max_error_mm':maximum*1000}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path);p.add_argument('--plan',type=Path);p.add_argument('--verify',action='store_true');main(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
