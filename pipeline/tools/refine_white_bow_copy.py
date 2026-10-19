"""Reference-led white waist bow silhouette on a protected v15b source copy."""
import argparse, hashlib, importlib.util, json, math, sys
from pathlib import Path
import bpy, bmesh
from mathutils import Matrix, Vector

ROOT=Path(__file__).resolve().parents[1]
C=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1)))
SOURCE_SHA='e4aa69e740848e11d5130cf652de19eece7a6747e2aeb2e0d28853ec9d94742b'
NAMES=['FIT_NEW_BowWing_N','FIT_NEW_BowWing_P','FIT_NEW_BowTail_N','FIT_NEW_BowTail_P','FIT_NEW_BowKnot']
REF_NAME='REF_CURRENT_HEEL_Body_v16'

def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):
    with Path(p).open('x',encoding='utf8') as f:json.dump(d,f,ensure_ascii=False,indent=2)
def smooth(t):
    t=min(1,max(0,t));return t*t*(3-2*t)
def native(obj):return [C@obj.matrix_world@v.co for v in obj.data.vertices]

def scope_check(old,new):
    assert set(new['meshes'])==set(old['meshes'])|{REF_NAME}
    for key,value in old.items():
        if key in ('meshes','weights'):
            for name,row in value.items():
                actual=new[key][name]
                if key=='meshes' and name in NAMES:
                    assert {k:v for k,v in row.items() if k!='co'}=={k:v for k,v in actual.items() if k!='co'},name
                else:assert row==actual,(key,name)
        else:assert value==new[key],key

def checks():
    rows=[]
    for name in NAMES:
        obj=bpy.data.objects[name];bm=bmesh.new();bm.from_mesh(obj.data)
        bad=sum(not e.is_manifold for e in bm.edges);volume=bm.calc_volume(signed=True);bm.free()
        obj.data.calc_loop_triangles();minimum=min(t.area for t in obj.data.loop_triangles)
        assert bad==0 and minimum>1e-12 and abs(volume)>1e-8,(name,bad,minimum,volume)
        pts=native(obj)
        rows.append({'name':name,'vertices':len(pts),'triangles':len(obj.data.loop_triangles),'nonmanifold_edges':bad,'signed_volume_m3':volume,
            'minimum_triangle_area_m2':minimum,'bounds':[[min(p[i] for p in pts),max(p[i] for p in pts)] for i in range(3)]})
    return rows

def reference(path):
    data=json.loads(path.read_text(encoding='utf8'));assert data['pose_source']=='native_edit'
    body=data['body'];world=Matrix(body['world_matrix']);pts=[C.inverted()@world@Vector(p) for p in body['positions']]
    faces=[body['triangles'][i:i+3] for i in range(0,len(body['triangles']),3)]
    coll=bpy.data.collections.new('REFERENCE_CurrentHighHeel_v16_hidden')
    bpy.context.scene.collection.children.link(coll)
    mesh=bpy.data.meshes.new(REF_NAME);mesh.from_pydata(pts,[],faces);mesh.update()
    obj=bpy.data.objects.new(REF_NAME,mesh);coll.objects.link(obj)
    obj['reference_file']=str(path);obj['reference_sha256']=digest(path);obj['scope']='Current native edit Body reference only; no export, no anatomy or skin edits'
    coll.hide_viewport=True;coll.hide_render=True
    return {'name':REF_NAME,'source':str(path),'sha256':digest(path),'vertices':len(pts),'triangles':len(faces),'native_frame':data['frame']}

def build(a):
    source=Path(bpy.data.filepath).resolve();assert digest(source)==SOURCE_SHA and not bpy.data.is_dirty
    out=a.out.resolve();assert not out.exists() and out.is_relative_to(ROOT/'projects/whale-maid')
    scope=load('bow_scope',ROOT/'tools/verify_rear_mirror_sources.py');before=scope.read()
    matrices={o.name:[list(r) for r in o.matrix_world] for o in bpy.data.objects};rows=[]
    for name in NAMES:
        obj=bpy.data.objects[name];assert not obj.data.has_custom_normals
        old=native(obj);inv=(C@obj.matrix_world).inverted()
        nr,nc=(24,12) if 'Wing' in name else (40,10) if 'Tail' in name else (12,12)
        count=(nr+1)*(nc+1);assert len(old)==2*count
        sign=1 if name.endswith('_N') else -1
        center_x=-.00002385;max_root_error=0
        for i in range(count):
            row,col=divmod(i,nc+1);u=row/nr;v=2*col/nc-1
            front=max(old[i].z,old[i+count].z);depth=abs(old[i].z-old[i+count].z)
            blend=smooth((u-.125)/.875)
            for index in (i,i+count):
                p=old[index];q=p.copy()
                if 'Wing' in name:
                    x=center_x+sign*(.014+.105*u+.008*u**5*(1-v*v))
                    y=1.03403795+.020*u+.004*math.sin(math.pi*u)+v*(.012+.028*math.sin(math.pi*u/2))*(1-.12*u**8)
                    z=-.065-.017*u-.007*math.sin(math.pi*u)*(1-v*v)+.004*math.sin(2*math.pi*v+.6*u)*math.sin(math.pi*u)*(1-v*v)
                    if p.z<front-1e-7:z-=depth
                    q=p.lerp(Vector((x,y,z)),blend)
                elif 'Tail' in name:
                    flare=.070 if sign==1 else .095
                    length=.246 if sign==1 else .213
                    width=.025+.005*u+.004*math.sin(math.pi*u)
                    x=center_x+sign*(.034+flare*u)-v*width
                    y=1.01903795-length*u+.009*v*u**5+.004*math.sin(math.pi*v)*u**5
                    # Retain the existing depth conformance and skinning; reshape the visible cut and flare.
                    q.x=p.x+(x-p.x)*blend;q.y=p.y+(y-p.y)*blend
                    q.z=p.z-.0025*math.sin(2*math.pi*v+.6*u)*(1-v*v)*math.sin(math.pi*u)*blend
                else:
                    # Tighter wrap with an outward rounded face, preserving its body-facing surface.
                    q.x=center_x+(p.x-center_x)*(.80+.12*math.sin(math.pi*u))
                    if p.z<front-1e-7:q.z=front-(.019+.008*math.sin(math.pi*u)*(1-.6*v*v))
                if 'Knot' not in name and u<=.125:max_root_error=max(max_root_error,(p-q).length)
                obj.data.vertices[index].co=inv@q
        obj.data.update()
        new=native(obj)
        rows.append({'name':name,'maximum_move_mm':1000*max((p-q).length for p,q in zip(old,new)),
            'maximum_pinned_root_error_mm':max_root_error*1000,'changed_vertices':sum((p-q).length>1e-7 for p,q in zip(old,new))})
    ref=reference(a.reference.resolve());scope_check(before,scope.read());geometry=checks()
    assert all([list(r) for r in bpy.data.objects[n].matrix_world]==m for n,m in matrices.items())
    out.mkdir();stem=a.stem;assert stem.replace('_','').isalnum() and stem.isascii();target=out/(stem+'.blend')
    pref=bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version=0
        bpy.ops.wm.save_as_mainfile(filepath=str(target),copy=True,compress=True,relative_remap=False)
    finally:bpy.context.preferences.filepaths.save_version=pref
    bpy.ops.wm.open_mainfile(filepath=str(target));scope_check(before,scope.read());checks()
    rig=bpy.data.objects['WM_TargetVRoidRig_v01'];sb=rig.data.vrm_addon_extension.spring_bone1
    sb.enable_animation=False
    for p in rig.pose.bones:p.matrix_basis.identity()
    bpy.context.view_layer.update()
    exporter=load('bow_export',ROOT/'blender-addons/vroid_xwear_direct/__init__.py')
    meshes=[o for o in bpy.data.collections['FITTED_服装工作副本'].all_objects if o.type=='MESH'];assert len(meshes)==97
    package=out/(stem+'.xwear')
    result=exporter.export_xwear(package,rig,meshes,item_name='Whale maid reference white waist bow v16',author='Local creator',coordinate_matrix=C)
    write(package.with_suffix('.xwear.json'),result)
    assert digest(source)==SOURCE_SHA
    write(out/'build.json',{'source':str(source),'source_sha256':SOURCE_SHA,'copy':str(target),'copy_sha256':digest(target),
        'package':str(package),'package_sha256':digest(package),'changes':rows,'geometry_checks':geometry,'current_body_reference':ref,
        'scope':'5 white waist bow coordinate streams only, plus hidden current Body reference. Other 92 fitted meshes, original sources, UV, weights, materials, packed images, rig, object transforms and physics preserved.',
        'fitted_meshes':97,'native_acceptance':False,'whole_outfit_adopted':False,'rear_skirt_collision':'paused'})
    review=load('bow_review',ROOT/'tools/inspect_white_bow.py');review.render(out,'candidate')
    print(json.dumps({'built':True,'out':str(out),'changed_meshes':5}),flush=True)

def verify(a):
    candidate=Path(bpy.data.filepath).resolve();build=json.loads((candidate.parent/'build.json').read_text(encoding='utf8'))
    assert digest(candidate)==build['copy_sha256'];scope=load('bow_cold_scope',ROOT/'tools/verify_rear_mirror_sources.py')
    after=scope.read();geometry=checks();matrices={o.name:[list(r) for r in o.matrix_world] for o in bpy.data.objects if o.name!=REF_NAME}
    points={n:native(bpy.data.objects[n]) for n in NAMES};source=Path(build['source'])
    bpy.ops.wm.open_mainfile(filepath=str(source));before=scope.read();scope_check(before,after)
    source_geometry={r['name']:r for r in checks()}
    assert all(r['signed_volume_m3']*source_geometry[r['name']]['signed_volume_m3']>0 for r in geometry),'Source winding orientation changed'
    root_error=0
    for name in NAMES:
        if 'Knot' in name:continue
        nr,nc=(24,12) if 'Wing' in name else (40,10);count=(nr+1)*(nc+1);old=native(bpy.data.objects[name])
        for i in range(2*count):
            if ((i%count)//(nc+1))/nr<=.125:root_error=max(root_error,(old[i]-points[name][i]).length)
    assert root_error<3e-7,root_error
    assert all([list(r) for r in bpy.data.objects[n].matrix_world]==m for n,m in matrices.items())
    assert digest(source)==SOURCE_SHA and digest(candidate)==build['copy_sha256'] and digest(build['package'])==build['package_sha256']
    write(candidate.parent/'cold-source-check.json',{'passed':True,'candidate':str(candidate),'sha256':build['copy_sha256'],'source_unchanged':True,
        'geometry_checks':geometry,'five_closed_manifold':True,'maximum_pinned_root_error_mm':root_error*1000,
        'other_92_fitted_meshes_and_original_sources_preserved':True,'uv_weights_materials_images_rig_physics_object_transforms_preserved':True,
        'current_body_reference_hidden_and_excluded_from_package':True})
    print(json.dumps({'cold_source_passed':True,'root_error_mm':root_error*1000}),flush=True)

def finish_existing(a):
    """Complete export after a known saved-copy / temporary-path failure, without resaving."""
    target=Path(bpy.data.filepath).resolve();out=target.parent
    assert target.name=='whale_maid_white_bow_v16.blend' and not bpy.data.is_dirty
    assert not (out/'build.json').exists() and not target.with_suffix('.xwear').exists()
    scope=load('finish_bow_scope',ROOT/'tools/verify_rear_mirror_sources.py');after=scope.read()
    geometry=checks();points={n:native(bpy.data.objects[n]) for n in NAMES};sha=digest(target)
    source=ROOT/'projects/whale-maid/accessory-refinement-v02/shoe-heading-v15b/whale_maid_shoe_heading_v15.blend'
    bpy.ops.wm.open_mainfile(filepath=str(source));assert digest(source)==SOURCE_SHA;scope_check(scope.read(),after)
    prior={r['name']:r for r in checks()};rows=[]
    for name in NAMES:
        old=native(bpy.data.objects[name]);new=points[name]
        assert next(r for r in geometry if r['name']==name)['signed_volume_m3']*prior[name]['signed_volume_m3']>0
        nr,nc=(24,12) if 'Wing' in name else (40,10) if 'Tail' in name else (12,12);count=(nr+1)*(nc+1)
        root=max(((p-q).length for i,(p,q) in enumerate(zip(old,new)) if ((i%count)//(nc+1))/nr<=.125),default=0) if 'Knot' not in name else 0
        assert root<3e-7
        rows.append({'name':name,'maximum_move_mm':1000*max((p-q).length for p,q in zip(old,new)),
            'maximum_pinned_root_error_mm':root*1000,'changed_vertices':sum((p-q).length>1e-7 for p,q in zip(old,new))})
    bpy.ops.wm.open_mainfile(filepath=str(target));ref=bpy.data.objects[REF_NAME]
    ref_record={'name':REF_NAME,'source':ref['reference_file'],'sha256':ref['reference_sha256'],'vertices':len(ref.data.vertices),'triangles':len(ref.data.polygons)}
    assert digest(ref_record['source'])==ref_record['sha256']
    rig=bpy.data.objects['WM_TargetVRoidRig_v01'];rig.data.vrm_addon_extension.spring_bone1.enable_animation=False
    for p in rig.pose.bones:p.matrix_basis.identity()
    bpy.context.view_layer.update();meshes=[o for o in bpy.data.collections['FITTED_服装工作副本'].all_objects if o.type=='MESH'];assert len(meshes)==97
    package=target.with_suffix('.xwear');exporter=load('finish_bow_export',ROOT/'blender-addons/vroid_xwear_direct/__init__.py')
    result=exporter.export_xwear(package,rig,meshes,item_name='Whale maid reference white waist bow v16',author='Local creator',coordinate_matrix=C)
    write(package.with_suffix('.xwear.json'),result)
    write(out/'build.json',{'source':str(source),'source_sha256':SOURCE_SHA,'copy':str(target),'copy_sha256':sha,
        'package':str(package),'package_sha256':digest(package),'changes':rows,'geometry_checks':geometry,'current_body_reference':ref_record,
        'scope':'5 white waist bow coordinate streams only, plus hidden current Body reference. Other 92 fitted meshes, original sources, UV, weights, materials, packed images, rig, object transforms and physics preserved.',
        'fitted_meshes':97,'native_acceptance':False,'whole_outfit_adopted':False,'rear_skirt_collision':'paused','completed_saved_copy_without_resaving':True})
    load('finish_bow_render',ROOT/'tools/inspect_white_bow.py').render(out,'candidate')
    assert digest(target)==sha and digest(source)==SOURCE_SHA
    print(json.dumps({'completed_saved_copy':True,'out':str(out)}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path);p.add_argument('--reference',type=Path);p.add_argument('--verify',action='store_true');p.add_argument('--finish-existing',action='store_true');p.add_argument('--stem',default='whale_maid_white_bow_v16b')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);verify(a) if a.verify else finish_existing(a) if a.finish_existing else build(a)
