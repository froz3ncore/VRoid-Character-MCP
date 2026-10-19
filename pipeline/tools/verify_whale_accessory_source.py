"""Independent cold check of appearance additions against the protected baseline."""
import argparse
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path

import bpy,bmesh

ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main(a):
    candidate=Path(bpy.data.filepath).resolve();candidate_hash=digest(candidate)
    spec=importlib.util.spec_from_file_location('source_verify',ROOT/'tools/verify_rear_mirror_sources.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    actual=module.read()
    fitted=bpy.data.collections['FITTED_服装工作副本']
    added=[o for o in fitted.all_objects if o.name.startswith('FIT_ACCESSORY_')]
    expected_added=json.loads((candidate.parent/'build.json').read_text(encoding='utf8'))['added_meshes']
    assert {o.name for o in added}==set(expected_added) and len(fitted.all_objects)==69+len(added)
    meshes=[]
    for obj in added:
        obj.data.calc_loop_triangles()
        expected='J_Bip_C_Head' if '_Head_' in obj.name else 'J_Bip_C_Hips'
        for vertex in obj.data.vertices:
            influences=[(obj.vertex_groups[g.group].name,g.weight) for g in vertex.groups if g.weight>1e-7]
            assert influences==[(expected,1.)]
            assert all(math.isfinite(x) for x in vertex.co)
        assert obj.data.uv_layers.active
        assert all(0<=x<=1 for uv in obj.data.uv_layers.active.data for x in uv.uv)
        assert all(tri.area>1e-12 for tri in obj.data.loop_triangles)
        bm=bmesh.new();bm.from_mesh(obj.data)
        nonmanifold=sum(not edge.is_manifold for edge in bm.edges);bm.free()
        if '_WhaleTail_' in obj.name or '_BackBow_' in obj.name:assert nonmanifold==0,(obj.name,nonmanifold)
        meshes.append({'name':obj.name,'vertices':len(obj.data.vertices),'triangles':len(obj.data.loop_triangles),
                       'skin_bone':expected,'nonmanifold_edges':nonmanifold})
    bpy.ops.wm.open_mainfile(filepath=str(a.baseline))
    old=module.read()
    for key in old:
        if key in ('meshes','weights','images'):
            assert all(actual[key][name]==value for name,value in old[key].items()),key
        else:assert actual[key]==old[key],key
    assert set(actual['meshes'])-set(old['meshes'])=={o['name'] for o in meshes}
    assert digest(candidate)==candidate_hash
    result={'passed':True,'baseline':str(a.baseline),'baseline_sha256':digest(a.baseline),
        'candidate':str(candidate),'candidate_sha256':candidate_hash,'added':meshes,
        'added_meshes':len(meshes),'added_triangles':sum(m['triangles'] for m in meshes),
        'all_original_meshes_weights_uv_materials_images_bones_physics_preserved':True,
        'scope':'Saved source, UVs and rigid skin binding; native appearance and motion checked separately.'}
    with a.out.open('x',encoding='utf8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps({'passed':True,'added_meshes':len(meshes),'added_triangles':result['added_triangles']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);a.baseline=a.baseline.resolve();main(a)
