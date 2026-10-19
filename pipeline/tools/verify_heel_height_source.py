"""Fresh-process source comparison for the height-only outfit candidate."""
import argparse, json, sys
from pathlib import Path
import bpy
from mathutils import Matrix, Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
from align_outfit_heel_height import C, ROOT, check, digest, load, write


def main(a):
    candidate = Path(bpy.data.filepath).resolve()
    build = json.loads((candidate.parent/'build.json').read_text(encoding='utf8'))
    assert digest(candidate)==build['copy_sha256'] and digest(build['package'])==build['package_sha256']
    scope = load('height_cold_scope', ROOT/'tools/verify_rear_mirror_sources.py')
    after = scope.read()
    rig_after = bpy.data.objects['WM_TargetVRoidRig_v01'].matrix_world.copy()
    matrices = {o.name:o.matrix_world.copy() for o in bpy.data.objects if o.type=='MESH'}
    bpy.ops.wm.open_mainfile(filepath=build['source'])
    before = scope.read()
    rig_before = bpy.data.objects['WM_TargetVRoidRig_v01'].matrix_world.copy()
    delta = Vector(build['measured_height_delta_m'])
    check(before,after,set(build['translated_meshes']),delta)
    expected = C.to_3x3()@(rig_after.translation-rig_before.translation)
    assert (expected-delta).length<2e-7
    assert max(abs(rig_before[i][j]-rig_after[i][j]) for i in range(3) for j in range(3))<1e-7
    mesh_transform_error = max(abs(x-y) for name,mat in matrices.items() for row,old in zip(bpy.data.objects[name].matrix_world,mat) for x,y in zip(row,old))
    assert mesh_transform_error<2e-7 and digest(build['source'])==build['source_sha256']
    write(a.out,{'passed':True,'candidate':str(candidate),'sha256':build['copy_sha256'],'reference_bones':build['matched_bones'],'height_translation_mm':[v*1000 for v in delta],'changed_meshes':len(build['translated_meshes']),'shoe_stocking_world_geometry_unchanged':True,'mesh_transform_max_error':mesh_transform_error,'topology_uv_weights_materials_images_local_bones_and_physics_parameters_preserved':True,'source_unchanged':True,'native_acceptance_separate':True})
    print(json.dumps({'cold_check_passed':True,'height_mm':delta.y*1000}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--out',type=Path,required=True)
    main(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
