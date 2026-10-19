"""Actual target-body joint poses, VRM solver response and rendered fitting evidence."""
import bpy,json,math,importlib
from pathlib import Path
from mathutils import Matrix,Vector
from mathutils.bvhtree import BVHTree

ROOT=Path(r'D:\vroidmcp');OUT=ROOT/'projects/whale-maid/target-fit-v01';RIG='WM_TargetVRoidRig_v01'
CASES={'rest':{},'arms_forward':{'J_Bip_L_UpperArm':('Z',-.45),'J_Bip_R_UpperArm':('Z',.45)},
       'step':{'J_Bip_L_UpperLeg':('Y',-.4),'J_Bip_R_UpperLeg':('Y',.3),'J_Bip_L_LowerLeg':('Y',.2)},
       'seated_joint_pose':{'J_Bip_L_UpperLeg':('Y',-math.pi/2),'J_Bip_R_UpperLeg':('Y',-math.pi/2),'J_Bip_L_LowerLeg':('Y',math.pi/2),'J_Bip_R_LowerLeg':('Y',math.pi/2)}}

def reset_native(rig):
    for pb in rig.pose.bones:
        if not pb.name.startswith(('WM_Skirt_','WM_BackRibbon_')):pb.matrix_basis.identity()
    bpy.context.view_layer.update()

def apply_case(rig,case,fraction):
    reset_native(rig)
    for name,(axis,angle) in CASES[case].items():
        pb=rig.pose.bones[name];head=pb.head.copy()
        pb.matrix=Matrix.Translation(head)@Matrix.Rotation(angle*fraction,4,axis)@Matrix.Translation(-head)@pb.matrix
        bpy.context.view_layer.update()

def points_and_faces(ob):
    ev=ob.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh()
    try:return [ob.matrix_world@v.co for v in mesh.vertices],[tuple(f.vertices) for f in mesh.polygons]
    finally:ev.to_mesh_clear()

def render_pose(label,view):
    source=bpy.context.scene
    objects=[o for o in source.objects if o.type=='MESH' and (o.name.startswith('REF_VRoid_') or 'fit_source_id' in o)]
    scene=bpy.data.scenes.new('TARGET_FIT_REVIEW_TEMP');created=[]
    try:
        scene.render.engine='BLENDER_WORKBENCH';scene.display.shading.light='STUDIO';scene.display.shading.color_type='TEXTURE'
        scene.display.shading.show_shadows=False;scene.display.shading.background_type='WORLD'
        world=bpy.data.worlds.new('TARGET_FIT_REVIEW_WORLD');world.color=(.12,.12,.12);scene.world=world
        scene.render.resolution_x=720;scene.render.resolution_y=900;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG'
        data=bpy.data.cameras.new('TARGET_REVIEW_CAMERA');camera=bpy.data.objects.new('TARGET_REVIEW_CAMERA',data);scene.collection.objects.link(camera);created.append(camera)
        center=Vector((0,0,.84));direction={'front':Vector((1,0,0)),'side':Vector((0,-1,0)),'back':Vector((-1,0,0))}[view]
        camera.location=center+direction*4;camera.rotation_euler=(-direction).to_track_quat('-Z','Y').to_euler();data.type='ORTHO';data.ortho_scale=1.95;scene.camera=camera
        deps=bpy.context.evaluated_depsgraph_get()
        for ob in objects:
            mesh=bpy.data.meshes.new_from_object(ob.evaluated_get(deps),depsgraph=deps)
            copy=bpy.data.objects.new('ReviewCopy',mesh);scene.collection.objects.link(copy);copy.matrix_world=ob.matrix_world.copy();created.append(copy)
        folder=OUT/'pose-review';folder.mkdir(exist_ok=True)
        scene.render.filepath=str(folder/f'{label}_{view}.png');bpy.ops.render.render(write_still=True,scene=scene.name)
    finally:
        for ob in created:
            data=ob.data;typ=ob.type;bpy.data.objects.remove(ob,do_unlink=True)
            if typ=='MESH' and data.users==0:bpy.data.meshes.remove(data)
            if typ=='CAMERA' and data.users==0:bpy.data.cameras.remove(data)
        world=scene.world;bpy.data.scenes.remove(scene)
        if world.users==0:bpy.data.worlds.remove(world)

def measure(case):
    vertices=[];faces=[]
    for name in ['Body','Hand']:
        ob=bpy.data.objects['REF_VRoid_'+name];pts,polys=points_and_faces(ob);offset=len(vertices);vertices.extend(pts);faces.extend(tuple(i+offset for i in f) for f in polys)
    bvh=BVHTree.FromPolygons(vertices,faces,all_triangles=True)
    findings=[];finite=True;total=0;inside=0
    for ob in bpy.data.collections['FITTED_服装工作副本'].objects:
        points,polys=points_and_faces(ob)
        samples=points+[sum((points[i] for i in p),Vector())/len(p) for p in polys]
        penetrations=[]
        for p in samples:
            finite=finite and all(math.isfinite(x) for x in p)
            loc,normal,index,distance=bvh.find_nearest(p);signed=(p-loc).dot(normal)
            if distance<.12 and signed<-.003:penetrations.append(-signed)
        total+=len(samples);inside+=len(penetrations)
        if penetrations:findings.append({'object':ob.name,'sample_points':len(samples),'inside_samples':len(penetrations),'max_depth_m':max(penetrations)})
    return {'case':case,'finite':finite,'sample_points':total,'inside_samples':inside,'inside_fraction':inside/max(1,total),
            'worst_objects':sorted(findings,key=lambda f:f['inside_samples'],reverse=True)[:12],
            'screening_threshold_pass':finite and inside/max(1,total)<.005 and max((f['max_depth_m'] for f in findings),default=0)<.01,
            'method':'Nearest body surface normal, garment vertices and face centres; screening only, not exact watertight collision proof'}

def review(render=True):
    rig=bpy.data.objects[RIG];sb=rig.data.vrm_addon_extension.spring_bone1
    handler=importlib.import_module('bl_ext.blender_org.vrm.editor.spring_bone1.handler')
    registration=[(i,h) for i,h in enumerate(bpy.app.handlers.frame_change_pre) if h.__module__==handler.__name__]
    for _,h in registration:bpy.app.handlers.frame_change_pre.remove(h)
    results=[];cache={}
    try:
        for case in CASES:
            sb.enable_animation=False
            for pb in rig.pose.bones:pb.matrix_basis.identity()
            bpy.context.scene.frame_set(1);bpy.context.view_layer.update();sb.enable_animation=True
            for step in range(1,81):
                apply_case(rig,case,min(1,step/20))
                handler.update_pose_bone_rotations(bpy.context,1/60);bpy.context.view_layer.update()
            results.append(measure(case))
            cache[case]={p.name:[list(row) for row in p.matrix_basis] for p in rig.pose.bones}
            if render:
                render_pose(case,'front');render_pose(case,'side')
                if case=='rest':render_pose(case,'back')
        result={'all_numeric_pass':all(r['finite'] for r in results),'all_screening_thresholds_pass':all(r['screening_threshold_pass'] for r in results),'cases':results,'scope':'Actual captured skeleton poses and Blender VRM solver; screening is not visual quality or XWear/VRM/Godot runtime acceptance'}
        (OUT/'target_pose_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        (OUT/'target_pose_cache.json').write_text(json.dumps(cache),encoding='utf-8')
        print(json.dumps({'all_numeric_pass':result['all_numeric_pass'],'all_screening_thresholds_pass':result['all_screening_thresholds_pass'],'cases':[{'case':r['case'],'inside_samples':r['inside_samples'],'inside_fraction':r['inside_fraction'],'max_depth_m':max((f['max_depth_m'] for f in r['worst_objects']),default=0)} for r in results]},ensure_ascii=False));return result
    finally:
        sb.enable_animation=False
        for p in rig.pose.bones:p.matrix_basis.identity()
        bpy.context.scene.frame_set(1);bpy.context.view_layer.update()
        for i,h in registration:bpy.app.handlers.frame_change_pre.insert(min(i,len(bpy.app.handlers.frame_change_pre)),h)

def fit_problem_pose(case='step',iterations=5,source_id=1):
    """Rest-geometry fitting from a tested pose using inverse linear skin matrices.

    Adjusts garment source copies, not the body, without runtime-only constraints or
    hiding penetrations. Existing UVs and weights remain; final review covers all poses.
    """
    rig=bpy.data.objects[RIG];sb=rig.data.vrm_addon_extension.spring_bone1;sb.enable_animation=False
    cache=json.loads((OUT/'target_pose_cache.json').read_text(encoding='utf-8'))
    for name,rows in cache[case].items():rig.pose.bones[name].matrix_basis=Matrix(rows)
    bpy.context.view_layer.update()
    body=[];faces=[]
    for name in ['Body','Hand']:
        pts,polys=points_and_faces(bpy.data.objects['REF_VRoid_'+name]);offset=len(body);body.extend(pts);faces.extend(tuple(i+offset for i in p) for p in polys)
    bvh=BVHTree.FromPolygons(body,faces,all_triangles=True)
    ob=next(o for o in bpy.data.collections['FITTED_服装工作副本'].objects if o['fit_source_id']==source_id)
    inverses={};before=[v.co.copy() for v in ob.data.vertices]
    from collections import defaultdict
    try:
        for _ in range(iterations):
            points,polys=points_and_faces(ob);corrections=defaultdict(list)
            for i,p in enumerate(points):
                loc,n,idx,d=bvh.find_nearest(p)
                if d<.12 and (p-loc).dot(n)<.003:corrections[i].append(loc+n*.010-p)
            for poly in polys:
                p=sum((points[i] for i in poly),Vector())/len(poly);loc,n,idx,d=bvh.find_nearest(p)
                if d<.12 and (p-loc).dot(n)<.003:
                    for i in poly:corrections[i].append(loc+n*.010-p)
            for i,values in corrections.items():
                delta=sum(values,Vector())/len(values)*.75
                if delta.length>.020:delta.normalize();delta*=.020
                if i not in inverses:
                    matrix=Matrix(((0,0,0,0),)*4)
                    for g in ob.data.vertices[i].groups:
                        bone=rig.pose.bones[ob.vertex_groups[g.group].name]
                        matrix+=(bone.matrix@bone.bone.matrix_local.inverted())*g.weight
                    inverses[i]=matrix.to_3x3().inverted_safe()
                ob.data.vertices[i].co+=inverses[i]@delta
            ob.data.update();bpy.context.view_layer.update()
        displacements=[(v.co-p).length for v,p in zip(ob.data.vertices,before)]
        result={'pose':case,'source_part_id':source_id,'iterations':iterations,'adjusted_vertices':sum(d>1e-7 for d in displacements),'max_rest_geometry_change_m':max(displacements),'method':'Inverse linear skin matrices, garment-only rest fitting; unchanged body, weights and UVs'}
        suffix='' if source_id==1 else f'_part_{source_id}'
        (OUT/f'pose_aware_fit_{case}{suffix}.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result))
    finally:
        for p in rig.pose.bones:p.matrix_basis.identity()
        bpy.context.view_layer.update()
    helpers={'__name__':'fit_helpers'}
    exec(compile((ROOT/'tools/fit_cloth_to_vroid.py').read_text(encoding='utf-8'),'fit_cloth_to_vroid.py','exec'),helpers)
    helpers['save']()

def save_pose_preview(rebuild=False):
    rig=bpy.data.objects[RIG];sb=rig.data.vrm_addon_extension.spring_bone1
    preview=OUT/'whale_maid_target_pose_review.blend'
    if preview.exists() and not rebuild:raise RuntimeError('Pose review file exists; inspect before writing')
    if rig.animation_data and rig.animation_data.action:raise RuntimeError('Unexpected target rig action; preserve it before baking')
    cache=json.loads((OUT/'target_pose_cache.json').read_text(encoding='utf-8'));scene=bpy.context.scene;created=[];end=scene.frame_end
    sb.enable_animation=False;action=None
    try:
        for frame,case in zip([1,31,61,91],CASES):
            created.append(scene.timeline_markers.new(case,frame=frame))
            for name,rows in cache[case].items():
                pb=rig.pose.bones[name];pb.rotation_mode='QUATERNION';pb.matrix_basis=Matrix(rows)
                for path in ['location','rotation_quaternion','scale']:pb.keyframe_insert(path,frame=frame)
        action=rig.animation_data.action;action.name='TARGET_FOUR_SOLVED_POSES_REVIEW_ONLY'
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for curve in bag.fcurves:
                        for key in curve.keyframe_points:key.interpolation='CONSTANT'
        scene.frame_end=91;scene.frame_set(1);scene['preview_type']='Four static solved poses, not continuous walk/sit animation'
        old=bpy.context.preferences.filepaths.save_version
        try:
            bpy.context.preferences.filepaths.save_version=0
            bpy.ops.wm.save_as_mainfile(filepath=str(preview),copy=True,relative_remap=False,compress=True)
        finally:bpy.context.preferences.filepaths.save_version=old
        print('TARGET_POSE_PREVIEW '+str(preview))
    finally:
        rig.animation_data_clear()
        if action and action.users==0:bpy.data.actions.remove(action)
        for marker in created:scene.timeline_markers.remove(marker)
        scene.frame_end=end;scene.frame_set(1)
        for pb in rig.pose.bones:pb.matrix_basis.identity()
        sb.enable_animation=True;scene['preview_type']='Editable clothing physics and target-body fitting'
        bpy.context.view_layer.update()
        fit={'__name__':'fit_module'}
        exec(compile((ROOT/'tools/fit_cloth_to_vroid.py').read_text(encoding='utf-8'),'fit_cloth_to_vroid.py','exec'),fit)
        fit['save']()

if __name__=='__main__':review()
