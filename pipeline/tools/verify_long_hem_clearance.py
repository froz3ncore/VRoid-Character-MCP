"""Cold-read the final local clearance patch and all protected parameters."""
import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix,Vector

ROOT=Path(__file__).resolve().parents[1]


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main(a):
    report=json.loads(a.build.read_text(encoding='utf8'))
    source,target=Path(report['source']),Path(report['copy'])
    assert Path(bpy.data.filepath).resolve()==source.resolve()
    assert digest(source)==report['source_sha256'] and digest(target)==report['copy_sha256']
    verifier=load('mirror_verify',ROOT/'tools/verify_rear_mirror_sources.py')
    builder=load('clearance_builder',ROOT/'tools/build_recovery_clearance_copy.py')
    old=verifier.read()
    obj=next(o for o in bpy.data.objects if o.name.startswith('FIT_T001'))
    name=obj.name
    transform=builder.COORD@obj.matrix_world
    manifest=json.loads(Path(report['manifest']).read_text(encoding='utf8'))
    resolved=builder.resolve_by_position(obj,transform,manifest['nudges'])
    expected={i:Vector(row['new_source_position']) for indices,_,row in resolved for i in indices}
    bpy.ops.wm.open_mainfile(filepath=str(target))
    new=verifier.read()
    assert {k:v for k,v in old.items() if k!='meshes'}=={k:v for k,v in new.items() if k!='meshes'}
    moved={};max_error=0.;max_move=0.
    for mesh,before in old['meshes'].items():
        after=new['meshes'][mesh]
        assert {k:v for k,v in before.items() if k!='co'}=={k:v for k,v in after.items() if k!='co'}
        for index,(p,q) in enumerate(zip(before['co'],after['co'])):
            if p==q:continue
            assert mesh==name and index in expected,(mesh,index)
            pa,pb=transform@Vector(p),transform@Vector(q)
            assert abs(pa.y-pb.y)<1e-8
            max_move=max(max_move,(pb-pa).length)
            max_error=max(max_error,(pb-expected[index]).length)
            moved[index]=True
    assert set(moved)==set(expected)
    assert max_move<=.040002 and max_error<2e-6
    assert digest(source)==report['source_sha256'] and digest(target)==report['copy_sha256']
    result={'passed':True,'source':str(source),'source_sha256':digest(source),
        'candidate':str(target),'candidate_sha256':digest(target),
        'changed_blender_vertices':len(moved),'declared_position_groups':len(resolved),
        'max_added_source_move_mm':max_move*1000,'target_max_error_m':max_error,
        'native_y_coordinates_unchanged':True,
        'all_other_geometry_uv_materials_images_weights_bones_springs_colliders_groups_unchanged':True,
        'unpacked_images':[{'name':i.name,'path':bpy.path.abspath(i.filepath)} for i in bpy.data.images if not i.packed_file and i.source=='FILE'],
        'adopted':False,'native_acceptance':False}
    with a.out.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    main(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
