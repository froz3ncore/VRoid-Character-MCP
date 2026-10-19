"""Independent height registration trial; protected shoe/stocking world geometry."""
import argparse, hashlib, importlib.util, json, math, sys
from pathlib import Path
import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
C = Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1)))
CI = C.inverted()
SHA = '7976d04deb923c2c6a0af42e82c6cf77b82e55f7d1ae71447c22ddf50ee79fbf'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def equivalent(a, b):
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(equivalent(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(equivalent(x, y) for x, y in zip(a, b))
    if isinstance(a, float):
        return math.isclose(a, b, abs_tol=2e-6, rel_tol=0)
    return a == b


def check(before, after, changed, delta):
    for key in before:
        if key == 'meshes':
            assert before[key].keys() == after[key].keys()
            for name, mesh in before[key].items():
                actual = after[key][name]
                assert {k:v for k,v in mesh.items() if k!='co'} == {k:v for k,v in actual.items() if k!='co'}, name
                if name in changed:
                    matrix = C@bpy.data.objects[name].matrix_world
                    assert max((matrix@Vector(q)-matrix@Vector(p)-delta).length for p,q in zip(mesh['co'], actual['co'])) < 3e-7, name
                else:
                    assert mesh == actual, name
        elif key == 'bones':
            assert before[key] == after[key], key
        elif key == 'collider_parameters':
            assert equivalent(before[key], after[key]), key
        else:
            assert before[key] == after[key], key


def main(a):
    source = Path(bpy.data.filepath).resolve()
    assert digest(source) == SHA and not bpy.data.is_dirty
    out = a.out.resolve()
    assert not out.exists() and out.is_relative_to(ROOT/'projects/whale-maid')
    data = json.loads(a.reference.read_text(encoding='utf8'))
    assert data['pose_source'] == 'native_edit'
    body = next(m for m in data['base_meshes'] if m['name'] == 'Body')
    shoe = next(m for m in data['garments'] if m['name'].startswith('FIT_ACCESSORY_Shoe_'))
    def bones(mesh):
        return {data['bones'][i]['name']: Matrix(data['bones'][i]['world_matrix']) for i in mesh['bone_ids']}
    base, garment = bones(body), bones(shoe)
    names = sorted(n for n in set(base)&set(garment) if n.startswith('J_'))
    gaps = [base[n].translation-garment[n].translation for n in names]
    delta = sum(gaps, Vector())/len(gaps)
    residual = max((gap-delta).length for gap in gaps)
    assert len(names)>50 and residual<2e-6 and .05<delta.y<.07 and abs(delta.x)<2e-6 and abs(delta.z)<2e-6, (len(names),list(delta),residual)
    scope = load('height_scope', ROOT/'tools/verify_rear_mirror_sources.py')
    before = scope.read()
    transforms = {o.name: o.matrix_world.copy() for o in bpy.data.objects if o.type=='MESH'}
    fitted = [o for o in bpy.data.collections['FITTED_服装工作副本'].all_objects if o.type=='MESH']
    protected = {o.name for o in fitted if o.name.startswith(('FIT_ACCESSORY_Shoe_','FIT_NEW_WhiteStocking_'))}
    assert len(fitted)==97 and len(protected)==10
    changed = {o.name for o in fitted if o.name not in protected}
    for obj in fitted:
        if obj.name in protected:
            continue
        local = (C@obj.matrix_world).inverted().to_3x3()@delta
        for vertex in obj.data.vertices:
            vertex.co += local
        obj.data.update()
    rig = bpy.data.objects['WM_TargetVRoidRig_v01']
    rig_before = rig.matrix_world.copy()
    rig.matrix_world.translation += CI.to_3x3()@delta
    bpy.context.view_layer.update()
    # Keep mesh object transforms and protected authored world geometry intact.
    # Move the armature object rather than editing short bones: all local rest
    # matrices/rolls remain byte-identical, avoiding tail-rounding axis changes.
    for name, matrix in transforms.items():
        bpy.data.objects[name].matrix_world = matrix
    sb = rig.data.vrm_addon_extension.spring_bone1
    for collider, record in zip(sb.colliders, before['collider_parameters']):
        shape = collider.shape.sphere if collider.shape_type=='Sphere' else collider.shape.capsule
        values = record['sphere'] if collider.shape_type=='Sphere' else record['capsule']
        shape.offset = values['offset']
        shape.radius = values['radius']
        if collider.shape_type=='Capsule':
            shape.tail = values['tail']
    bpy.context.view_layer.update()
    after = scope.read()
    check(before, after, changed, delta)
    assert all(max(abs(x-y) for row,old in zip(bpy.data.objects[n].matrix_world,mat) for x,y in zip(row,old))<2e-7 for n,mat in transforms.items())
    out.mkdir()
    stem = 'whale_maid_heel_height_v14'
    target = out/(stem+'.blend')
    pref = bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_as_mainfile(filepath=str(target), copy=True, compress=True, relative_remap=False)
    finally:
        bpy.context.preferences.filepaths.save_version = pref
    bpy.ops.wm.open_mainfile(filepath=str(target))
    check(before, scope.read(), changed, delta)
    rig = bpy.data.objects['WM_TargetVRoidRig_v01']
    rig.data.vrm_addon_extension.spring_bone1.enable_animation = False
    for pose in rig.pose.bones:
        pose.matrix_basis.identity()
    bpy.context.view_layer.update()
    exporter = load('height_export', ROOT/'blender-addons/vroid_xwear_direct/__init__.py')
    package = out/(stem+'.xwear')
    result = exporter.export_xwear(package, rig, [o for o in bpy.data.collections['FITTED_服装工作副本'].all_objects if o.type=='MESH'], item_name='Whale maid heel-height registration v14', author='Local creator', coordinate_matrix=C)
    write(package.with_suffix('.xwear.json'), result)
    assert digest(source)==SHA
    write(out/'build.json', {'source':str(source),'source_sha256':SHA,'copy':str(target),'copy_sha256':digest(target),'package':str(package),'package_sha256':digest(package),'reference':str(a.reference.resolve()),'reference_sha256':digest(a.reference),'matched_bones':len(names),'measured_height_delta_m':list(delta),'bone_delta_residual_m':residual,'rig_world_before':[list(r) for r in rig_before],'rig_world_after':[list(r) for r in rig.matrix_world],'translated_meshes':sorted(changed),'protected_shoes_stockings':sorted(protected),'cold_reopen_scope_passed':True,'native_acceptance':False,'adopted':False,'physics_parameters_preserved':True,'scope':'Translate armature object (all 264 rest bones in world) and 87 non-footwear garments by measured high-heel height difference. Local bone matrices/rolls and ten shoe/stocking source world meshes stay unchanged. No topology/UV/weights/material/texture changes or collision tuning.'})
    print(json.dumps({'built':True,'out':str(out),'delta_mm':[v*1000 for v in delta],'matched_bones':len(names),'protected_meshes':len(protected)}),flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    main(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
