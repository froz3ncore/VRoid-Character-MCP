"""Conform whale-tail and white-bow attachments to the actual garment back.

Callable through Blender MCP or CLI. Only coordinates of eight explicit meshes
change; the source, topology, weights, textures, rig and physics are protected.
"""
import argparse,hashlib,importlib.util,json,math,sys
from pathlib import Path
import bpy
from mathutils import Matrix,Vector
from mathutils.bvhtree import BVHTree
ROOT=Path(__file__).resolve().parents[1]
C=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1)))
CI=C.inverted();RIG='WM_TargetVRoidRig_v01'
SOURCE_SHA='a9fffbd6ea8d5db469358aa440506c48ddb00dda5e448f3cf0ca0811353ac900'
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,data):
    with p.open('x',encoding='utf8') as f:json.dump(data,f,ensure_ascii=False,indent=2)
def back_surface():
    main=next(o for o in bpy.data.collections['FITTED_服装工作副本'].objects if o.name.startswith('FIT_T001'))
    return BVHTree.FromPolygons([C@main.matrix_world@v.co for v in main.data.vertices],[tuple(p.vertices) for p in main.data.polygons])
def rear_z(tree,x,y):
    for xx in (x,max(-.11,min(.11,x)),0.):
        hit,normal,index,distance=tree.ray_cast(Vector((xx,y,-1)),Vector((0,0,1)),1.10)
        if hit is not None and hit.z<.035:return hit.z
    raise RuntimeError('No garment back for attachment sample '+str((x,y)))
def check_scope(before,after,names,added=()):
    assert set(after['meshes'])-set(before['meshes'])==set(added)
    for key in before:
        if key=='weights':assert all(after[key][n]==v for n,v in before[key].items()),key
        elif key!='meshes':assert before[key]==after[key],key
    for name,data in before['meshes'].items():
        if name in names:assert {k:v for k,v in data.items() if k!='co'}=={k:v for k,v in after['meshes'][name].items() if k!='co'},name
        else:assert data==after['meshes'][name],name
def build(source,out,include_shoes=False):
    source=source.resolve();out=out.resolve()
    assert Path(bpy.data.filepath).resolve()==source and not bpy.data.is_dirty
    assert digest(source)==SOURCE_SHA and not out.exists()
    assert out.is_relative_to(ROOT/'projects/whale-maid')
    verifier=load('mount_verify',ROOT/'tools/verify_rear_mirror_sources.py');before=verifier.read()
    tree=back_surface();fitted=bpy.data.collections['FITTED_服装工作副本']
    changed=[o for o in fitted.objects if o.name.startswith(('FIT_NEW_Bow','FIT_ACCESSORY_WhaleTail_'))]
    changed.sort(key=lambda o:(0 if 'WhaleTail_Body' in o.name else 1,o.name))
    assert len(changed)==8
    old={o.name:[C@o.matrix_world@v.co for v in o.data.vertices] for o in changed}
    rows=[];mounts=[]
    for obj in changed:
        points=old[obj.name];inverse=(C@obj.matrix_world).inverted()
        if 'BowKnot' in obj.name:
            z=rear_z(tree,0,.993);front=max(p.z for p in points);delta=z-.016-front
            for v,p in zip(obj.data.vertices,points):v.co=inverse@(p+Vector((0,0,delta)))
        elif 'BowWing' in obj.name:
            # Keep the loop's fabric relief while its inner edge lies on the dress.
            for i,(v,p) in enumerate(zip(obj.data.vertices,points)):
                u=(i%325)//13/24;across=2*(i%13)/12-1
                surface=rear_z(tree,p.x,p.y)
                relief=.017*math.sin(math.pi*u)*(1-across*across)
                thickness=.0025 if i>=325 else 0.
                q=p.copy();q.z=surface-.004-relief-thickness;v.co=inverse@q
        elif 'BowTail' in obj.name:
            for i,(v,p) in enumerate(zip(obj.data.vertices,points)):
                u=(i%451)//11/40;across=2*(i%11)/10-1
                q=p.copy();q.z=rear_z(tree,p.x,p.y)-.005-.006*(.5+.5*math.sin(3*math.pi*u))*(1-across*across)-(.0025 if i>=451 else 0.)
                v.co=inverse@q
        elif 'WhaleTail_Body' in obj.name:
            for ring in range(41):
                group=points[ring*24:(ring+1)*24];center=sum(group,Vector())/24;t=ring/40
                lift=.024*(1-t)**4;cy=center.y+lift;surface=rear_z(tree,center.x,cy)
                depth=max(p.z for p in group)-center.z;factor=.58+.42*min(1,t/.25)
                cz=surface-depth*factor-.003
                for j,p in enumerate(group):
                    q=p.copy();q.y=cy;q.z=cz+(p.z-center.z)*factor;obj.data.vertices[ring*24+j].co=inverse@q
                if ring in (0,4,20,40):mounts.append({'ring':ring,'x':center.x,'height':cy,'garment_z':surface,'before_front_gap_mm':1000*(surface-max(p.z for p in group)),'after_front_gap_mm':3.})
        else:
            # Preserve the fluke silhouette, moving both lobes by the final tube root.
            tube=bpy.data.objects['FIT_ACCESSORY_WhaleTail_Body']
            current=[C@tube.matrix_world@v.co for v in tube.data.vertices][-24:]
            prior=old['FIT_ACCESSORY_WhaleTail_Body'][-24:]
            delta=sum(current,Vector())/24-sum(prior,Vector())/24
            for v,p in zip(obj.data.vertices,points):v.co=inverse@(p+delta)
        obj.data.update()
        actual=[C@obj.matrix_world@v.co for v in obj.data.vertices]
        rows.append({'mesh':obj.name,'vertices':len(points),'max_move_mm':1000*max((a-b).length for a,b in zip(actual,points))})
    names={o.name for o in changed};added=[];shoe_report=[]
    if include_shoes:
        shoe_module=load('reference_shoes',ROOT/'tools/restore_reference_shoes.py');added,shoe_report=shoe_module.restore()
    added_names=[o.name for o in added]
    check_scope(before,verifier.read(),names,added_names)
    out.mkdir(parents=True)
    target=out/'whale_maid_mounts_footwear_v04.blend'
    preference=bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version=0
        bpy.ops.wm.save_as_mainfile(filepath=str(target),copy=True,compress=True,relative_remap=False)
    finally:bpy.context.preferences.filepaths.save_version=preference
    bpy.ops.wm.open_mainfile(filepath=str(target));check_scope(before,verifier.read(),names,added_names)
    rig=bpy.data.objects[RIG];spring=rig.data.vrm_addon_extension.spring_bone1;enabled=spring.enable_animation
    poses={p.name:p.matrix_basis.copy() for p in rig.pose.bones}
    try:
        spring.enable_animation=False
        for pose in rig.pose.bones:pose.matrix_basis.identity()
        bpy.context.view_layer.update()
        exporter=load('mount_export',ROOT/'blender-addons/vroid_xwear_direct/__init__.py');package=out/'whale_maid_mounts_footwear_v04.xwear'
        # Collections were reloaded by open_mainfile.
        meshes=[o for o in bpy.data.collections['FITTED_服装工作副本'].all_objects if o.type=='MESH']
        exported=exporter.export_xwear(package,rig,meshes,item_name='Whale maid fitted attachments v04',author='Local creator',coordinate_matrix=C)
        write(package.with_suffix('.xwear.json'),exported)
        review=load('mount_review',ROOT/'tools/review_target_cloth.py');review.OUT=out
        for view in ('front','side','back'):review.render_pose('mounts_v04',view)
    finally:
        for pose in rig.pose.bones:pose.matrix_basis=poses[pose.name]
        spring.enable_animation=enabled
    assert digest(source)==SOURCE_SHA
    source_build=json.loads((source.parent/'build.json').read_text(encoding='utf8'))
    report={'source':str(source),'source_sha256':SOURCE_SHA,'copy':str(target),'copy_sha256':digest(target),'package':str(package),'package_sha256':digest(package),'added_meshes':source_build['added_meshes']+added_names,'new_shoe_meshes':added_names,'shoe_extraction':shoe_report,'binding_map':{s['mesh']:s['skin_bone'] for s in shoe_report},'changed_meshes':rows,'tail_mount_samples':mounts,'cold_source_check_passed':True,'geometry_change_scope':'Coordinates of five white waist bow pieces and three whale tail pieces; optional eight isolated shoe parts added','original_topology_uv_weights_materials_images_bones_springs_colliders_preserved':True,'fitted_meshes':87+len(added),'native_acceptance':False,'collision_free_certified':False}
    write(out/'build.json',report);print(json.dumps({'built':True,'out':str(out),'changes':rows,'tail_mount_samples':mounts}),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--include-shoes',action='store_true')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);build(a.source,a.out,a.include_shoes)
