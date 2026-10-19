"""Build candidate D: recovery-clearance nudge for the hip-side skirt cluster.

Applies the offline-validated localized vertex nudges (tools/predict_weight_shift.py
manifest) to a copy of the sleeve-cuff source, changing nothing else: no new
mesh, no topology, no UV, no texture, no weight, no spring or collider change.

Workflow (Blender background, default configuration with the VRM addon):

    blender.exe --background SOURCE.blend --python tools/build_recovery_clearance_copy.py -- \
        --source SOURCE.blend --manifest MANIFEST.json --out OUTDIR

The script saves the copy, reopens it cold, verifies every expectation from
the saved file, then exports the .xwear package and reports.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fit', ROOT / 'blender-addons/vroid_xwear_direct/fit.py')
fit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fit)
spec = importlib.util.spec_from_file_location('xwear', ROOT / 'blender-addons/vroid_xwear_direct/__init__.py')
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)
COORD = Matrix(((0, -1, 0, 0), (0, 0, 1, 0), (1, 0, 0, 0), (0, 0, 0, 1)))


def geometry_snapshot():
    return {o.name: {
        'positions': [list(v.co) for v in o.data.vertices],
        'faces': [list(p.vertices) for p in o.data.polygons],
        'uv': [[list(v.uv) for v in uv.data] for uv in o.data.uv_layers],
    } for o in bpy.data.objects if o.type == 'MESH'}


def image_digests():
    return {i.name: hashlib.sha256(bytes(i.packed_file.data)).hexdigest()
            for i in bpy.data.images if i.packed_file}


def weight_snapshot(obj):
    return {v.index: sorted((obj.vertex_groups[g.group].name, round(g.weight, 9))
                            for g in v.groups if g.weight > 1e-9)
            for v in obj.data.vertices}


def resolve_by_position(obj, transform, records, tolerance=1e-5):
    """Group manifest records by source position and match blend vertices.

    Export vertex order is not assumed to match any particular export map:
    blend vertices are found by their transformed position.  Duplicate
    (seam) vertices sharing one position are moved together, once.
    Returns a list of (blend_indices, delta_blend, record) with unique keys.
    """
    groups = {}
    for record in records:
        key = tuple(round(c, 6) for c in record['source_position'])
        previous = groups.get(key)
        target = tuple(round(c, 6) for c in record['new_source_position'])
        if previous is None:
            groups[key] = {'record': record, 'target': target}
        else:
            assert previous['target'] == target, (key, previous['target'], target)
    positions = [transform @ v.co for v in obj.data.vertices]
    resolved = []
    for key, group in groups.items():
        source = Vector(group['record']['source_position'])
        distances = sorted(((p - source).length, i) for i, p in enumerate(positions))
        matched = [i for d, i in distances if d <= tolerance]
        assert matched, ('no blend vertex at source position', key, distances[0][0])
        assert distances[len(matched)][0] > tolerance * 10, ('ambiguous seam match', key)
        native_delta = Vector(group['record']['new_source_position']) - source
        resolved.append((matched, native_delta, group['record']))
    return resolved


def build(source, out, manifest_path, stem='whale_maid_recovery_clearance_v03'):
    source = Path(source).resolve()
    out = Path(out).resolve()
    manifest_path = Path(manifest_path).resolve()
    assert re.fullmatch(r'[a-z][a-z0-9_]{1,63}',stem)
    assert Path(bpy.data.filepath).resolve() == source and not bpy.data.is_dirty
    assert not out.exists() and out.is_relative_to(ROOT / 'projects/whale-maid')
    original_digest = fit.digest(source)
    manifest = json.loads(manifest_path.read_text(encoding='utf8'))
    nudges = manifest['nudges']
    assert nudges and all('vertex' in n and 'source_position' in n and 'new_source_position' in n
                          for n in nudges)

    obj = next(o for o in bpy.data.objects if o.name.startswith('FIT_T001'))
    transform = COORD @ obj.matrix_world
    inverse3 = transform.inverted().to_3x3()
    before = geometry_snapshot()
    images_before = image_digests()
    weights_before = weight_snapshot(obj)
    rig = bpy.data.objects['WM_TargetVRoidRig_v01']
    springs_before = len(rig.data.vrm_addon_extension.spring_bone1.springs)
    colliders_before = len(rig.data.vrm_addon_extension.spring_bone1.colliders)

    resolved = resolve_by_position(obj, transform, nudges)
    applied = []
    for blend_indices, native_delta, record in resolved:
        for blend_index in blend_indices:
            obj.data.vertices[blend_index].co += inverse3 @ native_delta
        applied.append({
            'export_vertex': record['vertex'],
            'blend_vertices': blend_indices,
            'move_mm': float(native_delta.length * 1000),
            'depth_m': record['depth_m'],
            'dominant_bone': record['dominant_bone'],
        })
    obj.data.update()

    after = geometry_snapshot()
    changed = {}
    for name in before:
        assert before[name]['faces'] == after[name]['faces'], name
        assert before[name]['uv'] == after[name]['uv'], name
        moved_here = [i for i, (a, b) in enumerate(zip(before[name]['positions'], after[name]['positions']))
                      if a != b]
        if moved_here:
            changed[name] = moved_here
    assert set(changed) == {obj.name}, changed.keys()
    expected_moved = sorted(i for a in applied for i in a['blend_vertices'])
    assert sorted(changed[obj.name]) == expected_moved
    assert image_digests() == images_before
    assert weight_snapshot(obj) == weights_before
    spring_bone = rig.data.vrm_addon_extension.spring_bone1
    assert len(spring_bone.springs) == springs_before
    assert len(spring_bone.colliders) == colliders_before

    out.mkdir(parents=True, exist_ok=False)
    target = out / (stem+'.blend')
    old_version = bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version = 0
        assert 'FINISHED' in bpy.ops.wm.save_as_mainfile(
            filepath=str(target), copy=True, relative_remap=False, compress=True)
    finally:
        bpy.context.preferences.filepaths.save_version = old_version
    copy_digest = fit.digest(target)
    assert fit.digest(source) == original_digest

    # cold reload from the saved file and verify everything from disk
    bpy.ops.wm.open_mainfile(filepath=str(target))
    cold_obj = next(o for o in bpy.data.objects if o.name.startswith('FIT_T001'))
    cold_transform = COORD @ cold_obj.matrix_world
    max_error = 0.0
    for blend_indices, native_delta, record in resolved:
        expected = Vector(record['new_source_position'])
        for blend_index in blend_indices:
            actual = cold_transform @ cold_obj.data.vertices[blend_index].co
            max_error = max(max_error, float((actual - expected).length))
    cold_after = geometry_snapshot()
    cold_changed = {}
    for name in before:
        assert before[name]['faces'] == cold_after[name]['faces'], name
        assert before[name]['uv'] == cold_after[name]['uv'], name
        moved_here = [i for i, (a, b) in enumerate(zip(before[name]['positions'], cold_after[name]['positions']))
                      if a != b]
        if moved_here:
            cold_changed[name] = moved_here
    assert cold_changed == changed
    assert image_digests() == images_before
    assert weight_snapshot(cold_obj) == weights_before
    cold_rig = bpy.data.objects['WM_TargetVRoidRig_v01']
    spring_bone = cold_rig.data.vrm_addon_extension.spring_bone1
    assert len(spring_bone.springs) == springs_before and len(spring_bone.colliders) == colliders_before
    assert max_error < 2e-6, max_error

    meshes = [o for o in bpy.data.collections['FITTED_服装工作副本'].all_objects if o.type == 'MESH']
    assert len(meshes) == 69
    enabled = spring_bone.enable_animation
    poses = {p.name: p.matrix_basis.copy() for p in cold_rig.pose.bones}
    try:
        spring_bone.enable_animation = False
        for pose in cold_rig.pose.bones:
            pose.matrix_basis.identity()
        bpy.context.view_layer.update()
        package = out / (stem+'.xwear')
        manifest_out = exporter.export_xwear(package, cold_rig, meshes,
                                             item_name=stem+' local clearance experiment',
                                             author='Local test asset',
                                             coordinate_matrix=COORD)
        manifest_out.update(source_blend=str(target), source_sha256=copy_digest, experimental=True)
        fit.write_new(package.with_suffix('.xwear.json'), manifest_out)
    finally:
        for pose in cold_rig.pose.bones:
            pose.matrix_basis = poses[pose.name]
        spring_bone.enable_animation = enabled

    report = {
        'source': str(source),
        'source_sha256': original_digest,
        'copy': str(target),
        'copy_sha256': copy_digest,
        'manifest': str(manifest_path),
        'applied_nudges': applied,
        'changed_vertices': changed,
        'topology_uv_images_weights_springs_unchanged': True,
        'cold_reload_max_error_m': max_error,
        'package': str(package),
        'native_acceptance': False,
        'adopted': False,
    }
    fit.write_new(out / 'build.json', report)
    print(json.dumps({'built': str(target), 'nudges': len(applied),
                      'max_move_mm': max(a['move_mm'] for a in applied),
                      'cold_reload_max_error_m': max_error}, ensure_ascii=False))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--stem',default='whale_maid_recovery_clearance_v03')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    build(args.source, args.out, args.manifest,args.stem)
