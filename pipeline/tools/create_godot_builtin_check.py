"""Create an opt-in, isolated Godot builtin spring comparison from the checked importer."""
import argparse, hashlib, json, shutil, struct
from pathlib import Path
import create_godot_vrm_check as base

ROOT=Path(__file__).resolve().parents[1]

BACKEND=r'''extends RefCounted

static func resolve_name(skeleton: Skeleton3D, original: String) -> String:
    if skeleton.find_bone(original) >= 0:
        return original
    var mapping: Dictionary = skeleton.get_meta("vrm_rename_map", {})
    if mapping.has(StringName(original)):
        return str(mapping[StringName(original)])
    return original

static func parameter(values, index: int, scale: float) -> float:
    return scale * (float(values[index]) if index < values.size() else 1.0)

static func setup(skeleton: Skeleton3D, controller: Node) -> Dictionary:
    var result := {"backend":"Godot SpringBoneSimulator3D", "comparison_only":true,
        "errors":[],"warnings":[],"chains":[],"colliders":[],"imported_joint_total":0,
        "configured_joint_total":0,"unsupported_features":["plugin wind", "environment bodies", "group multipliers"],
        "scope":"Direct imported per-joint values; solver equivalence and collision freedom are unverified"}
    var simulation := SpringBoneSimulator3D.new()
    simulation.name = "BuiltinVRMSpringComparison"
    simulation.active = false
    skeleton.modifier_callback_mode_process = Skeleton3D.MODIFIER_CALLBACK_MODE_PROCESS_PHYSICS
    skeleton.add_child(simulation)
    var collision_map := {}
    var springs: Array = controller.get("spring_bones")
    for spring in springs:
        for group in spring.collider_groups:
            for collider in group.colliders:
                if collision_map.has(collider.get_instance_id()):
                    continue
                var resolved := resolve_name(skeleton, collider.bone)
                var offset: Vector3 = collider.offset
                var tail: Vector3 = collider.tail
                if collider.bone.is_empty():
                    var source: Node3D = controller.get_node_or_null(collider.node_path)
                    var cursor: Node = source
                    var local := Transform3D.IDENTITY
                    while cursor != null and not cursor is BoneAttachment3D:
                        if cursor is Node3D:local = cursor.transform*local
                        cursor = cursor.get_parent()
                    if cursor is BoneAttachment3D:
                        resolved = resolve_name(skeleton,cursor.bone_name)
                        offset = local*offset
                        tail = local*tail
                        if not local.basis.get_scale().is_equal_approx(Vector3.ONE):
                            result.errors.append("Scaled collider attachment is unsupported: "+str(collider.node_path))
                    else:
                        result.errors.append("Collider is not attached to a skeleton bone: "+str(collider.node_path))
                if skeleton.find_bone(resolved) < 0:
                    result.errors.append("Missing collider bone: "+resolved)
                var actual: SpringBoneCollision3D
                if collider.is_capsule:
                    var capsule := SpringBoneCollisionCapsule3D.new()
                    capsule.radius = collider.radius
                    capsule.mid_height = offset.distance_to(tail)
                    if capsule.mid_height > 0.000001:
                        capsule.rotation_offset = Quaternion(Vector3.UP, (tail-offset).normalized())
                    actual = capsule
                    actual.position_offset = (offset+tail)*0.5
                else:
                    var sphere := SpringBoneCollisionSphere3D.new()
                    sphere.radius = collider.radius
                    actual = sphere
                    actual.position_offset = offset
                simulation.add_child(actual)
                actual.name = "Collider_%02d" % collision_map.size()
                actual.bone_name = resolved
                collision_map[collider.get_instance_id()] = actual
                result.colliders.append({"bone":resolved,"node_path":str(collider.node_path),
                    "radius":collider.radius,"capsule":collider.is_capsule,
                    "offset":str(offset),"tail":str(tail),"binding":"resolved BoneAttachment or bone"})
    simulation.setting_count = springs.size()
    for index in springs.size():
        var spring = springs[index]
        var names: PackedStringArray = spring.joint_nodes
        result.imported_joint_total += names.size()
        if names.is_empty():
            result.errors.append("Empty spring chain")
            continue
        var resolved_names: PackedStringArray = []
        for name in names:
            var resolved := resolve_name(skeleton, name)
            if skeleton.find_bone(resolved) < 0:
                result.errors.append("Missing joint bone: "+name)
            resolved_names.append(resolved)
        simulation.set_root_bone_name(index, resolved_names[0])
        simulation.set_end_bone_name(index, resolved_names[-1])
        simulation.set_extend_end_bone(index, false)
        simulation.set_individual_config(index, true)
        var configured := simulation.get_joint_count(index)
        result.configured_joint_total += configured
        var order_matches := configured == resolved_names.size()
        for joint in configured:
            if joint >= resolved_names.size() or simulation.get_joint_bone_name(index,joint) != resolved_names[joint]:
                order_matches = false
        if not order_matches:
            result.errors.append("Joint order/count differs: "+spring.comment)
        for joint in mini(configured,resolved_names.size()):
            simulation.set_joint_stiffness(index,joint,parameter(spring.stiffness_force,joint,spring.stiffness_scale))
            simulation.set_joint_drag(index,joint,parameter(spring.drag_force,joint,spring.drag_force_scale))
            simulation.set_joint_radius(index,joint,parameter(spring.hit_radius,joint,spring.hit_radius_scale))
            simulation.set_joint_gravity(index,joint,parameter(spring.gravity_power,joint,spring.gravity_scale))
            simulation.set_joint_gravity_direction(index,joint,spring.gravity_dir[joint] if joint < spring.gravity_dir.size() else spring.gravity_dir_default)
        if not spring.center_bone.is_empty():
            simulation.set_center_from(index,SpringBoneSimulator3D.CENTER_FROM_BONE)
            simulation.set_center_bone_name(index,resolve_name(skeleton,spring.center_bone))
        elif not spring.center_node.is_empty():
            var center := controller.get_node_or_null(spring.center_node)
            if center != null:
                simulation.set_center_from(index,SpringBoneSimulator3D.CENTER_FROM_NODE)
                simulation.set_center_node(index,simulation.get_path_to(center))
            else:
                result.errors.append("Missing center node: "+str(spring.center_node))
        else:
            simulation.set_center_from(index,SpringBoneSimulator3D.CENTER_FROM_WORLD_ORIGIN)
        simulation.set_enable_all_child_collisions(index,false)
        var paths: Array[NodePath] = []
        for group in spring.collider_groups:
            for collider in group.colliders:
                var target: SpringBoneCollision3D = collision_map[collider.get_instance_id()]
                var path := simulation.get_path_to(target)
                if not paths.has(path):paths.append(path)
        simulation.set_collision_count(index,paths.size())
        for i in paths.size():simulation.set_collision_path(index,i,paths[i])
        result.chains.append({"comment":spring.comment,"joints":resolved_names,
            "imported_joint_count":names.size(),"configured_joint_count":configured,
            "collision_count":paths.size(),"extended_end":false})
    simulation.active = result.errors.is_empty()
    simulation.reset()
    result["simulator"] = simulation
    return result
'''

RECORD=r'''
func _record_builtin_pose() -> void:
    var angles := {}
    var rotations := {}
    var max_angle := 0.0
    var finite := true
    for bone in initial_springs:
        var rotation := skeleton.get_bone_pose_rotation(bone)
        finite = finite and rotation.is_finite()
        var angle: float = initial_springs[bone].angle_to(rotation)
        max_angle = max(max_angle,angle)
        angles[skeleton.get_bone_name(bone)] = angle
        rotations[skeleton.get_bone_name(bone)] = [rotation.x,rotation.y,rotation.z,rotation.w]
    last_builtin_sample = {"modifier_frame":frame_index,"max_skirt_rotation_radians":max_angle,
        "angles":angles,"rotations":rotations,"finite":finite,"measured_during_modifier":true}
'''

def create(source,out,vrm=None):
    source,out=Path(source).resolve(),Path(out).resolve()
    assert source.is_relative_to(ROOT/'projects/whale-maid') and out.is_relative_to(ROOT/'projects/whale-maid')
    assert not out.exists()
    out.mkdir(parents=True)
    for name in ('vrm','Godot-MToon-Shader'):
        shutil.copytree(source/'addons'/name,out/'addons'/name,
            ignore=shutil.ignore_patterns('bin','.git','.godot','~*','*.TMP'))
    shutil.copytree(source/'Script',out/'Script')
    (out/'assets').mkdir()
    shutil.copy2(vrm or source/'assets/avatar.vrm',out/'assets/avatar.vrm')
    shutil.copy2(source/'assets/avatar.vrm.import',out/'assets/avatar.vrm.import')
    shutil.copy2(source/'import-profile.json',out/'import-profile.json')
    project=base.PROJECT.replace('Whale maid isolated VRM acceptance','Whale maid builtin spring comparison')
    project+='\n[validation]\nbuiltin_spring_comparison=true\n'
    (out/'project.godot').write_text(project,encoding='utf8')
    adapter=out/'addons/vrm/runtime/vrm_spring_bone_adapter.gd'
    text=adapter.read_text(encoding='utf8')
    text=text.replace('if not has_simulation:\n        VRMLogger.error(',
        'if not has_simulation and not ProjectSettings.get_setting("validation/builtin_spring_comparison",false):\n        VRMLogger.error(',1)
    adapter.write_text(text,encoding='utf8')
    # Godot parses skin membership before _import_post_parse. Add only referenced
    # VRM joints/colliders/centers during preflight, not unrelated descendants.
    importer=out/'addons/vrm/importer/v1/vrmc/vrmc_vrm.gd'
    text=importer.read_text(encoding='utf8')
    text=text.replace('    vrm_utils.apply_default_import_settings(_state)',
        '''    if not _state.has_meta("vrm1_joint_skin_added_preflight"):
        var required: Dictionary = {}
        var obj: Dictionary = _state.json
        for bone in obj["extensions"]["VRMC_vrm"]["humanoid"]["humanBones"].values():
            required[int(bone["node"])] = true
        var secondary: Dictionary = obj.get("extensions",{}).get("VRMC_springBone",{})
        for collider in secondary.get("colliders",[]):
            required[int(collider["node"])] = true
        for spring in secondary.get("springs",[]):
            for joint in spring.get("joints",[]):
                required[int(joint["node"])] = true
            if spring.has("center"):
                required[int(spring["center"])] = true
        _add_joint_set_as_skin(obj,required)
        _state.set_meta("vrm1_joint_skin_added_preflight",true)
    vrm_utils.apply_default_import_settings(_state)''',1)
    text=text.replace('func _import_post_parse(state: GLTFState) -> Error:\n',
        'func _import_post_parse(state: GLTFState) -> Error:\n    if state.has_meta("vrm1_joint_skin_added_preflight"):\n        return OK\n',1)
    importer.write_text(text,encoding='utf8')
    (out/'builtin_backend.gd').write_text(BACKEND,encoding='utf8')
    script='const BuiltinBackend = preload("res://builtin_backend.gd")\n'
    script=base.SCRIPT.replace('extends Node3D','extends Node3D\n'+script+'\nvar last_builtin_sample := {}',1)
    insertion='''    var setup := BuiltinBackend.setup(skeleton,controller)
    var simulator: SpringBoneSimulator3D = setup["simulator"]
    setup.erase("simulator")
    report["backend_setup"] = setup
    report["comparison_only"] = true
    report["collision_free"] = false
    report["passed_cpp_physics_runtime"] = false
    simulator.modification_processed.connect(_record_builtin_pose)
    var expected: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://expected-springs.json"))
    var joint_counts_match := true
    var joint_names_match := true
    for chain in setup["chains"]:
        if not expected.has(chain["comment"]) or expected[chain["comment"]]["joints"].size() != chain["configured_joint_count"]:
            joint_counts_match = false
        elif expected.has(chain["comment"]):
            var source_names = expected[chain["comment"]]["joints"]
            for index in source_names.size():
                if BuiltinBackend.resolve_name(skeleton,source_names[index]) != chain["joints"][index]:
                    joint_names_match = false
    report["source_joint_counts_match"] = joint_counts_match and setup["chains"].size() == expected.size()
    report["source_joint_names_match"] = joint_names_match
'''
    script=script.replace('    var environment := WorldEnvironment.new()',insertion+'    var environment := WorldEnvironment.new()',1)
    script=script.replace('skeleton.get_node_or_null("VRMSpringBoneSimulation")','skeleton.get_node_or_null("BuiltinVRMSpringComparison")')
    begin=script.index('    var angles := {}',script.index('func _sample()'))
    end=script.index('    if DisplayServer.get_name()',begin)
    script=script[:begin]+'''    if not last_builtin_sample.is_empty():
        var sample: Dictionary = last_builtin_sample.duplicate(true)
        sample["physics_frame"] = frame_index
        measurements.append(sample)
'''+script[end:]
    script=script.replace('report["native_spring_extension_available"] and spring_motion_observed',
        'report["backend_setup"]["errors"].is_empty() and report["source_joint_counts_match"] and report["source_joint_names_match"] and spring_motion_observed')
    motion_begin=script.index('    var spring_motion_observed := false',script.index('func _finish()'))
    motion_end=script.index('    report["spring_motion_observed"]',motion_begin)
    script=script[:motion_begin]+'''    var spring_motion_observed := false
    var rear_peak := 0.0
    var finite := true
    var recovery_difference := 0.0
    if not measurements.is_empty():
        var settled: Dictionary = measurements[0]["rotations"]
        for sample in measurements:
            finite = finite and sample["finite"]
            for name in sample["rotations"]:
                var ring := str(name).split("_")[2].to_int()
                if ring < 4 or ring > 8:continue
                var a = settled[name]
                var b = sample["rotations"][name]
                var difference: float = Quaternion(a[0],a[1],a[2],a[3]).angle_to(Quaternion(b[0],b[1],b[2],b[3]))
                rear_peak = max(rear_peak,difference)
                if sample == measurements[-1]:recovery_difference = max(recovery_difference,difference)
    spring_motion_observed = rear_peak > 0.01 and finite and measurements.size() == 7
    report["rear_peak_from_settled_radians"] = rear_peak
    report["rear_final_from_settled_radians"] = recovery_difference
    report["finite_simulation_samples"] = finite
'''+script[motion_end:]
    script+=RECORD
    script=script.replace('camera.position = Vector3(2.1,1.2,-2.6)','camera.position = Vector3(1.4,0.8,2.0)')
    script=script.replace('camera.look_at(Vector3(0,0.8,0))','camera.look_at(Vector3(0,0.55,0))')
    script=script.replace('camera.fov = 35','camera.fov = 32')
    script=script.replace('    if frame_index == 330:',
        '''    if frame_index % 6 == 0 and frame_index < 330 and "--record-motion" in OS.get_cmdline_user_args():
        call_deferred("_capture_motion_frame")
    if frame_index == 330:''',1)
    script+='''
func _capture_motion_frame() -> void:
    if DisplayServer.get_name() == "headless":return
    var frame := frame_index
    await RenderingServer.frame_post_draw
    get_viewport().get_texture().get_image().save_png(output_folder + "/motion-%03d.png" % frame)
'''
    (out/'check.gd').write_text(script,encoding='utf8')
    shutil.copy2(source/'check.tscn',out/'check.tscn')
    shutil.copy2(source/'reimport_check.gd',out/'reimport_check.gd')
    raw=(out/'assets/avatar.vrm').read_bytes()
    document=json.loads(raw[20:20+struct.unpack_from('<I',raw,12)[0]])
    expected={s['name']:{'joints':[document['nodes'][j['node']]['name'] for j in s['joints']]} for s in document['extensions']['VRMC_springBone']['springs']}
    (out/'expected-springs.json').write_text(json.dumps(expected,indent=2),encoding='utf8')
    metadata={'source':str(source),'vrm_sha256':hashlib.sha256((out/'assets/avatar.vrm').read_bytes()).hexdigest(),
        'import_profile_sha256':hashlib.sha256((out/'import-profile.json').read_bytes()).hexdigest(),
        'external_physics_library_copied':False,'system_policy_modified':False,'comparison_only':True,
        'original_project_modified':False,'source_template_modified':False,'vrm_joint_skin_added_in_preflight':True}
    (out/'comparison-setup.json').write_text(json.dumps(metadata,indent=2),encoding='utf8')
    print(json.dumps({'created':str(out),**metadata}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--vrm',type=Path)
    a=p.parse_args();create(a.source,a.out,a.vrm)
