"""Cold scope, watertightness and fixed inward-surface checks for 13 pieces."""
import argparse,hashlib,importlib.util,json,sys
from pathlib import Path
import bpy,bmesh
from mathutils import Matrix,Vector
ROOT=Path(__file__).resolve().parents[1];C=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1)))
def main(a):
    candidate=Path(bpy.data.filepath).resolve();sha=hashlib.sha256(candidate.read_bytes()).hexdigest();report=json.loads((candidate.parent/'build.json').read_text(encoding='utf8'));assert sha==report['copy_sha256']
    s=importlib.util.spec_from_file_location('volume_check',ROOT/'tools/verify_rear_mirror_sources.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
    actual=m.read();changed={r['mesh'] for r in report['volume_changes']};checks=[]
    points={}
    for name in changed:
        obj=bpy.data.objects[name];points[name]=[C@obj.matrix_world@v.co for v in obj.data.vertices]
        bm=bmesh.new();bm.from_mesh(obj.data);bad=sum(not e.is_manifold for e in bm.edges);bm.free();assert bad==0,(name,bad)
        obj.data.calc_loop_triangles();assert all(t.area>1e-12 for t in obj.data.loop_triangles),name
        checks.append({'mesh':name,'vertices':len(obj.data.vertices),'triangles':len(obj.data.loop_triangles),'nonmanifold_edges':bad})
    bpy.ops.wm.open_mainfile(filepath=report['source']);old=m.read()
    for key in old:
        if key=='meshes':
            for name,value in old[key].items():
                assert {k:v for k,v in value.items() if k!='co'}=={k:v for k,v in actual[key][name].items() if k!='co'},name
                if name not in changed:assert value==actual[key][name],name
        else:assert old[key]==actual[key],key
    body='FIT_ACCESSORY_WhaleTail_Body';old_body=[C@bpy.data.objects[body].matrix_world@v.co for v in bpy.data.objects[body].data.vertices];new_body=points[body]
    errors=[]
    for row in range(41):errors.append(abs(max(p.z for p in old_body[row*24:(row+1)*24])-max(p.z for p in new_body[row*24:(row+1)*24])))
    shift=sum(new_body[-24:],Vector())/24-sum(old_body[-24:],Vector())/24
    for name in changed-{body}:
        old_points=[C@bpy.data.objects[name].matrix_world@v.co for v in bpy.data.objects[name].data.vertices];new_points=points[name];count=len(old_points)//2;delta=shift.z if 'WhaleTail_Fluke' in name else 0.
        for i in range(count):errors.append(abs(max(new_points[i].z,new_points[i+count].z)-max(old_points[i].z,old_points[i+count].z)-delta))
    assert max(errors)<2e-6,max(errors)
    assert hashlib.sha256(candidate.read_bytes()).hexdigest()==sha
    result={'passed':True,'candidate':str(candidate),'sha256':sha,'source':report['source'],'changed_meshes':len(changed),'checks':checks,'all_thirteen_closed_manifold':True,'other_geometry_topology_uv_weights_materials_images_bones_physics_preserved':True,'maximum_inward_surface_displacement_m':max(errors),'fluke_attachment_translation_m':list(shift),'scope':'Source volume and attachment integrity; native 3D measurements validate actual import separately'}
    with a.out.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({'passed':True,'closed_meshes':13,'maximum_inward_surface_error_m':max(errors)}),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
