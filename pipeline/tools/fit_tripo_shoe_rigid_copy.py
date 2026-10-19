"""Translate all original shoe parts together; preserve every source detail.

Runs in background Blender. The candidate and package are independent files;
--verify performs a fresh-process comparison to the recorded input source.
"""
import argparse, hashlib, importlib.util, json, sys
from pathlib import Path
import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
C = Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1)))
SOURCE_SHA = '770c595927db867fd9c44a34702142d43af37133cfe0f54aff63e2a6e6aa5ded'

def load(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path, value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,ensure_ascii=False,indent=2)

def compare(before, after, transforms):
    maximum=0.
    for key, value in before.items():
        if key!='meshes':assert after[key]==value,key;continue
        assert set(value)==set(after[key])
        for name, row in value.items():
            if name not in transforms:assert after[key][name]==row,name;continue
            other=after[key][name]
            assert {k:v for k,v in row.items() if k!='co'}=={k:v for k,v in other.items() if k!='co'},name
            obj=bpy.data.objects[name];to_native=C@obj.matrix_world
            for p,q in zip(row['co'],other['co']):
                error=(to_native@Vector(q)-transforms[name]@to_native@Vector(p)).length
                maximum=max(maximum,error)
    assert maximum<2e-7,maximum
    return maximum

def main(a):
    scope=load('rigid_scope',ROOT/'tools/verify_rear_mirror_sources.py')
    current=Path(bpy.data.filepath).resolve();assert not bpy.data.is_dirty
    if a.verify:
        report=json.loads((current.parent/'build.json').read_text(encoding='utf8'))
        assert digest(current)==report['copy_sha256'];after=scope.read()
        bpy.ops.wm.open_mainfile(filepath=report['source']);before=scope.read()
        transforms={n:Matrix(m) for n,m in report['native_transforms'].items()}
        maximum=compare(before,after,transforms)
        assert digest(report['source'])==report['source_sha256'] and digest(report['package'])==report['package_sha256']
        write(current.parent/'cold-source-check.json',{'passed':True,'candidate':str(current),
            'maximum_rigid_transform_error_mm':maximum*1000,'shoe_topology_uv_materials_weights_unchanged':True,
            'other_87_fitted_meshes_and_original_sources_unchanged':True,'rig_images_springs_colliders_unchanged':True})
        print(json.dumps({'cold_check_passed':True,'maximum_rigid_transform_error_mm':maximum*1000}),flush=True);return
    assert digest(current)==SOURCE_SHA
    out=a.out.resolve();assert out.is_relative_to(ROOT/'projects/whale-maid') and not out.exists()
    assert -20<=a.back_mm<=0
    before=scope.read();meshes=[o for o in bpy.data.collections['FITTED_服装工作副本'].all_objects if o.type=='MESH']
    shoes=[o for o in meshes if o.name.startswith('FIT_ACCESSORY_Shoe_')];assert len(shoes)==8
    transforms={o.name:Matrix.Translation(Vector((0,0,a.back_mm/1000))) for o in shoes}
    for obj in shoes:
        to_native=C@obj.matrix_world;inverse=to_native.inverted()
        for v in obj.data.vertices:v.co=inverse@transforms[obj.name]@to_native@v.co
        obj.data.update()
    bpy.context.view_layer.update();after=scope.read();maximum=compare(before,after,transforms)
    mesh_names=[o.name for o in meshes]
    out.mkdir(parents=True);stem='whale_maid_tripo_shoe_rigid_v12';target=out/(stem+'.blend')
    preference=bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version=0
        bpy.ops.wm.save_as_mainfile(filepath=str(target),copy=True,relative_remap=False,compress=True)
    finally:bpy.context.preferences.filepaths.save_version=preference
    bpy.ops.wm.open_mainfile(filepath=str(target));assert scope.read()==after
    rig=bpy.data.objects['WM_TargetVRoidRig_v01'];sb=rig.data.vrm_addon_extension.spring_bone1
    enabled=sb.enable_animation;poses={p.name:p.matrix_basis.copy() for p in rig.pose.bones}
    try:
        sb.enable_animation=False
        for p in rig.pose.bones:p.matrix_basis.identity()
        bpy.context.view_layer.update();export=load('rigid_export',ROOT/'blender-addons/vroid_xwear_direct/__init__.py')
        package=out/(stem+'.xwear');meshes=[bpy.data.objects[n] for n in mesh_names]
        result=export.export_xwear(package,rig,meshes,item_name='Whale maid original Tripo shoes rigid fit v12',author='Local creator',coordinate_matrix=C)
        write(package.with_suffix('.xwear.json'),result)
    finally:
        for p in rig.pose.bones:p.matrix_basis=poses[p.name]
        sb.enable_animation=enabled
    assert digest(current)==SOURCE_SHA
    write(out/'build.json',{'source':str(current),'source_sha256':SOURCE_SHA,'copy':str(target),
        'copy_sha256':digest(target),'package':str(package),'package_sha256':digest(package),
        'native_transforms':{n:[list(row) for row in m] for n,m in transforms.items()},
        'back_mm':a.back_mm,'maximum_rigid_transform_error_mm':maximum*1000,
        'scope':'Same rigid translation for all eight shoe/strap/buckle parts. No scale, rotation, resculpt, bind or UV changes.',
        'adopted':False,'native_acceptance':False,'shoe_fit_complete':False})
    print(json.dumps({'built':True,'out':str(out),'shoe_meshes':len(shoes),'back_mm':a.back_mm}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path);p.add_argument('--back-mm',type=float,default=-10.)
    p.add_argument('--verify',action='store_true');main(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
