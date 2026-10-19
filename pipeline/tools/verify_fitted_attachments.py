"""Independent saved-source scope check for mount and shoe restoration."""
import argparse,hashlib,importlib.util,json,math,sys
from pathlib import Path
import bpy,bmesh
ROOT=Path(__file__).resolve().parents[1]
def main(a):
    candidate=Path(bpy.data.filepath).resolve();raw=candidate.read_bytes();report=json.loads((candidate.parent/'build.json').read_text(encoding='utf8'))
    spec=importlib.util.spec_from_file_location('scope',ROOT/'tools/verify_rear_mirror_sources.py');scope=importlib.util.module_from_spec(spec);spec.loader.exec_module(scope)
    actual=scope.read();changed={r['mesh'] for r in report['changed_meshes']};added=set(report['new_shoe_meshes'])
    records=[]
    for obj in bpy.data.collections['FITTED_服装工作副本'].all_objects:
        if obj.name not in changed|added:continue
        obj.data.calc_loop_triangles()
        assert all(math.isfinite(x) for v in obj.data.vertices for x in v.co)
        assert all(t.area>1e-12 for t in obj.data.loop_triangles),(obj.name,'degenerate triangle')
        assert obj.data.uv_layers.active and all(math.isfinite(x) for v in obj.data.uv_layers.active.data for x in v.uv)
        if obj.name in added:
            expected=report['binding_map'][obj.name]
            for v in obj.data.vertices:
                groups=[(obj.vertex_groups[g.group].name,g.weight) for g in v.groups if g.weight>1e-7]
                assert groups==[(expected,1.)]
        bm=bmesh.new();bm.from_mesh(obj.data);boundaries=sum(e.is_boundary for e in bm.edges);bad=sum(len(e.link_faces)>2 for e in bm.edges);bm.free()
        assert bad==0,(obj.name,bad)
        if obj.name in changed:assert boundaries==0,(obj.name,boundaries)
        records.append({'mesh':obj.name,'vertices':len(obj.data.vertices),'triangles':len(obj.data.loop_triangles),'boundary_edges':boundaries,'nonmanifold_branch_edges':bad})
    assert len(bpy.data.collections['FITTED_服装工作副本'].all_objects)==95
    bpy.ops.wm.open_mainfile(filepath=str(a.baseline));old=scope.read()
    assert set(actual['meshes'])-set(old['meshes'])==added
    for key in old:
        if key=='meshes':
            for name,value in old[key].items():
                if name in changed:assert {k:v for k,v in actual[key][name].items() if k!='co'}=={k:v for k,v in value.items() if k!='co'},name
                else:assert actual[key][name]==value,name
        elif key=='weights':assert all(actual[key][n]==v for n,v in old[key].items()),key
        else:assert actual[key]==old[key],key
    assert candidate.read_bytes()==raw
    result={'passed':True,'candidate':str(candidate),'sha256':hashlib.sha256(raw).hexdigest(),'baseline':str(a.baseline),'original_other_meshes_bones_weights_uv_materials_images_physics_preserved':True,'changed_mesh_coordinates':sorted(changed),'new_shoe_meshes':sorted(added),'mesh_checks':records,'scope':'Saved source integrity and explicit changes; actual native appearance checked separately'}
    with a.out.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({'passed':True,'coordinate_changes':len(changed),'new_shoe_meshes':len(added)}),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    main(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
