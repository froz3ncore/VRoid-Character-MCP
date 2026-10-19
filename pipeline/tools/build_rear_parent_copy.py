"""Isolate front/rear root-parent differences in a fresh Blender/XWear copy."""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix

ROOT = Path(__file__).resolve().parents[1]
PAIRS = {4: 2, 5: 1, 7: 11, 8: 10}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(source, out, mirror_anchors=False):
    source, out = source.resolve(), out.resolve()
    assert Path(bpy.data.filepath).resolve() == source and not bpy.data.is_dirty
    assert out.is_relative_to(ROOT / 'projects/whale-maid') and not out.exists()
    fit = load('fit', ROOT / 'blender-addons/vroid_xwear_direct/fit.py')
    exporter = load('xwear', ROOT / 'blender-addons/vroid_xwear_direct/__init__.py')
    verifier = load('verify_source', ROOT / 'tools/verify_rear_dense_source.py')
    original_hash = fit.digest(source)
    assert original_hash == '9390b4423fae8a4e121304c607f3497b8f579f16a3ca27325c30ab1c5b600b2e'
    before = verifier.read()
    rig = bpy.data.objects['WM_TargetVRoidRig_v01']
    coord = Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1))) @ rig.matrix_world
    inverse = coord.inverted()
    # Derive the garment's sagittal reflection plane from the already mirrored
    # lower chain points, instead of assuming the humanoid hip is its centre.
    mids = [(coord @ rig.data.bones['WM_Skirt_%02d_01' % rear].head_local).z / 2 +
            (coord @ rig.data.bones['WM_Skirt_%02d_01' % front].head_local).z / 2
            for rear, front in PAIRS.items()]
    plane_z = sum(mids)/len(mids)
    assert max(mids)-min(mids) < 1e-6
    anchor_changes = []
    if mirror_anchors:
        for rear, front in {**PAIRS, 6: 0}.items():
            rear_name, front_name = 'WM_Skirt_%02d_00' % rear, 'WM_Skirt_%02d_00' % front
            front_bone = rig.data.bones[front_name]
            head, tail = coord @ front_bone.head_local, coord @ front_bone.tail_local
            head.z, tail.z = 2*plane_z-head.z, 2*plane_z-tail.z
            anchor_changes.append({'bone':rear_name, 'front_control':front_name,
                'before_native_head':list(coord @ rig.data.bones[rear_name].head_local),
                'after_native_head':list(head), 'head':list(inverse @ head), 'tail':list(inverse @ tail)})
    changes = []
    for rear, front in PAIRS.items():
        rear_name, front_name = 'WM_Skirt_%02d_00' % rear, 'WM_Skirt_%02d_00' % front
        old_parent = rig.data.bones[rear_name].parent.name
        parent = rig.data.bones[front_name].parent.name
        assert old_parent == 'J_Bip_C_Hips' and parent.endswith('_UpperLeg')
        changes.append({'bone': rear_name, 'front_control': front_name,
                        'before_parent': old_parent, 'after_parent': parent})
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        for change in changes:
            bone = rig.data.edit_bones[change['bone']]
            matrix, length = bone.matrix.copy(), bone.length
            bone.use_connect = False
            bone.parent = rig.data.edit_bones[change['after_parent']]
            bone.matrix, bone.length = matrix, length
        for change in anchor_changes:
            bone = rig.data.edit_bones[change['bone']]
            bone.head, bone.tail = change['head'], change['tail']
    finally:
        bpy.ops.object.mode_set(mode='OBJECT')

    def verify():
        actual = verifier.read()
        expected = dict(before, bones={name: dict(bone) for name, bone in before['bones'].items()})
        for change in changes:
            expected['bones'][change['bone']]['parent'] = change['after_parent']
        for change in anchor_changes:
            expected['bones'][change['bone']].update(anchor_bones[change['bone']])
        # Blender may round rest-matrix components on the edit-mode transition.
        max_position_delta, max_matrix_delta = 0., 0.
        for name, bone in expected['bones'].items():
            other = actual['bones'][name]
            for field in ('head', 'tail'):
                max_position_delta = max(max_position_delta, *(abs(a-b) for a,b in zip(bone[field], other[field])))
                other[field] = bone[field]
            max_matrix_delta = max(max_matrix_delta, *(abs(a-b) for ra,rb in zip(bone['matrix'], other['matrix']) for a,b in zip(ra,rb)))
            other['matrix'] = bone['matrix']
        assert max_position_delta < 2e-6, max_position_delta
        assert max_matrix_delta < 1e-5, max_matrix_delta
        assert actual == expected, 'Unexpected source change beyond root parenting'
        return {'position_m':max_position_delta,'matrix_component':max_matrix_delta}

    edited_bones = verifier.read()['bones']
    anchor_bones = {c['bone']: edited_bones[c['bone']] for c in anchor_changes}
    for change in anchor_changes:
        from mathutils import Vector
        bone = rig.data.bones[change['bone']]
        assert (bone.head_local-Vector(change['head'])).length < 2e-6
        assert (bone.tail_local-Vector(change['tail'])).length < 2e-6
    live_error = verify()
    out.mkdir(parents=True, exist_ok=False)
    stem = 'whale_maid_rear_anchor_e2' if mirror_anchors else 'whale_maid_rear_parent_e1'
    target = out / (stem+'.blend')
    old_version = bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version = 0
        assert 'FINISHED' in bpy.ops.wm.save_as_mainfile(filepath=str(target), copy=True,
                                                       relative_remap=False, compress=True)
    finally:
        bpy.context.preferences.filepaths.save_version = old_version
    bpy.ops.wm.open_mainfile(filepath=str(target))
    cold_error = verify()
    rig = bpy.data.objects['WM_TargetVRoidRig_v01']
    sb = rig.data.vrm_addon_extension.spring_bone1
    meshes = [o for o in bpy.data.collections['FITTED_服装工作副本'].all_objects if o.type == 'MESH']
    assert len(meshes) == 69
    sb.enable_animation = False
    for pose in rig.pose.bones:
        pose.matrix_basis.identity()
    bpy.context.view_layer.update()
    package = out / (stem+'.xwear')
    manifest = exporter.export_xwear(package, rig, meshes,
        item_name='Whale maid rear anchor E2 comparison' if mirror_anchors else 'Whale maid rear parent E1 comparison', author='Local test asset',
        coordinate_matrix=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1))))
    manifest.update(source_blend=str(target), source_sha256=fit.digest(target), experimental=True)
    fit.write_new(package.with_suffix('.xwear.json'), manifest)
    assert fit.digest(source) == original_hash
    report = {'source': str(source), 'source_sha256': original_hash,
        'copy': str(target), 'copy_sha256': fit.digest(target), 'changes': changes,
        'anchor_changes':anchor_changes,'garment_reflection_depth_m':plane_z,
        'package': str(package), 'package_sha256': fit.digest(package),
        'cold_source_check_passed': True, 'rest_rounding_delta':{'live':live_error,'cold':cold_error},
        'geometry_uv_materials_images_weights_springs_unchanged': True,
        'unchanged_bone_positions_preserved_within_m': 2e-6,
        'unchanged_bone_rest_matrix_components_preserved_within':1e-5,
        'adopted': False, 'collision_free': False}
    fit.write_new(out / 'build.json', report)
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--mirror-anchors',action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    build(args.source, args.out, args.mirror_anchors)
