"""Targeted bodice-edge fit and coherent three-bone skirt skin on a v16b copy."""
import argparse,hashlib,importlib.util,json,math,sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Matrix,Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import barycentric_transform

ROOT=Path(__file__).resolve().parents[1]
C=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1)))
SOURCE_SHA='1c1884adff3353f5c3e71d25b10629e4218df2698ceaa7f1b9e5a6c0205a36c3'
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):
    with Path(p).open('x',encoding='utf8') as f:json.dump(d,f,ensure_ascii=False,indent=2)
def smooth(x):
    x=max(0,min(1,x));return x*x*(3-2*x)
def skirt_weights(p,amount):
    radius=math.hypot(p.x,p.z);cos=p.z/max(radius,1e-5)
    front=smooth((cos+.18)/1.03);height=smooth((1.015-p.y)/.18)
    f=amount*front*height;r=smooth((p.x+.15)/.30)
    return {n:w for n,w in [('J_Bip_C_Hips',1-f),('J_Bip_L_UpperLeg',f*(1-r)),('J_Bip_R_UpperLeg',f*r)] if w>1e-8}
def torso_name(n):return any(t in n for t in ('Chest','Spine','Bust'))
def assign(obj,index,weights):
    total=sum(weights.values());assert total>.001
    for g in list(obj.data.vertices[index].groups):obj.vertex_groups[g.group].remove([index])
    for n,w in weights.items():
        group=obj.vertex_groups.get(n) or obj.vertex_groups.new(name=n);group.add([index],w/total,'REPLACE')

def transport_normals(obj,old_positions,old_normals):
    """Transport the authored normal clusters by local face deformation gradients."""
    obj.data.update();new=np.asarray([list(v.co) for v in obj.data.vertices]);old=np.asarray(old_positions)
    moved=np.linalg.norm(new-old,axis=1)>1e-8;acc={};keys=[];pred=[]
    for face in obj.data.polygons:
        ids=list(face.vertices);a,b,c=ids[:3];x1,x2=old[b]-old[a],old[c]-old[a];y1,y2=new[b]-new[a],new[c]-new[a]
        nx=np.cross(x1,x2);ny=np.cross(y1,y2);ax=np.linalg.norm(nx);ay=np.linalg.norm(ny)
        matrix=np.eye(3)
        if moved[ids].any() and min(ax,ay)>1e-12:
            A=np.column_stack((x1,x2,nx/np.sqrt(ax)));B=np.column_stack((y1,y2,ny/np.sqrt(ay)))
            matrix=np.linalg.inv(B@np.linalg.inv(A)).T
        for li in face.loop_indices:
            vi=obj.data.loops[li].vertex_index;n=np.asarray(old_normals[li]);key=(vi,tuple(np.round(n,4)))
            value=matrix@n;value/=max(np.linalg.norm(value),1e-12);weight=max(ay,1e-10)
            acc[key]=acc.get(key,np.zeros(3))+value*weight;keys.append((li,key));pred.append(value)
    values=[None]*len(old_normals)
    for li,key in keys:
        n=acc[key];values[li]=(n/max(np.linalg.norm(n),1e-12)).tolist()
    assert all(v is not None for v in values)
    obj.data.normals_split_custom_set(values)
    return {'custom_normals_transported':True,'corner_normals':len(values),'maximum_vector_change':max((Vector(a)-Vector(b)).length for a,b in zip(old_normals,values)),
        'method':'Area-weighted local inverse-transpose face gradients, preserving original vertex/normal clusters; no UV or topology change.'}

def scope_check(before,after,coordinate_names,weight_names):
    for key,value in before.items():
        if key=='meshes':
            assert value.keys()==after[key].keys()
            for n,row in value.items():
                actual=after[key][n]
                if n in coordinate_names:assert {k:v for k,v in row.items() if k!='co'}=={k:v for k,v in actual.items() if k!='co'},n
                else:assert row==actual,n
        elif key=='weights':
            for n,row in value.items():
                if n not in weight_names:assert row==after[key][n],n
        else:assert value==after[key],key

def build(a):
    source=Path(bpy.data.filepath).resolve();assert digest(source)==SOURCE_SHA and not bpy.data.is_dirty
    out=a.out.resolve();assert not out.exists() and out.is_relative_to(ROOT/'projects/whale-maid')
    scope=load('chest_skirt_scope',ROOT/'tools/verify_rear_mirror_sources.py');before=scope.read()
    reference=json.loads(a.reference.read_text(encoding='utf8'));assert reference['pose_source']=='native_edit'
    body=next(m for m in reference['base_meshes'] if m['name']=='Body')
    m=Matrix(body['world_matrix']);nm=m.to_3x3().inverted().transposed();bp=[m@Vector(p) for p in body['positions']];bn=[(nm@Vector(n)).normalized() for n in body['normals']]
    faces=[body['triangles'][i:i+3] for i in range(0,len(body['triangles']),3)];tree=BVHTree.FromPolygons(bp,faces,all_triangles=True)
    body_names=[reference['bones'][i]['name'] for i in body['bone_ids']]
    def nearest(p):
        q,_,index,_=tree.find_nearest(p);ids=faces[index];n=barycentric_transform(q,*(bp[j] for j in ids),*(bn[j] for j in ids)).normalized()
        # Barycentric skin transfer uses geometric area ratios at the closest point.
        pts=[bp[j] for j in ids];normal=(pts[1]-pts[0]).cross(pts[2]-pts[0]);area=normal.length
        bary=[(pts[(i+1)%3]-q).cross(pts[(i+2)%3]-q).length/max(area,1e-12) for i in range(3)];weights={}
        for j,w in zip(ids,bary):
            for slot,value in zip(body['weights'][j]['indices'],body['weights'][j]['weights']):
                name=body_names[slot]
                if value>1e-8 and torso_name(name):weights[name]=weights.get(name,0)+w*value
        return q,n,weights
    fitted=[o for o in bpy.data.collections['FITTED_服装工作副本'].all_objects if o.type=='MESH'];assert len(fitted)==97
    main=next(o for o in fitted if o.name.startswith('FIT_T001'));rows=[];coordinates=set();weights_changed=set();chest=[]
    old_positions=[list(v.co) for v in main.data.vertices];old_normals=[list(v.vector) for v in main.data.corner_normals]
    assert main.data.has_custom_normals
    for obj in fitted:
        if not obj.name.startswith('FIT_T'):continue
        matrix=C@obj.matrix_world;inv=matrix.inverted();points=[matrix@v.co for v in obj.data.vertices]
        skirt=obj is main or (.30<min(p.y for p in points) and max(p.y for p in points)<1.015)
        changed_skin=0;changed_co=0;maximum=0
        for v,p in zip(obj.data.vertices,points):
            if skirt and p.y<1.015 and not a.preserve_skirt:
                assign(obj,v.index,skirt_weights(p,a.thigh_follow));changed_skin+=1
            if obj is main:
                side=smooth((abs(p.x)-.065)/.035)*(1-smooth((abs(p.x)-.155)/.04))
                frontfade=1-smooth((p.z-.075)/.075);backfade=smooth((p.z+.075)/.045)
                vertical=smooth((p.y-1.095)/.105) if p.y<=1.20 else 1-smooth((p.y-1.20)/.12)
                amount=side*frontfade*backfade*vertical
                if amount>.001:
                    q=p+Vector((0,a.chest_lift*amount,0))
                    for _ in range(2):
                        hit,n,skin=nearest(q)
                        if (q-hit).dot(n)<.004:q=hit+n*.0055
                    delta=(q-p).length
                    assert delta<.115,(v.index,delta)
                    if delta>1e-7:
                        v.co=inv@q;changed_co+=1;maximum=max(maximum,delta)
                        _,_,skin=nearest(q)
                        if skin:
                            skin=dict(sorted(skin.items(),key=lambda kv:-kv[1])[:4]);assign(obj,v.index,skin);changed_skin+=1
                        chest.append({'vertex':v.index,'before':list(p),'after':list(q),'lift_mask':amount})
        if changed_co:coordinates.add(obj.name)
        if changed_skin:weights_changed.add(obj.name)
        if changed_skin or changed_co:rows.append({'mesh':obj.name,'coordinate_vertices':changed_co,'skin_vertices':changed_skin,'maximum_coordinate_move_mm':maximum*1000})
        obj.data.update()
    normal_report=transport_normals(main,old_positions,old_normals)
    scope_check(before,scope.read(),coordinates,weights_changed)
    rig=bpy.data.objects['WM_TargetVRoidRig_v01'];assert all(n in rig.data.bones for n in ('J_Bip_L_UpperLeg','J_Bip_R_UpperLeg'))
    out.mkdir();stem=a.stem;target=out/(stem+'.blend');pref=bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(target),copy=True,compress=True,relative_remap=False)
    finally:bpy.context.preferences.filepaths.save_version=pref
    bpy.ops.wm.open_mainfile(filepath=str(target));scope_check(before,scope.read(),coordinates,weights_changed)
    sb=bpy.data.objects['WM_TargetVRoidRig_v01'].data.vrm_addon_extension.spring_bone1;sb.enable_animation=False
    rig=bpy.data.objects['WM_TargetVRoidRig_v01']
    for p in rig.pose.bones:p.matrix_basis.identity()
    bpy.context.view_layer.update();package=out/(stem+'.xwear');exporter=load('chest_skirt_export',ROOT/'blender-addons/vroid_xwear_direct/__init__.py')
    result=exporter.export_xwear(package,rig,[o for o in bpy.data.collections['FITTED_服装工作副本'].all_objects if o.type=='MESH'],item_name=stem,author='Local creator',coordinate_matrix=C)
    write(package.with_suffix('.xwear.json'),result)
    write(out/'chest-adjustments.json',chest)
    write(out/'build.json',{'source':str(source),'source_sha256':SOURCE_SHA,'copy':str(target),'copy_sha256':digest(target),'package':str(package),'package_sha256':digest(package),
        'coordinate_meshes':sorted(coordinates),'weight_meshes':sorted(weights_changed),'changes':rows,'normal_transport':normal_report,'chest_lift_m':a.chest_lift,'thigh_follow':a.thigh_follow,'reference':str(a.reference.resolve()),'reference_sha256':digest(a.reference),
        'source_topology_uv_materials_images_object_transforms_rig_physics_preserved':True,
        'skirt_preserved':a.preserve_skirt,
        'tradeoff':('Original skirt geometry, skin, spring and collision configuration retained; seated skirt issues remain.' if a.preserve_skirt else 'Skirt garment skin uses continuous hips and bilateral upper-leg influences. Independent skirt spring flutter is removed from these vertices; original spring configuration and bow ribbons are retained. Not a cloth simulation or rear-skirt collision fix.'),
        'native_acceptance':False,'whole_outfit_adopted':False})
    assert digest(source)==SOURCE_SHA
    print(json.dumps({'built':True,'out':str(out),'coordinate_meshes':len(coordinates),'skin_meshes':len(weights_changed),'chest_vertices':len(chest)}),flush=True)

def verify(a):
    candidate=Path(bpy.data.filepath).resolve();build=json.loads((candidate.parent/'build.json').read_text(encoding='utf8'));assert digest(candidate)==build['copy_sha256']
    scope=load('chest_skirt_cold',ROOT/'tools/verify_rear_mirror_sources.py');after=scope.read();matrices={o.name:[list(r) for r in o.matrix_world] for o in bpy.data.objects};checks=[]
    protected_normals={o.name:[tuple(n.vector) for n in o.data.corner_normals] for o in bpy.data.objects if o.type=='MESH' and o.name not in build['coordinate_meshes'] and o.data.has_custom_normals}
    for n in build['weight_meshes']:
        obj=bpy.data.objects[n]
        assert all(0<len(v.groups)<=4 and abs(sum(g.weight for g in v.groups)-1)<1e-5 for v in obj.data.vertices)
        obj.data.calc_loop_triangles();assert all(math.isfinite(x) for v in obj.data.vertices for x in v.co)
        checks.append({'mesh':n,'vertices':len(obj.data.vertices),'maximum_influences':max(len(v.groups) for v in obj.data.vertices)})
    bpy.ops.wm.open_mainfile(filepath=build['source']);scope_check(scope.read(),after,set(build['coordinate_meshes']),set(build['weight_meshes']))
    assert all([tuple(n.vector) for n in bpy.data.objects[name].data.corner_normals]==values for name,values in protected_normals.items())
    assert all([list(r) for r in bpy.data.objects[n].matrix_world]==m for n,m in matrices.items())
    assert digest(candidate)==build['copy_sha256'] and digest(build['source'])==SOURCE_SHA
    write(candidate.parent/'cold-source-check.json',{'passed':True,'candidate':str(candidate),'checks':checks,'topology_uv_materials_packed_images_rig_physics_object_transforms_preserved':True,'protected_v16b_bow_shoes_stockings_head_tail_preserved':True,'source_unchanged':True})
    print(json.dumps({'cold_passed':True,'checked_skin_meshes':len(checks)}),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path);p.add_argument('--reference',type=Path);p.add_argument('--stem',default='whale_maid_chest_skirt_v17b');p.add_argument('--chest-lift',type=float,default=.070);p.add_argument('--thigh-follow',type=float,default=.12);p.add_argument('--preserve-skirt',action='store_true');p.add_argument('--verify',action='store_true')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);verify(a) if a.verify else build(a)
