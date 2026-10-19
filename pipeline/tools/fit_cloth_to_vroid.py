"""Blender MCP operations using an actual validated VRoid body snapshot.

init_target() preserves the Tripo/spring source hierarchy in a hidden collection.
fit_clothes() derives garment copies, removes identified generated skin patches,
maps proportions and transfers upper-garment skin weights to the captured skeleton.
"""
import bpy,bmesh,json,math,hashlib
from pathlib import Path
from mathutils import Matrix,Vector
from mathutils.bvhtree import BVHTree
from collections import defaultdict

ROOT=Path(r'D:\vroidmcp')
BODY=ROOT/'projects/whale-maid/target-body/whale_maid_vroid_body_reference.json'
OUT=ROOT/'projects/whale-maid/target-fit-v01'
RIG='WM_TargetVRoidRig_v01'
C=Matrix(((0,0,1,0),(-1,0,0,0),(0,1,0,0),(0,0,0,1)))

def save():
    old=bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version=0
        bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'whale_maid_target_fit_v01.blend'),relative_remap=False,compress=True)
    finally:bpy.context.preferences.filepaths.save_version=old

def material(name,color):
    m=bpy.data.materials.new(name);m.diffuse_color=color;m.use_nodes=True
    shader=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    shader.inputs['Base Color'].default_value=color;shader.inputs['Roughness'].default_value=.7
    return m

def init_target():
    data=json.loads(BODY.read_text(encoding='utf-8'))
    OUT.mkdir(exist_ok=True)
    path=OUT/'whale_maid_target_fit_v01.blend'
    if path.exists() or RIG in bpy.data.objects:raise RuntimeError('Target fitting output exists; inspect before another write')
    if bpy.data.filepath!=str(ROOT/'projects/whale-maid/tripo-source/cloth-springs-v01/tripo_cloth_springs_v01.blend'):
        raise RuntimeError('Expected the preserved spring source file')
    bpy.data.objects['WM_ClothSpringRig_v01'].data.vrm_addon_extension.spring_bone1.enable_animation=False
    bpy.context.scene.frame_set(1)
    for p in bpy.data.objects['WM_ClothSpringRig_v01'].pose.bones:p.rotation_quaternion=(1,0,0,0)
    # First save to a new filepath; never write back to the source blend.
    save();scene=bpy.context.scene;scene.name='WhaleMaid_TargetVRoid_Fitting_v01'
    sourcecol=bpy.data.collections.new('SOURCE_原始Tripo与弹簧草案_保留');
    children=list(scene.collection.children);objects=list(scene.collection.objects)
    scene.collection.children.link(sourcecol)
    for col in children:sourcecol.children.link(col);scene.collection.children.unlink(col)
    for o in objects:sourcecol.objects.link(o);scene.collection.objects.unlink(o)
    sourcecol.hide_viewport=True;sourcecol.hide_render=True
    bodycol=bpy.data.collections.new('TARGET_真实VRoid身体_灰模参考');scene.collection.children.link(bodycol)
    rigcol=bpy.data.collections.new('TARGET_真实VRoid骨架');scene.collection.children.link(rigcol)
    arm=bpy.data.armatures.new(RIG);rig=bpy.data.objects.new(RIG,arm);rigcol.objects.link(rig)
    rig['body_reference_sha256']=hashlib.sha256(BODY.read_bytes()).hexdigest()
    rig['source_vroid_sha256']='9259a34f60c9ba1fe6b35eba5e8596ef44018eae8bbd607f8db22d74a832ddae'
    rig['native_height_cm']=data['height_cm'];rig['role']='Captured current VRoid edit pose, not an invented generic skeleton'
    arm.display_type='STICK';rig.show_in_front=True
    nodes={n['id']:n for n in data['nodes']};names={};used=set()
    influences={i for mesh in data['meshes'] for i in mesh['bone_nodes']}
    for ident,n in nodes.items():
        name=n['name']
        if name in used:name+=f'__node_{ident}'
        used.add(name);names[ident]=name
    for o in bpy.context.selected_objects:o.select_set(False)
    rig.select_set(True);bpy.context.view_layer.objects.active=rig
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        for ident,n in nodes.items():
            original=Matrix(n['world_matrix']);converted=C@original@C.inverted()
            q=converted.to_quaternion().normalized();matrix=q.to_matrix().to_4x4();matrix.translation=converted.translation
            b=arm.edit_bones.new(names[ident]);b.matrix=matrix
            lengths=[(C@Vector(nodes[i]['world_matrix'][r][3] for r in range(3))-matrix.translation).length for i in nodes if nodes[i]['parent']==ident]
            lengths=[d for d in lengths if .003<d<.5]
            b.length=min(lengths) if lengths else .015;b.use_deform=ident in influences
        for ident,n in nodes.items():
            if n['parent'] is not None:arm.edit_bones[names[ident]].parent=arm.edit_bones[names[n['parent']]]
    finally:bpy.ops.object.mode_set(mode='OBJECT')
    clay=material('VRoid reference clay - NOT source texture',(.48,.62,.67,1))
    for source in data['meshes']:
        transform=C@Matrix(source['world_matrix'])
        vertices=[transform@Vector(p) for p in source['positions']]
        indices=source['triangles'];faces=[(indices[i],indices[i+2],indices[i+1]) for i in range(0,len(indices),3)]
        mesh=bpy.data.meshes.new('REF_'+source['name']);mesh.from_pydata(vertices,[],faces);mesh.update()
        ob=bpy.data.objects.new('REF_VRoid_'+source['name'],mesh);bodycol.objects.link(ob)
        ob['native_renderer']=source['name'];ob['reference_only']=True;ob.parent=rig
        mesh.materials.append(clay)
        if source['uv0']:
            uv=mesh.uv_layers.new(name='NativeUV0')
            for loop in mesh.loops:uv.data[loop.index].uv=source['uv0'][loop.vertex_index]
        groups={i:ob.vertex_groups.new(name=names[n]) for i,n in enumerate(source['bone_nodes'])}
        for i,w in enumerate(source['weights']):
            for index,weight in zip(w['indices'],w['weights']):
                if weight>1e-7:groups[index].add([i],weight,'ADD')
        mod=ob.modifiers.new('NativeBodySkin','ARMATURE');mod.object=rig
        for poly in mesh.polygons:poly.use_smooth=True
    ext=arm.vrm_addon_extension;ext.spec_version='1.0'
    mapping={'hips':'J_Bip_C_Hips','spine':'J_Bip_C_Spine','chest':'J_Bip_C_Chest','upper_chest':'J_Bip_C_UpperChest','neck':'J_Bip_C_Neck','head':'J_Bip_C_Head'}
    for side,letter in [('left','L'),('right','R')]:
        for slot,native in [('shoulder','Shoulder'),('upper_arm','UpperArm'),('lower_arm','LowerArm'),('hand','Hand'),('upper_leg','UpperLeg'),('lower_leg','LowerLeg'),('foot','Foot'),('toes','ToeBase')]:mapping[side+'_'+slot]=f'J_Bip_{letter}_{native}'
    for slot,bone in mapping.items():
        if bone in arm.bones and hasattr(ext.vrm1.humanoid.human_bones,slot):getattr(ext.vrm1.humanoid.human_bones,slot).node.bone_name=bone
    rig['reference_node_names_json']=json.dumps(names)
    save();print(json.dumps({'file':str(path),'target_bones':len(arm.bones),'body_meshes':len(data['meshes']),'height_cm':data['height_cm']}))

def torso_map(p):
    # Match garment waist/chest/neck, rather than scaling by the very different heads.
    anchors=[(.64,.99),(.70,1.08),(.76,1.20),(.80,1.285),(.83,1.326),(.86,1.37)]
    if p.z<=.64:z=.99+(p.z-.64)*1.55
    else:
        z=anchors[-1][1]+(p.z-anchors[-1][0])*1.55
        for (a,b),(c,d) in zip(anchors,anchors[1:]):
            if a<=p.z<=c:z=b+(p.z-a)/(c-a)*(d-b);break
    return Vector((p.x*1.55+.015,p.y*1.55,z))

def arm_map(p,rig):
    positive=p.y>=0;sign=1 if positive else -1;side='L' if positive else 'R'
    # Centres measured from original puff/sleeve cross-sections, not bbox corners.
    src=[Vector((.010,sign*.063,.790)),Vector((.008,sign*.137,.660)),Vector((.014,sign*.198,.570))]
    dst=[rig.data.bones[f'J_Bip_{side}_{n}'].head_local.copy() for n in ['UpperArm','LowerArm','Hand']]
    possibilities=[]
    for i in range(2):
        direction=src[i+1]-src[i];t=max(0,min(1,(p-src[i]).dot(direction)/direction.length_squared))
        possibilities.append(((p-(src[i]+direction*t)).length,i,t))
    _,i,t=min(possibilities)
    direction=src[i+1]-src[i];target=dst[i+1]-dst[i]
    rot=direction.rotation_difference(target)
    return dst[i]+target*t+rot@(p-(src[i]+direction*t))*1.55

def reference_surface():
    verts=[];faces=[];weights=[]
    for name in ['Body','Hand']:
        ob=bpy.data.objects['REF_VRoid_'+name];start=len(verts)
        for v in ob.data.vertices:
            verts.append(v.co.copy());weights.append({ob.vertex_groups[g.group].name:g.weight for g in v.groups})
        faces.extend(tuple(start+i for i in f.vertices) for f in ob.data.polygons)
    bvh=BVHTree.FromPolygons(verts,faces,all_triangles=True)
    return bvh,verts,faces,weights

def nearest_weights(point,bvh,verts,faces,skin):
    loc,normal,index,distance=bvh.find_nearest(point)
    if index is None:raise RuntimeError('No target skin surface')
    ids=faces[index];a,b,c=(verts[i] for i in ids)
    # Barycentric interpolation with clamping against tiny floating-point excursions.
    u=b-a;v=c-a;w=loc-a
    d00=u.dot(u);d01=u.dot(v);d11=v.dot(v);d20=w.dot(u);d21=w.dot(v);den=d00*d11-d01*d01
    if abs(den)<1e-14:fractions=[1,0,0]
    else:
        q=(d11*d20-d01*d21)/den;r=(d00*d21-d01*d20)/den;fractions=[max(0,1-q-r),max(0,q),max(0,r)]
    result=defaultdict(float)
    for ident,f in zip(ids,fractions):
        for name,weight in skin[ident].items():result[name]+=f*weight
    result=dict(sorted(result.items(),key=lambda item:item[1],reverse=True)[:4]);total=sum(result.values())
    return {k:v/total for k,v in result.items() if v>1e-7}

def source_colors(ob):
    import numpy as np
    image=next(n.image for m in ob.data.materials for n in m.node_tree.nodes if n.type=='TEX_IMAGE' and n.image)
    pixels=np.empty(len(image.pixels),dtype=np.float32);image.pixels.foreach_get(pixels);pixels=pixels.reshape(image.size[1],image.size[0],4)
    colors=[];uv=ob.data.uv_layers.active
    for face in ob.data.polygons:
        samples=[]
        for i in face.loop_indices:
            u,v=uv.data[i].uv;x=max(0,min(image.size[0]-1,int(u*image.size[0])));y=max(0,min(image.size[1]-1,int(v*image.size[1])));samples.append(pixels[y,x,:3])
        colors.append(np.mean(samples,axis=0))
    return colors

def fit_clothes():
    rig=bpy.data.objects[RIG]
    if 'FITTED_服装工作副本' in bpy.data.collections:raise RuntimeError('Fitted clothing already exists; inspect first')
    col=bpy.data.collections.new('FITTED_服装工作副本');bpy.context.scene.collection.children.link(col)
    sources=[o for o in bpy.context.scene.objects if o.type=='MESH' and 'source_part_id' in o]
    bvh,verts,faces,skin=reference_surface();records=[]
    mapping={'WM_Hips':'J_Bip_C_Hips','WM_Spine':'J_Bip_C_Spine','WM_Chest':'J_Bip_C_Chest'}
    for src in sources:
        ident=src['source_part_id'];group=src['semantic_group'][:2]
        if group not in {'01','02','03','04','05','06','11','12','13'} or ident in {4,5}:continue
        ob=src.copy();ob.data=src.data.copy();ob.name='FIT_T'+f'{ident:03d}'+'__'+src.name.split('__',1)[-1]
        ob.parent=rig;ob.matrix_parent_inverse=Matrix.Identity(4);ob.matrix_world=Matrix.Identity(4)
        ob.hide_render=False;ob.hide_viewport=False;col.objects.link(ob);ob.hide_set(False)
        ob['fit_source_id']=ident;ob['reference_only']=False
        for mod in list(ob.modifiers):ob.modifiers.remove(mod)
        attr=ob.data.attributes.new('source_vertex_index','INT','POINT')
        for i,x in enumerate(attr.data):x.value=i
        zattr=ob.data.attributes.new('source_world_z','FLOAT','POINT')
        for v,x in zip(src.data.vertices,zattr.data):x.value=(src.matrix_world@v.co).z
        remove=[]
        if ident in {1,7,8,11}:
            colors=source_colors(src)
            for f,color in zip(src.data.polygons,colors):
                p=sum((src.matrix_world@src.data.vertices[i].co for i in f.vertices),Vector())/len(f.vertices)
                r,g,b=map(float,color);warm=r>.48 and g>.28 and r>g+.025 and r>b+.012
                region=(ident==1 and p.z>.79) or (ident in {7,8} and p.z>.745) or (ident==11 and p.z<.61)
                if warm and region:remove.append(f.index)
            bm=bmesh.new();bm.from_mesh(ob.data);bm.faces.ensure_lookup_table()
            bmesh.ops.delete(bm,geom=[bm.faces[i] for i in remove],context='FACES');bm.to_mesh(ob.data);bm.free()
        source_indices=[x.value for x in ob.data.attributes['source_vertex_index'].data]
        old_weights=[]
        for v in ob.data.vertices:old_weights.append({ob.vertex_groups[g.group].name:g.weight for g in v.groups})
        for g in list(ob.vertex_groups):ob.vertex_groups.remove(g)
        groups={};adjustments=[]
        arm_piece=group in {'04','05','06'} or ident in {20,21}
        for v,source_index,prior in zip(ob.data.vertices,source_indices,old_weights):
            p=src.matrix_world@src.data.vertices[source_index].co
            fitted=arm_map(p,rig) if arm_piece else torso_map(p)
            initial=fitted.copy()
            # Push only near/inside skin points; keep distant ruffles and the intended silhouette.
            for _ in range(3):
                loc,normal,index,distance=bvh.find_nearest(fitted)
                signed=(fitted-loc).dot(normal)
                if signed>=.004 or distance>.09:break
                fitted=loc+normal*.004
            v.co=fitted;adjustments.append((fitted-initial).length)
            if prior and (group in {'02','03','12'} or ident==1 and p.z<.64):
                weights={mapping.get(k,k):w for k,w in prior.items()}
            else:weights=nearest_weights(fitted,bvh,verts,faces,skin)
            for name,weight in weights.items():
                if name not in groups:groups[name]=ob.vertex_groups.new(name=name)
                groups[name].add([v.index],weight,'REPLACE')
        mod=ob.modifiers.new('TargetVRoidSkin','ARMATURE');mod.object=rig
        ob['wear_ready']=False;ob['fitting_stage']='Body landmark fit + nearest-surface upper skin; pose tests pending'
        records.append({'source_id':ident,'object':ob.name,'removed_generated_skin_faces':len(remove),'vertices':len(ob.data.vertices),'triangles':len(ob.data.polygons),'max_skin_clearance_adjustment_m':max(adjustments,default=0)})
    (OUT/'fit_geometry_report.json').write_text(json.dumps({'body_reference':str(BODY),'body_height_cm':rig['native_height_cm'],'clothes':records,'shoes_and_generated_legs_excluded':True,'source_data_preserved':True,'scope':'Initial target-body fitting; deformation and collision acceptance pending'},ensure_ascii=False,indent=2),encoding='utf-8')
    save();print(json.dumps({'fitted_meshes':len(records),'removed_skin_faces':sum(r['removed_generated_skin_faces'] for r in records),'max_adjustment':max(r['max_skin_clearance_adjustment_m'] for r in records)},ensure_ascii=False))

def attach_target_springs():
    rig=bpy.data.objects[RIG];old=bpy.data.objects['WM_ClothSpringRig_v01']
    sb=rig.data.vrm_addon_extension.spring_bone1
    if sb.springs or 'WM_Skirt_00_00' in rig.data.bones:raise RuntimeError('Target springs already exist')
    anchors={'WM_Hips':'J_Bip_C_Hips','WM_Spine':'J_Bip_C_Spine','WM_Chest':'J_Bip_C_Chest'}
    for o in bpy.context.selected_objects:o.select_set(False)
    rig.select_set(True);bpy.context.view_layer.objects.active=rig
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        for b in old.data.bones:
            if not b.name.startswith(('WM_Skirt_','WM_BackRibbon_')):continue
            n=rig.data.edit_bones.new(b.name);n.head=torso_map(b.head_local);n.tail=torso_map(b.tail_local);n.use_deform=b.use_deform
            n.parent=rig.data.edit_bones[anchors.get(b.parent.name,b.parent.name)]
    finally:bpy.ops.object.mode_set(mode='OBJECT')
    col=bpy.data.collections.new('TARGET_随真实腿骨运动的碰撞体');bpy.context.scene.collection.children.link(col)
    specs=[('Pelvis','J_Bip_C_Hips',rig.data.bones['J_Bip_C_Hips'].head_local+Vector((0,0,-.015)),None,.080)]
    for side in ['L','R']:
        for label,start,end,radius in [('thigh','UpperLeg','LowerLeg',.064),('shin','LowerLeg','Foot',.047)]:
            bone=rig.data.bones[f'J_Bip_{side}_{start}'];endbone=rig.data.bones[f'J_Bip_{side}_{end}']
            specs.append((side+' '+label,bone.name,bone.head_local.copy(),endbone.head_local.copy(),radius))
    details=[]
    for name,bone_name,head,tail,radius in specs:
        c=sb.add_collider(bpy.context,rig);c.node.bone_name=bone_name
        c.shape_type=(c.SHAPE_TYPE_CAPSULE if tail is not None else c.SHAPE_TYPE_SPHERE).identifier;c.reset_bpy_object(bpy.context,rig)
        sh=c.shape.capsule if tail is not None else c.shape.sphere
        inverse=rig.data.bones[bone_name].matrix_local.inverted();sh.offset=inverse@head;sh.radius=radius
        if tail is not None:sh.tail=inverse@tail
        c.bpy_object.name='TARGET_COLLIDER_'+name
        for ob in [c.bpy_object,*c.bpy_object.children]:
            col.objects.link(ob)
            for other in list(ob.users_collection):
                if other!=col:other.objects.unlink(ob)
        details.append({'name':name,'bone':bone_name,'radius_m':radius,'shape':'capsule' if tail is not None else 'sphere'})
    cg=sb.add_collider_group();cg.vrm_name='Actual VRoid leg-bone anchored body colliders'
    for c in sb.colliders:cg.add_collider().collider_uuid=c.uuid
    for original in old.data.vrm_addon_extension.spring_bone1.springs:
        s=sb.add_spring();s.vrm_name=original.vrm_name
        s.add_collider_group().collider_group_uuid=cg.uuid
        for j in original.joints:
            n=s.add_joint();n.node.bone_name=j.node.bone_name;n.hit_radius=j.hit_radius*1.55
            n.stiffness=j.stiffness*1.55;n.drag_force=j.drag_force;n.gravity_power=j.gravity_power*1.55;n.gravity_dir=tuple(j.gravity_dir)
    sb.fixup();sb.enable_animation=False
    col.hide_render=True
    rig['clothing_springs_target_bound']=True;rig['collision_quality']='bone-anchored approximate capsules, not exact skin shapes'
    (OUT/'target_spring_binding.json').write_text(json.dumps({'target_rig':rig.name,'target_bones':len(rig.data.bones),'spring_chains':len(sb.springs),'spring_joint_nodes':sum(len(s.joints) for s in sb.springs),'colliders':details,'apron_independent':False,'cloth_fit_source':'whale_maid_03_test_base.vroid'},ensure_ascii=False,indent=2),encoding='utf-8')
    save();print(json.dumps({'target_bones':len(rig.data.bones),'springs':len(sb.springs),'colliders':len(sb.colliders)}))

def refine_sleeve_clearance():
    rig=bpy.data.objects[RIG];bvh,verts,faces,skin=reference_surface();results=[]
    for ob in bpy.data.collections['FITTED_服装工作副本'].objects:
        if ob['fit_source_id'] not in {7,8,11,22}:continue
        before=len(ob.data.polygons)
        bm=bmesh.new();bm.from_mesh(ob.data)
        long_edges=[e for e in bm.edges if e.calc_length()>.023]
        bmesh.ops.subdivide_edges(bm,edges=long_edges,cuts=2,use_grid_fill=True)
        bm.to_mesh(ob.data);bm.free()
        for g in list(ob.vertex_groups):ob.vertex_groups.remove(g)
        groups={}
        for v in ob.data.vertices:
            p=v.co.copy()
            for _ in range(3):
                loc,normal,index,distance=bvh.find_nearest(p);signed=(p-loc).dot(normal)
                if signed>=.007 or distance>.06:break
                p=loc+normal*.007
            v.co=p
            for name,weight in nearest_weights(p,bvh,verts,faces,skin).items():
                if name not in groups:groups[name]=ob.vertex_groups.new(name=name)
                groups[name].add([v.index],weight,'REPLACE')
        results.append({'object':ob.name,'faces_before':before,'faces_after':len(ob.data.polygons)})
    (OUT/'sleeve_clearance_refinement.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    save();print(json.dumps(results,ensure_ascii=False))

def refine_upper_surface():
    bvh,verts,faces,skin=reference_surface();results=[]
    for ob in bpy.data.collections['FITTED_服装工作副本'].objects:
        ident=ob['fit_source_id'];group=ob['semantic_group'][:2]
        if ident not in {1,7,8,11,22} and group not in {'04','11','13'}:continue
        bm=bmesh.new();bm.from_mesh(ob.data)
        edges=[e for e in bm.edges if e.calc_length()>.025 and min(v.co.z for v in e.verts)>1.0]
        bmesh.ops.subdivide_edges(bm,edges=edges,cuts=1,use_grid_fill=True)
        bm.to_mesh(ob.data);bm.free()
        selected={v.index for v in ob.data.vertices if ident!=1 or ob.data.attributes['source_world_z'].data[v.index].value>.64}
        for _ in range(10):
            for i in selected:
                v=ob.data.vertices[i];loc,n,idx,d=bvh.find_nearest(v.co);signed=(v.co-loc).dot(n)
                if d<.09 and signed<.008:v.co=loc+n*.008
            corrections=defaultdict(list)
            for f in ob.data.polygons:
                if not all(i in selected for i in f.vertices):continue
                p=sum((ob.data.vertices[i].co for i in f.vertices),Vector())/len(f.vertices)
                loc,n,idx,d=bvh.find_nearest(p);signed=(p-loc).dot(n)
                if d<.09 and signed<.004:
                    correction=loc+n*.008-p
                    if correction.length>.02:correction.normalize();correction*=.02
                    for i in f.vertices:corrections[i].append(correction)
            for i,values in corrections.items():ob.data.vertices[i].co+=sum(values,Vector())/len(values)*.7
        groups={g.name:g for g in ob.vertex_groups}
        for i in selected:
            for g in ob.vertex_groups:g.remove([i])
            for name,w in nearest_weights(ob.data.vertices[i].co,bvh,verts,faces,skin).items():
                if name not in groups:groups[name]=ob.vertex_groups.new(name=name)
                groups[name].add([i],w,'REPLACE')
        results.append({'source_id':ident,'surface_vertices_rebound':len(selected),'faces':len(ob.data.polygons)})
    (OUT/'upper_surface_refinement.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    save();print(json.dumps({'upper_refined_meshes':len(results)}))

def drive_front_skirt_from_thighs():
    rig=bpy.data.objects[RIG];sb=rig.data.vrm_addon_extension.spring_bone1
    if sb.enable_animation:raise RuntimeError('Stop physics before structural edit')
    for o in bpy.context.selected_objects:o.select_set(False)
    rig.select_set(True);bpy.context.view_layer.objects.active=rig
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        for i in [0,1,2,10,11]:
            bone=rig.data.edit_bones[f'WM_Skirt_{i:02d}_00'];matrix=bone.matrix.copy();length=bone.length
            bone.parent=rig.data.edit_bones['J_Bip_L_UpperLeg' if i in [0,1,2] else 'J_Bip_R_UpperLeg']
            bone.matrix=matrix;bone.length=length
    finally:bpy.ops.object.mode_set(mode='OBJECT')
    for c in sb.colliders:
        if c.node.bone_name.endswith('UpperLeg'):c.shape.capsule.radius=.075
    rig['front_skirt_root_strategy']='Front sectors inherit actual thigh movement; centre-front follows left thigh in this iteration'
    save();print('Front skirt roots now inherit target thigh motion; no runtime constraints required')

def repair_neck_and_skirt_anchors():
    rig=bpy.data.objects[RIG];sb=rig.data.vrm_addon_extension.spring_bone1;sb.enable_animation=False
    col=bpy.data.collections['FITTED_服装工作副本'];main=next(o for o in col.objects if o['fit_source_id']==1)
    bm=bmesh.new();bm.from_mesh(main.data);zlayer=bm.verts.layers.float.get('source_world_z')
    remove=[f for f in bm.faces if sum(v[zlayer] for v in f.verts)/len(f.verts)>.807]
    count=len(remove);bmesh.ops.delete(bm,geom=remove,context='FACES');bm.to_mesh(main.data);bm.free()
    # Unknown back-collar scraps were marked needs_review at source inspection.
    # Preserve them in a visible-in-outliner quarantine, rather than project them into spikes.
    quarantine=bpy.data.collections.get('REVIEW_领后不明碎片_暂隔离')
    if not quarantine:quarantine=bpy.data.collections.new('REVIEW_领后不明碎片_暂隔离');bpy.context.scene.collection.children.link(quarantine)
    quarantined=[]
    for ob in list(col.objects):
        if ob['fit_source_id'] in {76,134,135}:
            quarantine.objects.link(ob);col.objects.unlink(ob);quarantined.append(ob.name)
    quarantine.hide_viewport=True;quarantine.hide_render=True
    for o in bpy.context.selected_objects:o.select_set(False)
    rig.select_set(True);bpy.context.view_layer.objects.active=rig;bpy.ops.object.mode_set(mode='EDIT')
    try:
        for i in [0,1,2,10,11]:
            b=rig.data.edit_bones[f'WM_Skirt_{i:02d}_00'];b.head=b.parent.head.copy()
    finally:bpy.ops.object.mode_set(mode='OBJECT')
    changed=0
    for ob in col.objects:
        if ob['semantic_group'][:2] not in {'01','02','03'}:continue
        groups={g.name:g for g in ob.vertex_groups}
        for v in ob.data.vertices:
            z=ob.data.attributes['source_world_z'].data[v.index].value
            if z>.64:continue
            u=(math.atan2(v.co.y,(v.co.x-.015))%(2*math.pi))/(2*math.pi)*12;i=int(u);blend=u-i
            if z>=.57:weights={'J_Bip_C_Hips':1.0}
            else:
                if z>.50:parts=[('J_Bip_C_Hips',(z-.50)/.07),(0,(.57-z)/.07)]
                else:
                    t=min(3,(.50-z)/.09);j=int(t);f=t-j;parts=[(j,1-f),(min(j+1,3),f)]
                weights=defaultdict(float)
                for ring,rw in [(i%12,1-blend),((i+1)%12,blend)]:
                    for segment,w in parts:weights[segment if isinstance(segment,str) else f'WM_Skirt_{ring:02d}_{segment:02d}']+=rw*w
            for g in ob.vertex_groups:g.remove([v.index])
            for name,w in weights.items():
                if w<=1e-7:continue
                if name not in groups:groups[name]=ob.vertex_groups.new(name=name)
                groups[name].add([v.index],w,'REPLACE')
            changed+=1
    (OUT/'neck_and_anchor_repair.json').write_text(json.dumps({'removed_generated_neck_faces':count,'quarantined_uncertain_fragments':quarantined,'skirt_vertices_reweighted':changed,'strategy':'Upper apron/waist anchored to hips; release below actual hip level; front spring root pivots at native thigh heads'},ensure_ascii=False,indent=2),encoding='utf-8')
    save();print(json.dumps({'removed_neck_faces':count,'quarantined':len(quarantined),'reweighted_vertices':changed}))

def refine_lower_back_clearance():
    rig=bpy.data.objects[RIG];ob=next(o for o in bpy.data.collections['FITTED_服装工作副本'].objects if o['fit_source_id']==1)
    bvh,*_=reference_surface()
    bm=bmesh.new();bm.from_mesh(ob.data)
    edges=[e for e in bm.edges if e.calc_length()>.025 and all(.78<v.co.z<1.015 and v.co.x<.04 for v in e.verts)]
    bmesh.ops.subdivide_edges(bm,edges=edges,cuts=2,use_grid_fill=True);bm.to_mesh(ob.data);bm.free()
    selected={v.index for v in ob.data.vertices if .78<v.co.z<1.015 and v.co.x<.04}
    for _ in range(8):
        for i in selected:
            v=ob.data.vertices[i];loc,n,idx,d=bvh.find_nearest(v.co)
            if d<.08 and (v.co-loc).dot(n)<.008:v.co=loc+n*.008
        corrections=defaultdict(list)
        for face in ob.data.polygons:
            if not all(i in selected for i in face.vertices):continue
            p=sum((ob.data.vertices[i].co for i in face.vertices),Vector())/len(face.vertices);loc,n,idx,d=bvh.find_nearest(p)
            if d<.08 and (p-loc).dot(n)<.003:
                for i in face.vertices:corrections[i].append(loc+n*.008-p)
        for i,values in corrections.items():ob.data.vertices[i].co+=sum(values,Vector())/len(values)*.6
    hip=ob.vertex_groups.get('J_Bip_C_Hips') or ob.vertex_groups.new(name='J_Bip_C_Hips')
    for i in selected:
        if ob.data.attributes['source_world_z'].data[i].value>=.57:
            for g in ob.vertex_groups:g.remove([i])
            hip.add([i],1,'REPLACE')
        else:
            weights=sorted([(g.group,g.weight) for g in ob.data.vertices[i].groups],key=lambda t:t[1],reverse=True)[:4];total=sum(w for _,w in weights)
            for g in ob.vertex_groups:g.remove([i])
            for index,w in weights:ob.vertex_groups[index].add([i],w/total,'REPLACE')
    for o in bpy.context.selected_objects:o.select_set(False)
    rig.select_set(True);bpy.context.view_layer.objects.active=rig;bpy.ops.object.mode_set(mode='EDIT')
    try:
        bone=rig.data.edit_bones['WM_Skirt_00_00'];bone.parent=rig.data.edit_bones['J_Bip_C_Hips'];bone.head=(.10,0,.91)
    finally:bpy.ops.object.mode_set(mode='OBJECT')
    rig['front_skirt_root_strategy']='Centre-front anchored to hips; adjacent front sectors inherit matching thigh; upper apron fixed above hip level'
    save();print(json.dumps({'lower_back_vertices_adjusted':len(selected),'front_centre_parent':'J_Bip_C_Hips'}))

def restore_upper_strap_surface():
    """Wrap upper straps along the body's front/back surfaces without normal snapping to neck."""
    ob=next(o for o in bpy.data.collections['FITTED_服装工作副本'].objects if o['fit_source_id']==1)
    source=next(o for o in bpy.data.objects if o.name.startswith('WM_T') and o.get('source_part_id')==1)
    suv=source.data.uv_layers.active;uvverts=[];positions=[];uvfaces=[]
    for face in source.data.polygons:
        start=len(uvverts)
        for loop_index in face.loop_indices:
            loop=source.data.loops[loop_index];uv=suv.data[loop_index].uv
            uvverts.append(Vector((uv.x,uv.y,0)));positions.append(source.matrix_world@source.data.vertices[loop.vertex_index].co)
        uvfaces.append(tuple(range(start,len(uvverts))))
    uvbvh=BVHTree.FromPolygons(uvverts,uvfaces,all_triangles=True)
    first_uv={}
    for loop in ob.data.loops:first_uv.setdefault(loop.vertex_index,ob.data.uv_layers.active.data[loop.index].uv.copy())
    bvh,verts,faces,skin=reference_surface();selected=[];ambiguous=0
    for vertex in ob.data.vertices:
        z=ob.data.attributes['source_world_z'].data[vertex.index].value
        if z<.74:continue
        uv=first_uv.get(vertex.index)
        if uv is None:continue
        point=Vector((uv.x,uv.y,0));loc,normal,index,distance=uvbvh.find_nearest(point)
        ids=uvfaces[index];a,b,c=(uvverts[i] for i in ids);u=b-a;v=c-a;w=loc-a
        den=u.dot(u)*v.dot(v)-u.dot(v)**2
        if abs(den)<1e-16:ambiguous+=1;continue
        q=(v.dot(v)*w.dot(u)-u.dot(v)*w.dot(v))/den;r=(u.dot(u)*w.dot(v)-u.dot(v)*w.dot(u))/den
        original=positions[ids[0]]*(1-q-r)+positions[ids[1]]*q+positions[ids[2]]*r
        if abs(original.z-z)>.004:ambiguous+=1;continue
        p=torso_map(original);front=original.x>=0
        origin=Vector((1 if front else -1,p.y,p.z));direction=Vector((-1 if front else 1,0,0))
        hit,n,idx,d=bvh.ray_cast(origin,direction,2)
        if hit is not None:p.x=max(p.x,hit.x+.008) if front else min(p.x,hit.x-.008)
        vertex.co=p;selected.append(vertex.index)
    groups={g.name:g for g in ob.vertex_groups}
    for i in selected:
        for g in ob.vertex_groups:g.remove([i])
        for name,w in nearest_weights(ob.data.vertices[i].co,bvh,verts,faces,skin).items():
            if name not in groups:groups[name]=ob.vertex_groups.new(name=name)
            groups[name].add([i],w,'REPLACE')
    ob.data.update()
    (OUT/'upper_strap_surface_repair.json').write_text(json.dumps({'vertices_restored_and_directionally_fitted':len(selected),'UV_source_position_ambiguities_skipped':ambiguous,'method':'Recover source triangle positions via retained UV, restore height/width, wrap front/back along X; target body unchanged'},indent=2),encoding='utf-8')
    save();print(json.dumps({'strap_vertices':len(selected),'ambiguous':ambiguous}))

if __name__=='__main__':init_target()
