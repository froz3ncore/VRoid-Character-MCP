"""Cold, read-only scope check of rear-parent/anchor comparison copies."""
import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('source_check', ROOT/'tools/verify_rear_dense_source.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read():
    data = module.read()
    sb = bpy.data.objects['WM_TargetVRoidRig_v01'].data.vrm_addon_extension.spring_bone1
    data['collider_parameters'] = [{
        'uuid':c.uuid,'bone':c.node.bone_name,'shape':c.shape_type,
        'sphere':{'offset':list(c.shape.sphere.offset),'radius':c.shape.sphere.radius},
        'capsule':{'offset':list(c.shape.capsule.offset),'tail':list(c.shape.capsule.tail),
                   'radius':c.shape.capsule.radius},
    } for c in sb.colliders]
    data['collider_groups'] = [{'uuid':g.uuid,'name':g.vrm_name,
        'colliders':[c.collider_uuid for c in g.colliders]} for g in sb.collider_groups]
    return data


def main(args):
    baseline = args.baseline.resolve()
    baseline_hash = digest(baseline)
    assert Path(bpy.data.filepath).resolve() == baseline
    old = read()
    rows = []
    for folder in args.candidate:
        report = json.loads((folder/'build.json').read_text(encoding='utf8'))
        target = Path(report['copy'])
        target_hash = digest(target)
        assert target_hash == report['copy_sha256']
        bpy.ops.wm.open_mainfile(filepath=str(target))
        actual = read()
        assert {k:v for k,v in actual.items() if k!='bones'} == {k:v for k,v in old.items() if k!='bones'}
        parents = {c['bone']:c['after_parent'] for c in report['changes']}
        anchors = {c['bone']:c for c in report.get('anchor_changes',[])}
        max_position, max_matrix = 0., 0.
        assert set(actual['bones']) == set(old['bones'])
        for name, before in old['bones'].items():
            after = actual['bones'][name]
            assert after['parent'] == parents.get(name, before['parent'])
            assert after['deform'] == before['deform']
            if name in anchors:
                for field in ('head','tail'):
                    assert (Vector(after[field])-Vector(anchors[name][field])).length < 2e-6
                continue
            for field in ('head','tail'):
                max_position = max(max_position, *(abs(a-b) for a,b in zip(before[field],after[field])))
            max_matrix = max(max_matrix, *(abs(a-b) for ra,rb in zip(before['matrix'],after['matrix']) for a,b in zip(ra,rb)))
        assert max_position < 2e-6 and max_matrix < 1e-5
        assert digest(target) == target_hash
        rows.append({'source':str(target),'sha256':target_hash,'cold_check_passed':True,
            'geometry_uv_materials_images_weights_springs_colliders_groups_unchanged':True,
            'changed_parents':parents,'changed_anchor_bones':sorted(anchors),
            'unchanged_bones_max_position_delta_m':max_position,
            'unchanged_bones_max_matrix_component_delta':max_matrix})
    assert digest(baseline) == baseline_hash
    with args.out.open('x',encoding='utf8') as stream:
        json.dump({'baseline':str(baseline),'baseline_sha256':baseline_hash,'sources':rows,
                   'adopted':False},stream,ensure_ascii=False,indent=2)
    print(json.dumps({'cold_scope_check_passed':True,'candidates':len(rows)}),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--candidate',type=Path,action='append',required=True)
    parser.add_argument('--out',type=Path,required=True)
    main(parser.parse_args(sys.argv[sys.argv.index('--')+1:]))
