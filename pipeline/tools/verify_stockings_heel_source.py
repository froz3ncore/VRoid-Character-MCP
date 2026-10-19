"""Fresh Blender read of neutral stockings, original shoe scope and shade export."""
import argparse,json,sys,math
from pathlib import Path
import bpy
from mathutils import Matrix,Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
from build_stockings_and_heel_copy import load,digest,write,C,CI,ROOT

def main(a):
    candidate=Path(bpy.data.filepath).resolve();build=json.loads((candidate.parent/'build.json').read_text(encoding='utf8'))
    assert digest(candidate)==build['copy_sha256']
    scope=load('sock_cold_scope',ROOT/'tools/verify_rear_mirror_sources.py');after=scope.read()
    data=json.loads(Path(build['native_reference']).read_text(encoding='utf8'));body=next(m for m in data['base_meshes'] if m['name']=='Body')
    assert digest(build['native_reference'])==build['native_reference_sha256']
    wm=Matrix(body['world_matrix']);nm=wm.to_3x3().inverted().transposed();maximum=0.
    for row in build['stockings']:
        obj=bpy.data.objects[row['mesh']];indices=row['original_body_indices']
        for vertex,ident in zip(obj.data.vertices,indices):
            expected=wm@Vector(body['positions'][ident])+(nm@Vector(body['normals'][ident])).normalized()*.00035
            maximum=max(maximum,(C@obj.matrix_world@vertex.co-expected).length)
            expected_weights={data['bones'][body['bone_ids'][k]]['name']:w for k,w in zip(body['weights'][ident]['indices'],body['weights'][ident]['weights']) if w>1e-7}
            assert {obj.vertex_groups[g.group].name:g.weight for g in vertex.groups}==expected_weights
        for loop in obj.data.loops:
            assert max(abs(x-y) for x,y in zip(obj.data.uv_layers.active.data[loop.index].uv,body['uv0'][indices[loop.vertex_index]]))<1e-7
    assert maximum<2e-7,maximum
    export=load('sock_cold_export',ROOT/'blender-addons/vroid_xwear_direct/__init__.py')
    mat=bpy.data.materials['WM_WhiteStocking_NeutralShade_v13'];actual=export.material_resource(mat,{},{});props={p['PropertyName']:p for p in actual['ShaderProperties']}
    rgba=list(props['_ShadeColor']['Color'].values())
    def linear(v):return v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4
    decoded=[linear(linear(v)) for v in rgba[:3]]+[rgba[3]]
    assert max(abs(x-y) for x,y in zip(decoded,[.82,.85,.9,1.]))<1e-6
    temporary=bpy.data.materials.new('Shade guard test');temporary.diffuse_color=(.6,.7,.8,1)
    base=export.material_resource(temporary);default={p['PropertyName']:p for p in base['ShaderProperties']};assert default['_Color']['Color']==default['_ShadeColor']['Color']
    rejected=0
    for value in [[.5,.5,.5],[1.2,.5,.5,1],[.5,.5,.5,.4]]:
        temporary['vroid_mcp_shade_color']=value
        try:export.material_resource(temporary)
        except ValueError:rejected+=1
    assert rejected==3;bpy.data.materials.remove(temporary)
    bpy.ops.wm.open_mainfile(filepath=build['source']);before=scope.read();new={r['mesh'] for r in build['stockings']};shoe_names={n for n in before['meshes'] if n.startswith('FIT_ACCESSORY_Shoe_')};assert len(shoe_names)==8
    delta=Vector((0,0,-.004));rigid_error=0.
    for key in before:
        if key in ('meshes','weights'):
            assert set(after[key])==set(before[key])|new
            for name,value in before[key].items():
                if key=='meshes' and name in shoe_names:
                    assert {k:v for k,v in value.items() if k!='co'}=={k:v for k,v in after[key][name].items() if k!='co'}
                    matrix=C@bpy.data.objects[name].matrix_world
                    for p,q in zip(value['co'],after[key][name]['co']):rigid_error=max(rigid_error,(matrix@Vector(q)-matrix@Vector(p)-delta).length)
                else:assert after[key][name]==value,(key,name)
        elif key=='images':assert all(after[key][n]==v for n,v in before[key].items()) and len(after[key])==len(before[key])+1
        else:assert after[key]==before[key],key
    assert rigid_error<2e-7 and digest(build['source'])==build['source_sha256'] and digest(build['package'])==build['package_sha256']
    write(a.out,{'passed':True,'candidate':str(candidate),'candidate_sha256':build['copy_sha256'],'source_unchanged':True,'original_87_other_meshes_uv_weights_images_rig_and_physics_unchanged':True,'shoe_rigid_transform_error_mm':rigid_error*1000,'stocking_surface_copy_error_mm':maximum*1000,'stocking_original_uv_and_weights_preserved':True,'default_material_shade_unchanged':True,'stocking_shade_wire_rgba':rgba,'stocking_requested_linear_shade_rgba':[.82,.85,.9,1.],'decoded_stocking_shade_rgba':decoded,'invalid_material_shade_cases_rejected':rejected,'native_acceptance_separate':True})
    print(json.dumps({'cold_check_passed':True,'stocking_error_mm':maximum*1000,'shade_guards':rejected}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
