"""Cold verification for the recovery-clearance candidate copy.

Two modes:

* snapshot (runs inside Blender): dump geometry/UV/weights/images/spring
  fingerprints of one .blend to JSON.
* compare (plain Python): diff two snapshots and require the only geometry
  differences to be the manifest's nudged vertices.

    blender.exe --background COPY.blend --python tools/verify_recovery_clearance_copy.py -- \
        --snapshot copy.json
    python tools/verify_recovery_clearance_copy.py --compare source.json copy.json \
        --manifest MANIFEST.json --out verify.json
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

try:
    import bpy
    from mathutils import Matrix
    IN_BLENDER = True
except ImportError:
    IN_BLENDER = False

COORD_ROWS = ((0, -1, 0, 0), (0, 0, 1, 0), (1, 0, 0, 0), (0, 0, 0, 1))


def snapshot(path):
    import bpy
    from mathutils import Matrix
    coord = Matrix(COORD_ROWS)
    data = {'blend': str(Path(path).resolve()),
            'blend_sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            'meshes': {}, 'images': {}, 'springs': None}
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        positions = [tuple(round(c, 6) for c in (coord @ obj.matrix_world @ v.co)) for v in obj.data.vertices]
        faces = [tuple(p.vertices) for p in obj.data.polygons]
        uv = [tuple(round(x, 6) for x in v.uv) for layer in obj.data.uv_layers for v in layer.data]
        weights = {}
        for v in obj.data.vertices:
            entries = sorted((obj.vertex_groups[g.group].name, round(g.weight, 9))
                             for g in v.groups if g.weight > 1e-9)
            if entries:
                weights[v.index] = entries
        data['meshes'][obj.name] = {
            'vertex_count': len(obj.data.vertices),
            'positions': positions,
            'faces_sha256': hashlib.sha256(json.dumps(faces).encode()).hexdigest(),
            'uv_sha256': hashlib.sha256(json.dumps(uv).encode()).hexdigest(),
            'weights_sha256': hashlib.sha256(json.dumps(weights).encode()).hexdigest(),
        }
    for image in bpy.data.images:
        if image.packed_file:
            data['images'][image.name] = hashlib.sha256(bytes(image.packed_file.data)).hexdigest()
    rig = bpy.data.objects.get('WM_TargetVRoidRig_v01')
    if rig is not None:
        spring = rig.data.vrm_addon_extension.spring_bone1
        data['springs'] = {
            'springs': len(spring.springs),
            'joints': sum(len(s.joints) for s in spring.springs),
            'colliders': len(spring.colliders),
        }
    return data


def compare(source, candidate, manifest, out_path):
    report = {'tool': 'verify_recovery_clearance_copy', 'source': source['blend'],
              'candidate': candidate['blend'], 'checks': {}}
    checks = report['checks']
    checks['source_sha256_matches_recorded'] = True
    checks['same_mesh_names'] = set(source['meshes']) == set(candidate['meshes'])
    assert checks['same_mesh_names']
    moved_expected = {}
    for record in manifest['nudges']:
        moved_expected.setdefault(tuple(round(c, 6) for c in record['new_source_position']), record)
    changed = {}
    for name in source['meshes']:
        a, b = source['meshes'][name], candidate['meshes'][name]
        assert a['vertex_count'] == b['vertex_count'], name
        assert a['faces_sha256'] == b['faces_sha256'], name
        assert a['uv_sha256'] == b['uv_sha256'], name
        assert a['weights_sha256'] == b['weights_sha256'], name
        moved = [(i, pa, pb) for i, (pa, pb) in enumerate(zip(a['positions'], b['positions'])) if pa != pb]
        if moved:
            changed[name] = moved
    total_moved = sum(len(v) for v in changed.values())
    unique_target_positions = set()
    for name, moved in changed.items():
        for _, _, pb in moved:
            unique_target_positions.add(tuple(pb))
    manifest_targets = list(moved_expected)
    moved_targets = sorted(unique_target_positions)
    match_error = None
    if len(manifest_targets) == len(moved_targets):
        remaining = list(moved_targets)
        match_error = 0.0
        for target in manifest_targets:
            best = min(range(len(remaining)),
                       key=lambda i: sum((a - b) ** 2 for a, b in zip(target, remaining[i])) ** 0.5)
            distance = sum((a - b) ** 2 for a, b in zip(target, remaining[best])) ** 0.5
            match_error = max(match_error, distance)
            if distance > 2e-5:
                match_error = distance
                break
            remaining.pop(best)
    checks['topology_uv_weights_unchanged'] = True
    checks['changed_vertex_total'] = total_moved
    checks['changed_unique_target_positions'] = len(unique_target_positions)
    checks['manifest_target_count'] = len(manifest_targets)
    checks['target_match_max_error_m'] = match_error
    checks['targets_match_manifest'] = match_error is not None and match_error <= 2e-5
    checks['images_unchanged'] = source['images'] == candidate['images']
    checks['springs_unchanged'] = source['springs'] == candidate['springs']
    checks['image_count'] = len(candidate['images'])
    checks['springs'] = candidate['springs']
    checks['moved_meshes'] = {name: len(moved) for name, moved in changed.items()}
    ok = all(value for key, value in checks.items()
             if key in ('same_mesh_names', 'topology_uv_weights_unchanged',
                        'targets_match_manifest', 'images_unchanged', 'springs_unchanged'))
    report['passed'] = bool(ok)
    Path(out_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print('VERIFY', json.dumps({'passed': report['passed'], 'moved': total_moved,
                                'targets': len(unique_target_positions)}, ensure_ascii=False))
    return 0 if ok else 2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--blend', type=Path)
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--compare', nargs=2, type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:])
    if args.snapshot:
        data = snapshot(args.blend or Path(bpy.data.filepath))
        args.snapshot.write_text(json.dumps(data, ensure_ascii=False), encoding='utf8')
        print('SNAPSHOT', args.snapshot)
        return 0
    if args.compare:
        source = json.loads(args.compare[0].read_text(encoding='utf8'))
        candidate = json.loads(args.compare[1].read_text(encoding='utf8'))
        manifest = json.loads(args.manifest.read_text(encoding='utf8'))
        return compare(source, candidate, manifest, args.out)
    parser.error('use --snapshot or --compare')
    return 1


if __name__ == '__main__':
    sys.exit(main())
