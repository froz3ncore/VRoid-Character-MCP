"""Configure selective rear-skirt leg-contact guards from explicit body bones."""
import bpy,json,hashlib,math
from mathutils import Vector

def configure(profile):
    rig=bpy.data.objects[profile['rig']];spring=rig.data.vrm_addon_extension.spring_bone1
    wanted=set(profile['rear_springs']);actual={s.vrm_name:s for s in spring.springs}
    if not wanted or wanted-set(actual):raise ValueError('Unknown rear skirt spring chain')
    if any(abs(x-1)>1e-6 for x in rig.matrix_world.to_scale()):raise ValueError('Unit armature scale required')
    if any(g.vrm_name==profile['group_name'] for g in spring.collider_groups):raise ValueError('Contact group already exists')
    specs=profile['guards'];back=Vector(profile['backward_axis']).normalized()
    if len(specs)!=4 or back.length<.9:raise ValueError('Explicit thigh/shin guards for both legs required')
    for spec in specs:
        if spec['start_bone'] not in rig.data.bones or spec['end_bone'] not in rig.data.bones:raise ValueError('Leg bone missing')
        if not all(math.isfinite(spec[k]) for k in ('radius_m','back_offset_m')) or not .01<=spec['radius_m']<=.15 or not 0<=spec['back_offset_m']<=.05:raise ValueError('Invalid guard size')
        if not 0<=spec.get('start_fraction',0)<=.5:raise ValueError('Invalid guard start fraction')
    hit=profile['joint_hit_radius_m']
    if not math.isfinite(hit) or not .001<=hit<=.04:raise ValueError('Invalid rear joint radius')
    prior={s.vrm_name:{'groups':[g.collider_group_uuid for g in s.collider_groups],
                    'joint_radius':[j.hit_radius for j in s.joints]} for s in spring.springs}
    original_colliders=[c.uuid for c in spring.colliders];guards=[]
    for spec in specs:
        start=rig.data.bones[spec['start_bone']];end=rig.data.bones[spec['end_bone']]
        inverse=start.matrix_local.inverted();shift=back*spec['back_offset_m']
        collider=spring.add_collider(bpy.context,rig);collider.node.bone_name=start.name
        collider.shape_type=collider.SHAPE_TYPE_CAPSULE.identifier;collider.reset_bpy_object(bpy.context,rig)
        begin=start.head_local.lerp(end.head_local,spec.get('start_fraction',0))
        collider.shape.capsule.offset=inverse@(begin+shift)
        collider.shape.capsule.tail=inverse@(end.head_local+shift);collider.shape.capsule.radius=spec['radius_m']
        collider.bpy_object.name='REAR_CONTACT_'+spec['name'];collider.bpy_object.hide_render=True
        for child in collider.bpy_object.children:child.hide_render=True
        guards.append({'name':spec['name'],'uuid':collider.uuid,'bone':start.name,
            'radius_m':collider.shape.capsule.radius,'offset':list(collider.shape.capsule.offset),'tail':list(collider.shape.capsule.tail)})
    group=spring.add_collider_group();group.vrm_name=profile['group_name']
    for uuid in original_colliders+[g['uuid'] for g in guards]:group.add_collider().collider_uuid=uuid
    for name in wanted:
        selected=actual[name];selected.collider_groups.clear();selected.add_collider_group().collider_group_uuid=group.uuid
        for index,joint in enumerate(selected.joints):
            if index>0 or not profile.get('preserve_root_radius',False):joint.hit_radius=hit
    spring.fixup()
    for name,s in actual.items():
        if name not in wanted:
            assert [g.collider_group_uuid for g in s.collider_groups]==prior[name]['groups']
            assert [j.hit_radius for j in s.joints]==prior[name]['joint_radius']
    return {'rear_springs':sorted(wanted),'joint_hit_radius_m':hit,'guards':guards,'colliders':len(spring.colliders),
        'collider_groups':len(spring.collider_groups),'front_and_ribbon_contacts_unchanged':True,'native_acceptance':False}
