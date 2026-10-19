"""Cold source/UV provenance and rigid accessory preservation for Tripo repair."""
import argparse, importlib.util, json, sys
from pathlib import Path
import bpy
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from mathutils.geometry import barycentric_transform
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def main(a):
    repair=load('tripo_repair',ROOT/'tools/repair_tripo_shoe_copy.py');scope=load('tripo_check',ROOT/'tools/verify_rear_mirror_sources.py');audit=load('tripo_audit',ROOT/'tools/audit_tripo_shoe_extraction.py')
    candidate=Path(bpy.data.filepath);build=json.loads((candidate.parent/'build.json').read_text(encoding='utf8'));assert repair.digest(candidate)==build['copy_sha256']
    actual=scope.read();manifest=json.loads((ROOT/'projects/whale-maid/tripo-source/parts_manifest_v01.json').read_text(encoding='utf8'));rebase=json.loads((ROOT/'projects/whale-maid/accessory-refinement-v02/candidate-e/build.json').read_text(encoding='utf8'));rows=[];coverage={}
    for record in manifest['parts']:
        if record['source_id'] not in (4,5):continue
        side='R' if record['source_id']==4 else 'L';sign=1 if side=='R' else -1;name='FIT_ACCESSORY_Shoe_'+side+'_T%03d'%record['source_id'];row=next(r for r in build['shoe_changes'] if r['mesh']==name);offset=Vector(row['translation_native_m'])
        original=bpy.data.objects[record['object']];obj=bpy.data.objects[name];old=Matrix(rebase['bones_before']['J_Bip_'+side+'_Foot']);transform=Matrix(rebase['bones_after']['J_Bip_'+side+'_Foot'])@old.inverted()
        points=[transform@Vector(((p.x-sign*.050)*1.6+old.translation.x,p.y*1.35+.020,p.z*1.70-.019)) for p in audit.original_points(record)]
        original.data.calc_loop_triangles();tris=list(original.data.loop_triangles);tree=BVHTree.FromPolygons(points,[tuple(t.vertices) for t in tris],all_triangles=True)
        candidate_tree=BVHTree.FromPolygons([repair.C@obj.matrix_world@v.co-offset for v in obj.data.vertices],[tuple(p.vertices) for p in obj.data.polygons])
        luma=audit.image_sampler(original);source_points=audit.original_points(record);samples=[]
        for face in original.data.polygons:
            ps=[points[i] for i in face.vertices];uvs=[original.data.uv_layers.active.data[i].uv.copy() for i in face.loop_indices]
            if max(source_points[i].y for i in face.vertices)<.045:
                center=sum(ps,Vector())/len(ps)
                for p in [center]+[v*.8+center*.2 for v in ps]:
                    distance=candidate_tree.find_nearest(p)[3];assert distance<2e-6,(name,'lost original sole/heel surface',distance)
            if max(source_points[i].y for i in face.vertices)<.09:
                center=sum(ps,Vector())/len(ps);uv=sum(uvs,Vector((0,0)))/len(uvs)
                if luma(uv)<.30:samples.append((face.index,center,candidate_tree.find_nearest(center)[3]))
        coverage[name]=samples
        max_distance=0.;max_uv=0.
        assert [m.name for m in obj.data.materials]==[m.name for m in original.data.materials]
        for polygon in obj.data.polygons:
            for li in polygon.loop_indices:
                loop=obj.data.loops[li];point=repair.C@obj.matrix_world@obj.data.vertices[loop.vertex_index].co-offset
                hits=tree.find_nearest_range(point,2e-6);assert hits,(name,li)
                max_distance=max(max_distance,min(h[3] for h in hits));uv=Vector((*obj.data.uv_layers.active.data[li].uv,0.));errors=[]
                for hit in hits:
                    tri=tris[hit[2]];uvs=[Vector((*original.data.uv_layers.active.data[i].uv,0.)) for i in tri.loops]
                    expected=barycentric_transform(point,*(points[i] for i in tri.vertices),*uvs)
                    if tri.material_index==polygon.material_index:errors.append((uv-expected).length)
                assert errors,(name,li,'material')
                max_uv=max(max_uv,min(errors))
        assert max_distance<2e-6 and max_uv<5e-4,(name,max_distance,max_uv)
        for v in obj.data.vertices:
            assert [(obj.vertex_groups[g.group].name,g.weight) for g in v.groups]==[('J_Bip_'+side+'_Foot',1.)]
        rows.append({'mesh':name,'maximum_original_surface_error_mm':max_distance*1000,'maximum_original_uv_error':max_uv,'topology':audit.topology(obj.data)})
    bpy.ops.wm.open_mainfile(filepath=build['source']);before=scope.read();changed=set(build['changed_shoe_meshes']);max_rigid_error=0.
    for key in before:
        if key in ('meshes','weights'):
            for name,value in before[key].items():
                if name not in changed:assert actual[key][name]==value,(key,name)
                elif not name.endswith(('T004','T005')):
                    if key=='weights':assert actual[key][name]==value
                    else:
                        assert {k:v for k,v in actual[key][name].items() if k!='co'}=={k:v for k,v in value.items() if k!='co'}
                        obj=bpy.data.objects[name];offset=Vector(next(r for r in build['shoe_changes'] if r['mesh']==name)['translation_native_m'])
                        for old,new in zip(value['co'],actual[key][name]['co']):max_rigid_error=max(max_rigid_error,(repair.C@obj.matrix_world@Vector(new)-repair.C@obj.matrix_world@Vector(old)-offset).length)
        else:assert actual[key]==before[key],key
    assert max_rigid_error<2e-7 and repair.digest(candidate)==build['copy_sha256'] and repair.digest(build['source'])==build['source_sha256']
    recovered=[]
    for name,samples in coverage.items():
        obj=bpy.data.objects[name];tree=BVHTree.FromPolygons([repair.C@obj.matrix_world@v.co for v in obj.data.vertices],[tuple(p.vertices) for p in obj.data.polygons]);improved=[]
        for face,center,distance in samples:
            old_distance=tree.find_nearest(center)[3]
            if old_distance>.0003 and distance<.00002:improved.append({'original_face':face,'old_distance_mm':old_distance*1000,'repaired_distance_mm':distance*1000})
        recovered.append({'mesh':name,'recovered_original_dark_face_centers':improved,'count':len(improved)})
    result={'passed':True,'source':build['source'],'candidate':str(candidate),'sha256':build['copy_sha256'],'original_surface_and_uv_provenance':rows,'original_lower_45mm_surface_samples_retained':True,'recovered_original_dark_surface_centers':recovered,'strap_buckle_rigid_translation_error_mm':max_rigid_error*1000,'other_87_meshes_and_original_tripo_sources_unchanged':True,'images_rig_weights_springs_colliders_preserved':True,'scope':'Original source surface and UV after subtracting rigid fit translation. Intentional shoe openings are retained; native fit and art acceptance are separate.'}
    repair.write(a.out,result);print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
