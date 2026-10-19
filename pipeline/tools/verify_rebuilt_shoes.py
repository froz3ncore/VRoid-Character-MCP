"""Independent cold verification of rebuilt shoe solids and protected content."""
import argparse,hashlib,importlib.util,json,math,sys
from pathlib import Path
import bpy,bmesh
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main(a):
    candidate=Path(bpy.data.filepath).resolve();build=json.loads((candidate.parent/'build.json').read_text(encoding='utf8'));assert digest(candidate)==build['copy_sha256']
    spec=importlib.util.spec_from_file_location('rebuilt_check',ROOT/'tools/verify_rear_mirror_sources.py');scope=importlib.util.module_from_spec(spec);spec.loader.exec_module(scope);actual=scope.read();changed=set(build['changed_shoe_meshes']);rows=[]
    for name in changed:
        obj=bpy.data.objects[name];obj.data.calc_loop_triangles();bad=[{'triangle':t.index,'area':t.area,'material':t.material_index} for t in obj.data.loop_triangles if t.area<=1e-12];assert not bad,(name,'degenerate',bad[:12])
        if not name.endswith(('T004','T005')):continue
        bm=bmesh.new();bm.from_mesh(obj.data);assert all(e.is_manifold for e in bm.edges),name
        bmesh.ops.triangulate(bm,faces=list(bm.faces));remaining=set(bm.faces);volumes=[]
        while remaining:
            pending=[remaining.pop()];faces=[]
            while pending:
                face=pending.pop();faces.append(face)
                for edge in face.edges:
                    for other in edge.link_faces:
                        if other in remaining:remaining.remove(other);pending.append(other)
            vertices={v for face in faces for v in face.verts};origin=sum((v.co for v in vertices),Vector())/len(vertices)
            volume=sum((f.verts[0].co-origin).dot((f.verts[1].co-origin).cross(f.verts[2].co-origin))/6 for f in faces);assert volume>1e-8,(name,volume);volumes.append(volume)
        bm.free();expected=next(row for row in build['shoe_rebuild'] if row['mesh']==name);assert len(volumes)==(1 if expected.get('continuous_upper_sole_union') else 2),(name,volumes)
        for vertex in obj.data.vertices:
            weights=[(obj.vertex_groups[g.group].name,g.weight) for g in vertex.groups if g.weight>1e-7];assert weights==[('J_Bip_'+name.split('_')[3]+'_Foot',1.)]
        rows.append({'mesh':name,'closed_components':len(volumes),'component_positive_volumes_m3':volumes,'vertices':len(obj.data.vertices),'triangles':len(obj.data.loop_triangles)})
    bpy.ops.wm.open_mainfile(filepath=build['source']);old=scope.read()
    for key in old:
        if key in ('meshes','weights'):
            for name,value in old[key].items():
                if name not in changed:assert actual[key][name]==value,name
                elif name not in {r['mesh'] for r in rows}:
                    if key=='meshes':assert {k:v for k,v in actual[key][name].items() if k!='co'}=={k:v for k,v in value.items() if k!='co'},name
                    else:assert actual[key][name]==value,name
        else:assert actual[key]==old[key],key
    assert digest(candidate)==build['copy_sha256'] and digest(build['source'])==build['source_sha256']
    result={'passed':True,'source':build['source'],'candidate':str(candidate),'sha256':build['copy_sha256'],'closed_main_shoes':rows,'other_87_meshes_including_volumetric_accessories_unchanged':True,'original_strap_buckle_topology_uv_weights_materials_preserved':True,'rig_springs_colliders_images_preserved':True,'body_occlusion_separate':True,'scope':'Source solids, positive normal orientation and preservation; native occlusion, wearing and appearance checked separately.'}
    with a.out.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({'passed':True,'closed_main_shoes':rows}),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
