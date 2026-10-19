"""Repair texture extraction on original Tripo surfaces; rigid fit only."""
import argparse, hashlib, importlib.util, json, sys
from pathlib import Path
import bpy, bmesh
from mathutils import Matrix, Vector
ROOT=Path(__file__).resolve().parents[1]
C=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1)))

def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):
    with p.open('x',encoding='utf8') as f:json.dump(d,f,ensure_ascii=False,indent=2)

def repair_mesh(record,rebase,offset):
    audit=load('tripo_audit',ROOT/'tools/audit_tripo_shoe_extraction.py')
    original=bpy.data.objects[record['object']];points=audit.original_points(record);luma=audit.image_sampler(original)
    side='R' if record['source_id']==4 else 'L';sign=1 if side=='R' else -1;bone='J_Bip_'+side+'_Foot'
    old=Matrix(rebase['bones_before'][bone]);transform=Matrix(rebase['bones_after'][bone])@old.inverted()
    fitted=bpy.data.objects['FIT_ACCESSORY_Shoe_'+side+'_T%03d'%record['source_id']]
    inverse=(C@fitted.matrix_world).inverted()
    def fit(p):return inverse@(transform@Vector(((p.x-sign*.050)*1.6+old.translation.x,p.y*1.35+.020,p.z*1.70-.019))+offset)
    bm=bmesh.new();bm.from_mesh(original.data);uv=bm.loops.layers.uv.active
    for v,p in zip(bm.verts,points):v.co=p
    # Conforming edge splits interpolate the original UVs. Adjacent faces share
    # split edges, avoiding T junctions from independent per-face tessellation.
    for level in range(5):
        edges=set()
        for face in bm.faces:
            if min(v.co.y for v in face.verts)>.091:continue
            us=[loop[uv].uv.copy() for loop in face.loops]
            samples=us+[(a+b)*.5 for a,b in zip(us,us[1:]+us[:1])]+[sum(us,Vector((0,0)))/len(us)]
            values=[luma(u) for u in samples]
            if min(values)<.42<max(values) or min(v.co.y for v in face.verts)<.09<max(v.co.y for v in face.verts):
                edges.update(e for e in face.edges if e.calc_length()>.0005)
        if not edges:break
        bmesh.ops.subdivide_edges(bm,edges=list(edges),cuts=1,use_grid_fill=True)
    vertices=[];faces=[];uvs=[];material_ids=[];source_faces=0
    def clip(items,value):
        result=[]
        for a,b in zip(items,items[1:]+items[:1]):
            av,bv=value(a),value(b)
            if av>=0:result.append(a)
            if (av>=0)!=(bv>=0):
                t=av/(av-bv);result.append((a[0].lerp(b[0],t),a[1].lerp(b[1],t)))
        return result
    for face in bm.faces:
        polygon=[(loop.vert.co.copy(),loop[uv].uv.copy()) for loop in face.loops]
        polygon=clip(polygon,lambda a:.09-a[0].y)
        if len(polygon)<3:continue
        polygon=clip(polygon,lambda a:.42-luma(a[1]))
        if len(polygon)<3:continue
        if luma(sum((u for p,u in polygon),Vector((0,0)))/len(polygon))>.50:continue
        start=len(vertices);vertices.extend(fit(p) for p,u in polygon);uvs.extend(u for p,u in polygon)
        faces.append(tuple(range(start,len(vertices))));material_ids.append(face.material_index);source_faces+=1
    bm.free();mesh=bpy.data.meshes.new('Tripo original UV boundary repair '+side);mesh.from_pydata(vertices,[],faces);mesh.update()
    for material in original.data.materials:mesh.materials.append(material)
    layer=mesh.uv_layers.new(name='OriginalUV_boundary_refined')
    for loop in mesh.loops:layer.data[loop.index].uv=uvs[loop.vertex_index]
    for face,slot in zip(mesh.polygons,material_ids):face.material_index=slot;face.use_smooth=True
    bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=1e-7)
    # Remove numerical slivers from near-threshold clipping, without filling
    # shoe openings or replacing the original outsole/heel.
    bad=[f for f in bm.faces if f.calc_area()<1e-12]
    if bad:bmesh.ops.delete(bm,geom=bad,context='FACES_ONLY')
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(mesh);bm.free();mesh.update()
    fitted.data=mesh;fitted.vertex_groups.clear();g=fitted.vertex_groups.new(name=bone);g.add(list(range(len(mesh.vertices))),1.,'REPLACE')
    fitted['repair_scope']='Original Tripo surface / interpolated original UV; refined extraction boundary, rigid translation only'
    mesh.calc_loop_triangles()
    return {'mesh':fitted.name,'vertices':len(mesh.vertices),'triangles':len(mesh.loop_triangles),'topology':audit.topology(mesh),'translation_native_m':list(offset),'source_part':record['source_id']}

def main(a):
    source=Path(bpy.data.filepath).resolve();sha=digest(source);out=a.out.resolve();assert not bpy.data.is_dirty
    assert sha=='b2935adaa39f354c04ed406a5598cf0710718ee4d104de18b5e7c5b98ffd6e74'
    assert out.is_relative_to(ROOT/'projects/whale-maid') and not (out/'build.json').exists()
    out.mkdir(exist_ok=True);scope=load('repair_scope',ROOT/'tools/verify_rear_mirror_sources.py');before=scope.read()
    manifest=json.loads((ROOT/'projects/whale-maid/tripo-source/parts_manifest_v01.json').read_text(encoding='utf8'))
    rebase=json.loads((ROOT/'projects/whale-maid/accessory-refinement-v02/candidate-e/build.json').read_text(encoding='utf8'))
    rows=[];offsets={side:Vector(((1 if side=='R' else -1)*.006,-.003,-.012)) for side in ['L','R']}
    for record in manifest['parts']:
        if record['source_id'] in (4,5):rows.append(repair_mesh(record,rebase,offsets['R' if record['source_id']==4 else 'L']))
    for obj in bpy.data.collections['FITTED_服装工作副本'].all_objects:
        if not obj.name.startswith('FIT_ACCESSORY_Shoe_') or obj.name.endswith(('T004','T005')):continue
        offset=offsets[obj.name.split('_')[3]];inverse=(C@obj.matrix_world).inverted()
        for v in obj.data.vertices:v.co=inverse@(C@obj.matrix_world@v.co+offset)
        obj.data.update();rows.append({'mesh':obj.name,'translation_native_m':list(offset),'topology_uv_material_weights_unchanged':True})
    after=scope.read();changed={r['mesh'] for r in rows};assert len(changed)==8
    for key in before:
        if key in ('meshes','weights'):
            for name,value in before[key].items():
                if name not in changed:assert after[key][name]==value,(key,name)
        else:assert before[key]==after[key],key
    stem='whale_maid_tripo_shoe_repair_v11';target=out/(stem+'.blend');assert not target.exists()
    previous=bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(target),copy=True,relative_remap=False,compress=True)
    finally:bpy.context.preferences.filepaths.save_version=previous
    bpy.ops.wm.open_mainfile(filepath=str(target));assert scope.read()==after
    rig=bpy.data.objects['WM_TargetVRoidRig_v01'];sb=rig.data.vrm_addon_extension.spring_bone1;enabled=sb.enable_animation;poses={p.name:p.matrix_basis.copy() for p in rig.pose.bones}
    try:
        sb.enable_animation=False
        for p in rig.pose.bones:p.matrix_basis.identity()
        bpy.context.view_layer.update();export=load('repair_export',ROOT/'blender-addons/vroid_xwear_direct/__init__.py');package=out/(stem+'.xwear')
        result=export.export_xwear(package,rig,[o for o in bpy.data.collections['FITTED_服装工作副本'].all_objects if o.type=='MESH'],item_name='Whale maid original Tripo shoes, extraction repair v11',author='Local creator',coordinate_matrix=C)
        write(package.with_suffix('.xwear.json'),result)
    finally:
        for p in rig.pose.bones:p.matrix_basis=poses[p.name]
        sb.enable_animation=enabled
    assert digest(source)==sha
    write(out/'build.json',{'source':str(source),'source_sha256':sha,'copy':str(target),'copy_sha256':digest(target),'package':str(package),'package_sha256':digest(package),'shoe_changes':rows,'changed_shoe_meshes':sorted(changed),'scope':'Original surface extraction boundary repair on two main shoes; same rigid translation for all shoe/strap/buckle parts per foot. No resculpt or generated shoe last.','native_acceptance':False,'adopted':False,'shoe_fit_complete':False,'body_occlusion_applied':False})
    print(json.dumps({'built':True,'out':str(out),'changes':rows}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
