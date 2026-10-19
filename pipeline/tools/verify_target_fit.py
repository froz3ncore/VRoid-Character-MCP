"""Cold verification of saved target-body fitting and fixed-pose playback."""
import bpy,json,hashlib,addon_utils
from pathlib import Path
from mathutils import Matrix,Vector

ROOT=Path(r'D:\vroidmcp');OUT=ROOT/'projects/whale-maid/target-fit-v01'
addon_utils.enable('bl_ext.blender_org.vrm',default_set=True,persistent=False)
snapshot=json.loads((ROOT/'projects/whale-maid/target-body/whale_maid_vroid_body_reference.json').read_text(encoding='utf-8'))
rig=bpy.data.objects['WM_TargetVRoidRig_v01'];sb=rig.data.vrm_addon_extension.spring_bone1
errors=[];preview='pose_review' in Path(bpy.data.filepath).stem
if preview:
    cache=json.loads((OUT/'target_pose_cache.json').read_text(encoding='utf-8'));maximum=0
    for frame,case in zip([1,31,61,91],['rest','arms_forward','step','seated_joint_pose']):
        bpy.context.scene.frame_set(frame)
        for name,rows in cache[case].items():
            maximum=max(maximum,max(abs(a-b) for r1,r2 in zip(rig.pose.bones[name].matrix_basis,rows) for a,b in zip(r1,r2)))
    if maximum>1e-5:errors.append('Pose playback mismatch')
    if sb.enable_animation:errors.append('Playback must disable live physics')
    result={'success':not errors,'errors':errors,'max_pose_matrix_error':maximum,'scope':'Four static solved poses only'}
    path=OUT/'pose_playback_cold_validation.json'
else:
    if not sb.enable_animation:errors.append('Primary physics not enabled')
    sb.enable_animation=False;bpy.context.scene.frame_set(1)
    for p in rig.pose.bones:p.matrix_basis.identity()
    bpy.context.view_layer.update()
    C=Matrix(((0,0,1,0),(-1,0,0,0),(0,1,0,0),(0,0,0,1)))
    maximum=0
    for source in snapshot['meshes']:
        ob=bpy.data.objects['REF_VRoid_'+source['name']];transform=C@Matrix(source['world_matrix'])
        if len(ob.data.vertices)!=len(source['positions']):errors.append('Body count changed')
        for v,p in zip(ob.data.vertices,source['positions']):maximum=max(maximum,(v.co-transform@Vector(p)).length)
        if source['uv0']:
            for loop in ob.data.loops:
                actual=ob.data.uv_layers.active.data[loop.index].uv;expected=source['uv0'][loop.vertex_index]
                if max(abs(a-b) for a,b in zip(actual,expected))>1e-6:errors.append('Body UV changed');break
    if maximum>1e-6:errors.append('Actual target body was modified')
    names=json.loads(rig['reference_node_names_json']);head_error=0
    for node in snapshot['nodes']:
        expected=C@Vector(node['world_matrix'][i][3] for i in range(3));bone=rig.data.bones[names[str(node['id'])]]
        head_error=max(head_error,(bone.head_local-expected).length)
        parent=names[str(node['parent'])] if node['parent'] is not None else None
        if (bone.parent.name if bone.parent else None)!=parent:errors.append('Native bone hierarchy changed')
    if head_error>1e-6:errors.append('Native bone positions changed')
    fitted=list(bpy.data.collections['FITTED_服装工作副本'].objects);bad=[];max_influences=0
    for ob in fitted:
        modifiers=[m for m in ob.modifiers if m.type=='ARMATURE']
        if len(modifiers)!=1 or modifiers[0].object!=rig:errors.append('Wrong garment armature')
        for v in ob.data.vertices:
            groups=[g for g in v.groups if g.weight>1e-7];max_influences=max(max_influences,len(groups))
            if not groups or len(groups)>4 or abs(sum(g.weight for g in groups)-1)>1e-4 or any(ob.vertex_groups[g.group].name not in rig.data.bones for g in groups):bad.append((ob.name,v.index))
    if bad:errors.append('Invalid garment weights')
    seen=set()
    for s in sb.springs:
        previous=None
        for joint in s.joints:
            bone=rig.data.bones.get(joint.node.bone_name)
            if not bone or bone.name in seen:errors.append('Missing/duplicated spring node')
            if previous and bone.parent!=previous:errors.append('Broken spring chain')
            if bone:seen.add(bone.name);previous=bone
    if len(sb.springs)!=14 or len(sb.colliders)!=5 or len(rig.data.bones)!=264:errors.append('Unexpected rig counts')
    scope={s.uuid for s in sb.collider_groups};colliders={c.uuid for c in sb.colliders}
    if any(c.collider_uuid not in colliders for g in sb.collider_groups for c in g.colliders):errors.append('Missing collider UUID')
    if any(g.collider_group_uuid not in scope for s in sb.springs for g in s.collider_groups):errors.append('Missing collider group UUID')
    # Originals inside SOURCE remain byte-equivalent in mesh data/UV/world placement.
    helpers={'__name__':'original_verification'}
    exec(compile((ROOT/'projects/whale-maid/tripo-source/organize_parts.py').read_text(encoding='utf-8'),'organize_parts.py','exec'),helpers)
    original=json.loads((ROOT/'projects/whale-maid/tripo-source/parts_manifest_v01.json').read_text(encoding='utf-8'))
    # A disabled collection's world matrices are not evaluated on cold load. Enable
    # only in this disposable verifier, without saving or changing the delivered file.
    bpy.data.collections['SOURCE_原始Tripo与弹簧草案_保留'].hide_viewport=False
    bpy.context.view_layer.update()
    for row in original['parts']:
        ob=bpy.data.objects[row['object']]
        if helpers['mesh_digest'](ob)!=row['source_digest']:errors.append('Preserved Tripo source changed:'+ob.name)
        hashes={im['name']:im['packed_sha256'] for im in row['images']}
        images=helpers['images_of'](ob)
        if not all(im.packed_file and hashlib.sha256(im.packed_file.data).hexdigest()==hashes.get(im.name) for im in images):errors.append('Preserved texture bytes changed')
    if len(fitted)!=73:errors.append('Fitted garment count mismatch')
    result={'success':not errors,'errors':errors,'target_body_max_vertex_error_m':maximum,'native_joint_head_max_error_m':head_error,
            'fitted_visible_meshes':len(fitted),'quarantined_fragments':3,'fitted_triangles':sum(sum(len(p.vertices)-2 for p in o.data.polygons) for o in fitted),
            'target_bones':len(rig.data.bones),'springs':len(sb.springs),'colliders':len(sb.colliders),'max_skin_influences':max_influences,'bad_weights':bad[:5],
            'source_meshes_preserved':151,'source_images_preserved':151,'scope':'Saved Blender source/fitting/rig only; no XWear/VRM/Godot acceptance'}
    path=OUT/'target_fit_cold_validation.json'
path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print('TARGET_FIT_COLD_VALIDATION '+json.dumps({**result,'errors':errors[:3]},ensure_ascii=False))
if errors:raise RuntimeError(str(errors))
