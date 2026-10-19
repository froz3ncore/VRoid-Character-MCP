"""Cold verify the explicit eight-shoe coordinate-only edit and saved source."""
import argparse,hashlib,importlib.util,json,math,sys
from pathlib import Path
import bpy,bmesh
ROOT=Path(__file__).resolve().parents[1]
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main(a):
    candidate=Path(bpy.data.filepath).resolve();report=json.loads((candidate.parent/'build.json').read_text(encoding='utf8'));sha=digest(candidate);assert sha==report['copy_sha256']
    s=importlib.util.spec_from_file_location('shoe_cold',ROOT/'tools/verify_rear_mirror_sources.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);actual=m.read()
    changed={r['mesh'] for r in report['shoe_envelope_changes']};assert len(changed)==8;rows=[]
    for name in changed:
        obj=bpy.data.objects[name];obj.data.calc_loop_triangles();assert all(t.area>1e-12 for t in obj.data.loop_triangles),name
        assert all(math.isfinite(x) for v in obj.data.vertices for x in v.co),name
        bm=bmesh.new();bm.from_mesh(obj.data);branch=sum(len(e.link_faces)>2 for e in bm.edges);boundaries=sum(e.is_boundary for e in bm.edges);bm.free();assert not branch,name
        rows.append({'mesh':name,'triangles':len(obj.data.loop_triangles),'boundary_edges':boundaries,'nonmanifold_branch_edges':branch})
    bpy.ops.wm.open_mainfile(filepath=report['source']);old=m.read()
    for key in old:
        if key=='meshes':
            for name,value in old[key].items():
                assert {k:v for k,v in value.items() if k!='co'}=={k:v for k,v in actual[key][name].items() if k!='co'},name
                if name not in changed:assert value==actual[key][name],name
        else:assert old[key]==actual[key],key
    assert digest(candidate)==sha and digest(report['source'])==report['source_sha256']
    result={'passed':True,'candidate':str(candidate),'sha256':sha,'source':report['source'],'changed_shoe_meshes':8,'other_meshes_including_13_volumetric_accessories_unchanged':True,'topology_uv_weights_materials_images_bones_springs_colliders_unchanged':True,'mesh_checks':rows,'scope':'Saved source integrity only; open shoe boundaries and appearance are not certified.'}
    with a.out.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({'passed':True,'changed_shoe_meshes':8}),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
