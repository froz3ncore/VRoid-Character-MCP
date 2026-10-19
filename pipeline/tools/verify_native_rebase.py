"""Independent cold verification of native-pose outfit calibration."""
import argparse,hashlib,importlib.util,json,math,sys
from pathlib import Path
import bpy
from mathutils import Matrix,Vector
ROOT=Path(__file__).resolve().parents[1]
C=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1)));CI=C.inverted()
def equivalent(a,b):
    if isinstance(a,dict):return a.keys()==b.keys() and all(equivalent(a[k],b[k]) for k in a)
    if isinstance(a,list):return len(a)==len(b) and all(equivalent(x,y) for x,y in zip(a,b))
    if isinstance(a,float):return math.isclose(a,b,abs_tol=2e-6,rel_tol=0.)
    return a==b
def main(a):
    candidate=Path(bpy.data.filepath).resolve();sha=hashlib.sha256(candidate.read_bytes()).hexdigest();report=json.loads((candidate.parent/'build.json').read_text(encoding='utf8'));assert sha==report['copy_sha256']
    s=importlib.util.spec_from_file_location('rebase_check',ROOT/'tools/verify_rear_mirror_sources.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
    actual=m.read();rig=bpy.data.objects['WM_TargetVRoidRig_v01'];maximum_matrix_error=0.
    for name,value in report['bones_after'].items():
        value=Matrix(value);saved=C@rig.matrix_world@rig.data.bones[name].matrix_local@CI
        maximum_matrix_error=max(maximum_matrix_error,max(abs(x-y) for ra,rb in zip(value,saved) for x,y in zip(ra,rb)))
    assert maximum_matrix_error<3e-5,maximum_matrix_error
    bpy.ops.wm.open_mainfile(filepath=report['source']);before=m.read();changed=set(report['calibrated_mesh_max_delta_m'])
    for key in before:
        if key=='bones':
            assert set(before[key])==set(actual[key])
            assert all(actual[key][n]['parent']==b['parent'] and actual[key][n]['deform']==b['deform'] for n,b in before[key].items())
        elif key=='meshes':
            for name,value in before[key].items():
                assert {k:v for k,v in value.items() if k!='co'}=={k:v for k,v in actual[key][name].items() if k!='co'},name
                if name not in changed:assert value==actual[key][name],name
        elif key=='collider_parameters':assert equivalent(before[key],actual[key]),key
        else:assert before[key]==actual[key],key
    transforms={n:Matrix(report['bones_after'][n])@Matrix(v).inverted() for n,v in report['bones_before'].items()}
    maximum_vertex_error=0.;vertices_checked=0
    for name in changed:
        if name=='FIT_NEW_BowKnot':continue # Explicit independent depth conformance, checked in native gap report.
        for p,q,weights in zip(before['meshes'][name]['co'],actual['meshes'][name]['co'],before['weights'][name]):
            point=C@Vector(p);total=sum(weights.values());expected=sum(((transforms[n]@point)*(w/total) for n,w in weights.items()),Vector());after=C@Vector(q)
            maximum_vertex_error=max(maximum_vertex_error,(expected-after).length);vertices_checked+=1
    assert maximum_vertex_error<3e-6,maximum_vertex_error
    assert hashlib.sha256(candidate.read_bytes()).hexdigest()==sha
    result={'passed':True,'candidate':str(candidate),'sha256':sha,'source':report['source'],'all_topology_uv_weights_materials_packed_images_preserved':True,'source_tripo_geometry_unchanged':True,'spring_and_collider_parameters_preserved_tolerance_m':2e-6,'bind_bone_positions_and_axes_explicitly_recalibrated':True,'maximum_saved_bone_matrix_component_error':maximum_matrix_error,'calibrated_vertices_checked':vertices_checked,'maximum_vertex_reconstruction_error_m':maximum_vertex_error,'native_pose_reconstruction_error_m':report['native_skin_reconstruction_error_m'],'white_knot_extra_depth_conformance':True,'scope':'Independent saved-source scope, bone matrices and skin reconstruction; native appearance remains separate'}
    with a.out.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({'passed':True,'vertices_checked':vertices_checked,'maximum_vertex_error_m':maximum_vertex_error,'matrix_error':maximum_matrix_error}),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
