"""Blender MCP callable clothing spring prototype for the reviewed whale-maid sample.

build() creates a separate file; inspect_status() reports actual objects/configuration;
review() runs the installed VRM solver, measures deformation, and stores reproducible poses.
No mesh cutting, new textures, inferred avatar licensing or VRM/XWear export.
"""
import bpy
import json
import math
import importlib
from pathlib import Path
from collections import defaultdict
from mathutils import Vector, Matrix

SOURCE = Path(r'D:\vroidmcp\projects\whale-maid\tripo-source')
OUT = SOURCE/'cloth-springs-v01'
RIG = 'WM_ClothSpringRig_v01'
ADDON = 'bl_ext.blender_org.vrm'
SKIRT_GROUPS = {'01','02','03'}

def helpers():
    ns={'__name__':'organization_helpers'}
    exec(compile((SOURCE/'organize_parts.py').read_text(encoding='utf-8'),'organize_parts.py','exec'),ns)
    return ns

def save(path, copy=False):
    old=bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version=0
        result=bpy.ops.wm.save_as_mainfile(filepath=str(path),copy=copy,relative_remap=False,compress=True)
        if 'FINISHED' not in result:raise RuntimeError(f'Save failed: {result}')
    finally:bpy.context.preferences.filepaths.save_version=old

def add_bone(rig,name,head,tail,parent=None,deform=True):
    b=rig.data.edit_bones.new(name);b.head=head;b.tail=tail
    if parent:b.parent=rig.data.edit_bones[parent]
    b.use_deform=deform
    return b

def ring_weights(p):
    # Neighbouring radial chains blend continuously. Four influences maximum.
    theta=math.atan2(p.y,p.x)%(2*math.pi)
    u=theta/(2*math.pi)*12;i=int(u);mix=u-i
    radials=[(i%12,1-mix),((i+1)%12,mix)]
    q=(.64-p.z)/.09
    if q<=0:return {'WM_Hips':1.0}
    if q<1:longitudinal=[('WM_Hips',1-q),(0,q)]
    else:
        t=min(q-1,3);j=int(t);f=t-j
        longitudinal=[(j,1-f),(min(j+1,3),f)]
    result=defaultdict(float)
    for ring,rw in radials:
        for segment,vw in longitudinal:
            name=segment if isinstance(segment,str) else f'WM_Skirt_{ring:02d}_{segment:02d}'
            result[name]+=rw*vw
    return {k:v for k,v in result.items() if v>1e-7}

def ribbon_weights(p):
    q=(.62-p.z)/.05
    if q<=0:return {'WM_Hips':1.0}
    # A shared continuous side blend keeps bow-centre fragments coherent.
    positive=max(0,min(1,(p.y+.015)/.03))
    sides=[('N',1-positive),('P',positive)]
    if q<1:segments=[('WM_Hips',1-q),(0,q)]
    else:
        t=min(q-1,2);j=int(t);f=t-j
        segments=[(j,1-f),(min(j+1,2),f)]
    result=defaultdict(float)
    for side,sw in sides:
        for segment,vw in segments:
            name=segment if isinstance(segment,str) else f'WM_BackRibbon_{side}_{segment:02d}'
            result[name]+=sw*vw
    return {k:v for k,v in result.items() if v>1e-7}

def upper_weights(p):
    if p.z<.70:
        f=max(0,min(1,(p.z-.64)/.06));return {'WM_Hips':1-f,'WM_Spine':f}
    f=max(0,min(1,(p.z-.70)/.06));return {'WM_Spine':1-f,'WM_Chest':f}

def build():
    manifest=json.loads((SOURCE/'parts_manifest_v01.json').read_text(encoding='utf-8'))
    mesh_digest=helpers()['mesh_digest']
    objects={o.get('source_part_id'):o for o in bpy.context.scene.objects if o.type=='MESH'}
    if set(objects)!=set(r['source_id'] for r in manifest['parts']):raise RuntimeError('Source identity mismatch')
    for row in manifest['parts']:
        o=objects[row['source_id']]
        if mesh_digest(o)!=row['source_digest'] or o.modifiers or o.vertex_groups:raise RuntimeError(f"Changed or already rigged source: {o.name}")
    if not hasattr(bpy.types.Armature,'vrm_addon_extension'):raise RuntimeError('VRM addon is not enabled')
    OUT.mkdir(exist_ok=True)
    path=OUT/'tripo_cloth_springs_v01.blend'
    if path.exists() or RIG in bpy.data.objects:raise RuntimeError('Output or rig exists; inspect actual status before another write')
    # Change the working filepath before edits; the organized source stays intact on disk.
    save(path)
    scene=bpy.context.scene;scene.name='WhaleMaid_ClothSprings_v01'
    rigcol=bpy.data.collections.new('15_服装弹簧骨_预览骨架');scene.collection.children.link(rigcol)
    collidercol=bpy.data.collections.new('16_物理碰撞_比例代理');scene.collection.children.link(collidercol)
    data=bpy.data.armatures.new(RIG);rig=bpy.data.objects.new(RIG,data);rigcol.objects.link(rig)
    data.display_type='STICK';rig.show_in_front=True
    rig['role']='Clothing physics prototype; anchors must be remapped to target VRoid skeleton'
    rig['front_axis']='+X';rig['normalized_source_height']=1.0
    rig['target_body_fitted']=False;rig['whole_character_rig']=False
    for o in bpy.context.selected_objects:o.select_set(False)
    rig.select_set(True);bpy.context.view_layer.objects.active=rig
    bpy.ops.object.mode_set(mode='EDIT')
    chains=[]
    try:
        add_bone(rig,'WM_Hips',(0,0,.64),(0,0,.70))
        add_bone(rig,'WM_Spine',(0,0,.70),(0,0,.76),'WM_Hips')
        add_bone(rig,'WM_Chest',(0,0,.76),(0,0,.81),'WM_Spine')
        for i in range(12):
            a=2*math.pi*i/12
            points=[]
            for j in range(5):
                t=j/4
                points.append(Vector(((.055+.105*t)*math.cos(a),(.069+.141*t)*math.sin(a),.64-.36*t)))
            names=[]
            for j in range(5):
                name=f'WM_Skirt_{i:02d}_{j:02d}'
                add_bone(rig,name,points[j],points[j+1] if j<4 else points[j]+Vector((0,0,-.008)),names[-1] if names else 'WM_Hips',j<4)
                names.append(name)
            chains.append({'name':f'Skirt_{i:02d}','bones':names,'kind':'skirt','stiffness':2.4,'drag_force':.72,'gravity_power':.018,'hit_radius':.004})
        for side,sign in [('N',-1),('P',1)]:
            points=[Vector((-.045-.06*j/3,sign*(.04+.025*j/3),.62-.15*j/3)) for j in range(4)]
            names=[]
            for j in range(4):
                name=f'WM_BackRibbon_{side}_{j:02d}'
                add_bone(rig,name,points[j],points[j+1] if j<3 else points[j]+Vector((0,0,-.008)),names[-1] if names else 'WM_Hips',j<3)
                names.append(name)
            chains.append({'name':f'BackRibbon_{side}','bones':names,'kind':'ribbon','stiffness':1.7,'drag_force':.65,'gravity_power':.025,'hit_radius':.003})
    finally:bpy.ops.object.mode_set(mode='OBJECT')
    for collection_name,prefixes in [('Anchors',('WM_Hips','WM_Spine','WM_Chest')),('Skirt springs',('WM_Skirt_',)),('Back ribbons',('WM_BackRibbon_',))]:
        bc=data.collections.new(collection_name)
        for b in data.bones:
            if any(b.name.startswith(p) for p in prefixes):bc.assign(b)
    root=bpy.data.objects['WM_Tripo_Organized_ROOT'];matrix=root.matrix_world.copy();root.parent=rig;root.matrix_world=matrix
    bound=[]
    for ident,o in objects.items():
        prefix=o['semantic_group'][:2]
        if prefix not in SKIRT_GROUPS|{'12'}:continue
        if o.data.users>1:o.data=o.data.copy()
        groups={name:o.vertex_groups.new(name=name) for name in data.bones.keys() if data.bones[name].use_deform}
        for v in o.data.vertices:
            p=o.matrix_world@v.co
            weights=ribbon_weights(p) if prefix=='12' else (ring_weights(p) if p.z<=.64 else upper_weights(p))
            weights={k:w for k,w in weights.items() if w>1e-7}
            total=sum(weights.values())
            if not total or len(weights)>4:raise RuntimeError('Invalid weights')
            for name,w in weights.items():groups[name].add([v.index],w/total,'REPLACE')
        for g in list(o.vertex_groups):
            if not any(any(x.group==g.index for x in v.groups) for v in o.data.vertices):o.vertex_groups.remove(g)
        mod=o.modifiers.new('WM_ClothSpringSkin','ARMATURE');mod.object=rig;mod.use_vertex_groups=True
        o['spring_binding']='coupled_skirt_apron' if ident==1 else ('back_ribbons' if prefix=='12' else 'skirt_detail')
        o['wear_ready']=False;bound.append(o.name)
    extension=data.vrm_addon_extension;extension.spec_version='1.0'
    for k,name in [('hips','WM_Hips'),('spine','WM_Spine'),('chest','WM_Chest')]:
        getattr(extension.vrm1.humanoid.human_bones,k).node.bone_name=name
    spring=extension.spring_bone1
    colliders=[]
    shapes=[('Pelvis proxy','sphere',Vector((0,0,.565)),None,.045),
            ('Leg Y negative proxy','capsule',Vector((.007,-.045,.51)),Vector((.007,-.045,.27)),.033),
            ('Leg Y positive proxy','capsule',Vector((.007,.045,.51)),Vector((.007,.045,.27)),.033)]
    inv=data.bones['WM_Hips'].matrix_local.inverted()
    for name,kind,head,tail,radius in shapes:
        c=spring.add_collider(bpy.context,rig);c.node.bone_name='WM_Hips'
        c.shape_type=(c.SHAPE_TYPE_SPHERE if kind=='sphere' else c.SHAPE_TYPE_CAPSULE).identifier
        c.reset_bpy_object(bpy.context,rig)
        shape=getattr(c.shape,kind);shape.offset=inv@head;shape.radius=radius
        if tail is not None:shape.tail=inv@tail
        c.bpy_object.name='WM_'+name
        for ob in [c.bpy_object,*c.bpy_object.children]:
            collidercol.objects.link(ob)
            for col in list(ob.users_collection):
                if col!=collidercol:col.objects.unlink(ob)
        colliders.append({'name':name,'type':kind,'node':'WM_Hips','offset':list(shape.offset),'tail':list(shape.tail) if tail is not None else None,'radius':shape.radius,'uuid':c.uuid})
    cg=spring.add_collider_group();cg.vrm_name='Body proportion proxies'
    for c in spring.colliders:cg.add_collider().collider_uuid=c.uuid
    for ch in chains:
        s=spring.add_spring();s.vrm_name=ch['name']
        s.add_collider_group().collider_group_uuid=cg.uuid
        # Center intentionally unset: translation inertia is visible in this preview.
        for name in ch['bones']:
            j=s.add_joint();j.node.bone_name=name;j.hit_radius=ch['hit_radius']
            j.stiffness=ch['stiffness'];j.drag_force=ch['drag_force'];j.gravity_power=ch['gravity_power'];j.gravity_dir=(0,0,-1)
    spring.fixup()
    # Drive only the armature object. Spring bones get NO authored motion keys.
    scene.render.fps=30;scene.frame_start=1;scene.frame_end=121
    rig.rotation_mode='XYZ'
    for f in range(1,122):
        t=(f-1)/30;amplitude=math.sin(math.pi*min(1,max(0,(t-.25)/2.75)))**2 if t<3 else 0
        rig.location=(.012*math.sin(2*math.pi*1.1*t)*amplitude,.026*math.sin(2*math.pi*.8*t)*amplitude,0)
        rig.rotation_euler=(0,.022*math.sin(2*math.pi*.8*t)*amplitude,.06*math.sin(2*math.pi*.55*t)*amplitude)
        rig.keyframe_insert('location',frame=f);rig.keyframe_insert('rotation_euler',frame=f)
    rig.animation_data.action.name='WM_Cloth_Inertia_Driver_NOT_BODY_ANIMATION'
    spring.enable_animation=False;scene.frame_set(1)
    for pb in rig.pose.bones:pb.rotation_mode='QUATERNION';pb.rotation_quaternion=(1,0,0,0)
    spring.enable_animation=True
    scene['physics_scope']='VRM1 cloth spring prototype on normalized Tripo source; target body fitting/export not accepted'
    collidercol.hide_render=True
    for o in bpy.context.selected_objects:o.select_set(False)
    rig.select_set(True);bpy.context.view_layer.objects.active=rig
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':area.spaces.active.overlay.show_extras=False
    save(path)
    plan={'schema_version':1,'file':str(path),'armature':RIG,'source':manifest['blend'],
          'source_height_units':1.0,'front_axis':'+X','anchors_are_provisional':True,
          'apron_independent_motion':False,'apron_motion':'coupled to front skirt to avoid tearing connected mesh',
          'chains':chains,'colliders':colliders,'bound_objects':bound,
          'limitations':['not a complete humanoid','not fitted to target VRoid body','hair and sleeves remain static','no topology repair','no XWear/VRM/Godot acceptance']}
    (OUT/'cloth_spring_plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(inspect_status(),ensure_ascii=False))
    return plan

def inspect_status():
    rig=bpy.data.objects.get(RIG)
    if not rig:return {'ok':False,'reason':'RIG_NOT_FOUND','file':bpy.data.filepath}
    spring=rig.data.vrm_addon_extension.spring_bone1
    bound=[o for o in bpy.context.scene.objects if o.type=='MESH' and any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers)]
    bad=[];max_influences=0
    for o in bound:
        for v in o.data.vertices:
            weights=[g.weight for g in v.groups if g.weight>1e-7]
            max_influences=max(max_influences,len(weights))
            if not weights or abs(sum(weights)-1)>1e-5 or len(weights)>4:bad.append([o.name,v.index])
    seen=set();chain_errors=[]
    for s in spring.springs:
        previous=None
        for j in s.joints:
            name=j.node.bone_name;b=rig.data.bones.get(name)
            if not b or name in seen:chain_errors.append(name)
            if previous and b.parent!=previous:chain_errors.append('parent:'+name)
            if b:seen.add(name);previous=b
    return {'ok':not bad and not chain_errors,'file':bpy.data.filepath,'armature':rig.name,
            'bones':len(rig.data.bones),'spring_chains':len(spring.springs),'spring_joint_nodes':sum(len(s.joints) for s in spring.springs),
            'colliders':len(spring.colliders),'bound_meshes':len(bound),'bound_vertices':sum(len(o.data.vertices) for o in bound),
            'max_influences':max_influences,'bad_weights':bad[:5],'chain_errors':chain_errors,
            'physics_enabled':spring.enable_animation,'target_vroid_body_fitted':False}

def reset_pose():
    rig=bpy.data.objects[RIG];spring=rig.data.vrm_addon_extension.spring_bone1
    spring.enable_animation=False
    bpy.context.scene.frame_set(1)
    for pb in rig.pose.bones:pb.rotation_quaternion=(1,0,0,0)
    bpy.context.view_layer.update()
    spring.enable_animation=True

def collider_clearance(rig,point,c,hit):
    mat=rig.matrix_world@rig.pose.bones[c.node.bone_name].matrix
    sphere=c.shape_type==c.SHAPE_TYPE_SPHERE.identifier
    shape=c.shape.sphere if sphere else c.shape.capsule
    a=mat@Vector(shape.offset)
    if not sphere:
        b=mat@Vector(shape.tail);ab=b-a
        a+=ab*max(0,min(1,(point-a).dot(ab)/max(ab.length_squared,1e-12)))
    return (point-a).length-shape.radius-hit

def contact_and_seam_review():
    """Check coincident source seams and exercise the real solver with a temporary contact."""
    rig=bpy.data.objects[RIG];spring=rig.data.vrm_addon_extension.spring_bone1
    handler=importlib.import_module(ADDON+'.editor.spring_bone1.handler')
    from mathutils.kdtree import KDTree
    poses=json.loads((OUT/'simulated_pose_cache.json').read_text())
    registration=[(i,h) for i,h in enumerate(bpy.app.handlers.frame_change_pre) if h.__module__==handler.__name__]
    for _,h in registration:bpy.app.handlers.frame_change_pre.remove(h)
    c=spring.colliders[0];saved_offset=tuple(c.shape.sphere.offset);saved_radius=c.shape.sphere.radius
    try:
        reset_pose();spring.enable_animation=False;bpy.context.scene.frame_set(60)
        for name,quat in poses['60'].items():rig.pose.bones[name].rotation_quaternion=quat
        bpy.context.view_layer.update()
        bound=[o for o in bpy.context.scene.objects if o.type=='MESH' and o.get('spring_binding')]
        rest=[];posed=[];owners=[];inv=rig.matrix_world.inverted()
        for o in bound:
            ev=o.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh()
            try:
                transform=inv@o.matrix_world
                for v in o.data.vertices:rest.append(transform@v.co);owners.append(o.name)
                for v in mesh.vertices:posed.append(transform@v.co)
            finally:ev.to_mesh_clear()
        kd=KDTree(len(rest))
        for i,p in enumerate(rest):kd.insert(p,i)
        kd.balance();pairs=[]
        for i,p in enumerate(rest):
            for _,j,dist in kd.find_range(p,1e-5):
                if j>i and owners[j]!=owners[i]:pairs.append((i,j))
        gap=max(((posed[i]-posed[j]).length for i,j in pairs),default=0)
        clearances=[collider_clearance(rig,rig.matrix_world@rig.pose.bones[j.node.bone_name].head,c,previous.hit_radius)
                    for s in spring.springs for previous,j in zip(s.joints,s.joints[1:]) for c in spring.colliders]
        # Deliberately move one existing sphere near a front-chain tail in a disposable test.
        # Restore both radius and offset even when an assertion fails.
        reset_pose();spring.enable_animation=False;bpy.context.scene.frame_set(1)
        target=rig.pose.bones['WM_Skirt_00_02'].head.copy()
        centre=target-Vector((.012,0,0))
        c.shape.sphere.offset=rig.data.bones['WM_Hips'].matrix_local.inverted()@centre
        c.shape.sphere.radius=.025
        bpy.context.view_layer.update()
        before=collider_clearance(rig,rig.matrix_world@target,c,.004)
        spring.enable_animation=True
        for _ in range(60):handler.update_pose_bone_rotations(bpy.context,1/60);bpy.context.view_layer.update()
        after=collider_clearance(rig,rig.matrix_world@rig.pose.bones['WM_Skirt_00_02'].head,c,.004)
        result={'success':gap<.001 and min(clearances)>-.001 and before<0 and after>-.001,
                'seam_matching_tolerance':1e-5,'matched_cross_object_vertex_pairs':len(pairs),
                'max_reviewed_seam_gap_units':gap,'frame_60_min_joint_proxy_clearance':min(clearances),
                'temporary_contact_test':{'before_signed_clearance':before,'after_signed_clearance':after,'steps':60},
                'scope':'Coincident source vertices only; does not prove all open borders sealed or all body poses collision-free'}
        (OUT/'contact_and_seam_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False));return result
    finally:
        c.shape.sphere.offset=saved_offset;c.shape.sphere.radius=saved_radius
        reset_pose()
        for i,h in registration:bpy.app.handlers.frame_change_pre.insert(min(i,len(bpy.app.handlers.frame_change_pre)),h)

def save_baked_preview():
    """Bake the recorded solver result for deterministic playback; primary physics file stays live."""
    rig=bpy.data.objects[RIG];spring=rig.data.vrm_addon_extension.spring_bone1
    path=OUT/'tripo_cloth_springs_playback.blend'
    if path.exists():raise RuntimeError('Playback file exists; inspect before overwrite')
    poses=json.loads((OUT/'simulated_pose_cache.json').read_text())
    original_action=rig.animation_data.action
    action=original_action.copy();action.name='WM_REVIEW_BAKED_VRM_SOLVER_OUTPUT'
    original_slot=rig.animation_data.action_slot
    rig.animation_data.action=action
    if original_slot:rig.animation_data.action_slot=action.slots[0]
    spring.enable_animation=False
    try:
        for frame,values in poses.items():
            for name,quat in values.items():
                pb=rig.pose.bones[name];pb.rotation_quaternion=quat;pb.keyframe_insert('rotation_quaternion',frame=int(frame))
        bpy.context.scene.frame_set(1)
        bpy.context.scene['review_baked_physics']=True
        save(path,copy=True)
        print('BAKED_PLAYBACK '+str(path))
    finally:
        rig.animation_data.action=original_action
        if original_slot:rig.animation_data.action_slot=original_slot
        bpy.context.scene['review_baked_physics']=False
        reset_pose()
        if action.users==0:bpy.data.actions.remove(action)
    save(OUT/'tripo_cloth_springs_v01.blend')

def review():
    """Real VRM addon solver; drive object only; record evaluated skin deformation."""
    rig=bpy.data.objects[RIG];scene=bpy.context.scene
    handler=importlib.import_module(ADDON+'.editor.spring_bone1.handler')
    spring=rig.data.vrm_addon_extension.spring_bone1
    registration=[(i,h) for i,h in enumerate(bpy.app.handlers.frame_change_pre) if h.__module__==handler.__name__]
    for _,h in registration:bpy.app.handlers.frame_change_pre.remove(h)
    samples=[];poses={};rest={}
    bound=[o for o in scene.objects if o.type=='MESH' and any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers)]
    import numpy as np
    def evaluated(o):
        ev=o.evaluated_get(bpy.context.evaluated_depsgraph_get());m=ev.to_mesh()
        try:
            arr=np.empty(len(m.vertices)*3,dtype=np.float64);m.vertices.foreach_get('co',arr)
            return arr.reshape((-1,3))
        finally:ev.to_mesh_clear()
    try:
        reset_pose()
        for o in bound:rest[o.name]=evaluated(o)
        for f in range(1,122):
            scene.frame_set(f);bpy.context.view_layer.update()
            for _ in range(2):handler.update_pose_bone_rotations(bpy.context,1/60);bpy.context.view_layer.update()
            poses[str(f)]={pb.name:list(pb.rotation_quaternion) for pb in rig.pose.bones if pb.name.startswith(('WM_Skirt_','WM_BackRibbon_'))}
            if f in {1,15,30,45,60,75,90,105,121}:
                maximum=0;upper=0;finite=True
                for o in bound:
                    p=evaluated(o);delta=np.linalg.norm(p-rest[o.name],axis=1)
                    maximum=max(maximum,float(delta.max(initial=0)))
                    z=np.array([(o.matrix_world@v.co).z for v in o.data.vertices])
                    # Object translation is absent in evaluated local mesh coordinates.
                    if o.get('source_part_id')==1:upper=max(upper,float(delta[z>.67].max(initial=0)))
                    finite=finite and bool(np.isfinite(p).all())
                samples.append({'frame':f,'max_skin_displacement_units':maximum,'upper_torso_max_displacement':upper,'finite_vertices':finite})
        result={'success':all(s['finite_vertices'] and s['upper_torso_max_displacement']<1e-5 and s['max_skin_displacement_units']<.15 for s in samples) and max(s['max_skin_displacement_units'] for s in samples)>.001,
                'solver':'installed VRM addon spring_bone1.handler.update_pose_bone_rotations','step_seconds':1/60,'frames':121,
                'samples':samples,'status':inspect_status(),'scope':'Cloth physics preview, not final fitting or runtime export acceptance'}
        (OUT/'physics_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        (OUT/'simulated_pose_cache.json').write_text(json.dumps(poses),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False))
        return result
    finally:
        reset_pose()
        for i,h in registration:bpy.app.handlers.frame_change_pre.insert(min(i,len(bpy.app.handlers.frame_change_pre)),h)

if __name__=='__main__':build()
