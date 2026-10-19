"""Create an isolated Godot check using the project's actual VRM importer snapshot."""
import argparse,hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
GAME=Path('D:/godot/anotherme_2026-03-18_22-59-30/another-me')

PROJECT='''config_version=5
[application]
config/name="Whale maid isolated VRM acceptance"
run/main_scene="res://check.tscn"
[display]
window/size/viewport_width=960
window/size/viewport_height=960
[editor_plugins]
enabled=PackedStringArray("res://addons/vrm/plugin.cfg")
[rendering]
rendering_device/driver.windows="d3d12"
anti_aliasing/quality/screen_space_aa=2
'''

SCRIPT='''extends Node3D

var avatar: Node3D
var skeleton: Skeleton3D
var controller: Node
var camera: Camera3D
var frame_index := 0
var initial_springs := {}
var original_poses := {}
var measurements: Array = []
var first_frame := {}
var report := {}
var left_leg := -1
var right_leg := -1
var left_lower := -1
var right_lower := -1
var output_folder := "res://runtime-" + str(Time.get_unix_time_from_system()).replace(".","_")

func _ready() -> void:
    DirAccess.make_dir_recursive_absolute(output_folder)
    var packed = load("res://assets/avatar.vrm")
    if not packed is PackedScene:
        push_error("VRM did not import as PackedScene")
        get_tree().quit(2)
        return
    avatar = packed.instantiate()
    add_child(avatar)
    var skeletons := avatar.find_children("*", "Skeleton3D", true, false)
    if skeletons.is_empty():
        get_tree().quit(3)
        return
    skeleton = skeletons[0]
    controller = avatar.find_child("VRMSpringBoneController", true, false)
    var meshes := avatar.find_children("*", "MeshInstance3D", true, false)
    var materials := {}
    var null_materials := 0
    var surfaces := 0
    for mesh in meshes:
        if mesh.mesh == null:
            continue
        for surface in mesh.mesh.get_surface_count():
            surfaces += 1
            var material = mesh.get_active_material(surface)
            if material == null:
                null_materials += 1
            else:
                materials[material.get_instance_id()] = true
    for bone in skeleton.get_bone_count():
        original_poses[bone] = skeleton.get_bone_pose_rotation(bone)
        if skeleton.get_bone_name(bone).begins_with("WM_Skirt_"):
            initial_springs[bone] = skeleton.get_bone_pose_rotation(bone)
    left_leg = skeleton.find_bone("J_Bip_L_UpperLeg")
    right_leg = skeleton.find_bone("J_Bip_R_UpperLeg")
    left_lower = skeleton.find_bone("J_Bip_L_LowerLeg")
    right_lower = skeleton.find_bone("J_Bip_R_LowerLeg")
    if left_leg < 0: left_leg = skeleton.find_bone("LeftUpperLeg")
    if right_leg < 0: right_leg = skeleton.find_bone("RightUpperLeg")
    if left_lower < 0: left_lower = skeleton.find_bone("LeftLowerLeg")
    if right_lower < 0: right_lower = skeleton.find_bone("RightLowerLeg")
    report = {"engine": Engine.get_version_info(), "meshes": meshes.size(), "surfaces": surfaces,
        "materials": materials.size(), "missing_materials": null_materials,
        "bones": skeleton.get_bone_count(), "skirt_bones": initial_springs.size(),
        "native_spring_extension_available": ClassDB.class_exists("VRMSpringBoneSimulation"),
        "spring_controller": controller != null, "left_leg": left_leg, "right_leg": right_leg,
        "scope": "Isolated importer and synthetic body motion check; no native walking or collision-free certification"}
    report["mesh_names"] = meshes.map(func(mesh): return str(mesh.name))
    report["garment_mesh_count"] = meshes.filter(func(mesh): return str(mesh.name).begins_with("FIT_")).size()
    report["skeleton_name"] = str(skeleton.name)
    var import_config := ConfigFile.new()
    import_config.load("res://assets/avatar.vrm.import")
    report["import_settings"] = {}
    for key in import_config.get_section_keys("params"):
        if str(key).begins_with("vrm/") or key == "import_script/path":
            report["import_settings"][key] = import_config.get_value("params",key)
    if controller:
        report["spring_chains"] = controller.get("spring_bones").size()
        report["colliders"] = controller.get("collider_library").size()
    var environment := WorldEnvironment.new()
    environment.environment = Environment.new()
    environment.environment.background_mode = Environment.BG_COLOR
    environment.environment.background_color = Color(0.13,0.15,0.19)
    environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
    environment.environment.ambient_light_color = Color.WHITE
    environment.environment.ambient_light_energy = 0.7
    add_child(environment)
    var light := DirectionalLight3D.new()
    light.rotation_degrees = Vector3(-35,-30,0)
    light.light_energy = 1.2
    add_child(light)
    camera = Camera3D.new()
    add_child(camera)
    camera.position = Vector3(2.1,1.2,-2.6)
    camera.look_at(Vector3(0,0.8,0))
    camera.fov = 35
    camera.current = true
    await get_tree().process_frame
    report["simulation_node"] = skeleton.get_node_or_null("VRMSpringBoneSimulation") != null

func _physics_process(_delta: float) -> void:
    if skeleton == null:
        return
    frame_index += 1
    var t := frame_index / 60.0
    # Separate test from native WALK00_F: a repeatable hip rotation, leg sweep,
    # then stationary recovery. Preserve the model's imported pose rotations.
    var motion := 0.0
    if t > 1.0 and t < 3.0:
        motion = sin((t - 1.0) * PI) * 0.75
    for pair in [[left_leg,motion],[right_leg,-motion]]:
        if pair[0] >= 0:
            skeleton.set_bone_pose_rotation(pair[0],original_poses[pair[0]] * Quaternion(Vector3.RIGHT,pair[1]))
    for pair in [[left_lower,max(0.0,motion)],[right_lower,max(0.0,-motion)]]:
        if pair[0] >= 0:
            skeleton.set_bone_pose_rotation(pair[0],original_poses[pair[0]] * Quaternion(Vector3.RIGHT,pair[1]*0.6))
    if frame_index in [60,90,120,150,180,240,300]:
        call_deferred("_sample")
    if frame_index == 330:
        call_deferred("_finish")

func _sample() -> void:
    var angles := {}
    var max_angle := 0.0
    for bone in initial_springs:
        var angle: float = initial_springs[bone].angle_to(skeleton.get_bone_pose_rotation(bone))
        max_angle = max(max_angle,angle)
        angles[skeleton.get_bone_name(bone)] = angle
    measurements.append({"physics_frame":frame_index,"max_skirt_rotation_radians":max_angle,"angles":angles})
    if DisplayServer.get_name() != "headless":
        await RenderingServer.frame_post_draw
        get_viewport().get_texture().get_image().save_png(output_folder + "/frame-%03d.png" % frame_index)

func _finish() -> void:
    report["measurements"] = measurements
    report["passed_resource_import"] = report["garment_mesh_count"] == 69 and report["missing_materials"] == 0 and left_leg >= 0 and right_leg >= 0
    var spring_motion_observed := false
    for sample in measurements:
        if sample["max_skirt_rotation_radians"] > 0.01:
            spring_motion_observed = true
    report["spring_motion_observed"] = spring_motion_observed
    report["passed_physics_runtime"] = report["simulation_node"] and report["native_spring_extension_available"] and spring_motion_observed
    report["passed_import_runtime"] = report["passed_resource_import"] and report["passed_physics_runtime"]
    var file := FileAccess.open(output_folder + "/acceptance.json",FileAccess.WRITE)
    file.store_string(JSON.stringify(report,"  "))
    print("GODOT_VRM_ACCEPTANCE ",JSON.stringify({"passed":report["passed_import_runtime"],"meshes":report["meshes"],"bones":report["bones"],"spring_chains":report.get("spring_chains",0),"colliders":report.get("colliders",0)}))
    get_tree().quit(0 if report["passed_import_runtime"] else 4)
'''

def apply_import_profile(out):
    out=Path(out)
    source=GAME/'Assets/character/main_female_c.vrm.import'
    text=source.read_text(encoding='utf8');params=text.split('[params]',1)[1]
    params=params.replace('import_script/path="uid://304fk0747j5c"','import_script/path="res://Script/vrm_post_import.gd"')
    (out/'Script').mkdir(exist_ok=True)
    for name in ('vrm_post_import.gd','vrm_post_import.gd.uid'):shutil.copy2(GAME/'Script'/name,out/'Script'/name)
    target=out/'assets/avatar.vrm.import'
    header=target.read_text(encoding='utf8').split('[params]',1)[0] if target.exists() else '[remap]\nimporter="scene"\ntype="PackedScene"\n[deps]\nsource_file="res://assets/avatar.vrm"\n'
    target.write_text(header+'[params]'+params,encoding='utf8')
    profile={'source_import_settings':str(source),'source_settings_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'post_import_script_sha256':hashlib.sha256((GAME/'Script/vrm_post_import.gd').read_bytes()).hexdigest(),
        'effective_params':dict(line.split('=',1) for line in params.splitlines() if '=' in line),
        'path_adjustment':'Same post-import script copied into isolated res://Script path; no source settings altered'}
    (out/'import-profile.json').write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf8')
    return profile

def main():
    p=argparse.ArgumentParser();p.add_argument('--vrm',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    out=a.out.resolve();assert out.is_relative_to(ROOT/'projects/whale-maid') and not out.exists();out.mkdir(parents=True)
    records={}
    for name in ('vrm','Godot-MToon-Shader'):
        source=GAME/'addons'/name;shutil.copytree(source,out/'addons'/name,ignore=shutil.ignore_patterns('.git','.godot'))
        for path in source.rglob('*'):
            if path.is_file():records[str(path.relative_to(GAME))]=hashlib.sha256(path.read_bytes()).hexdigest()
    (out/'assets').mkdir();shutil.copy2(a.vrm,out/'assets/avatar.vrm')
    (out/'project.godot').write_text(PROJECT,encoding='utf8')
    (out/'check.gd').write_text(SCRIPT,encoding='utf8')
    (out/'check.tscn').write_text('[gd_scene load_steps=2 format=3]\n[ext_resource type="Script" path="res://check.gd" id="1"]\n[node name="VRMCheck" type="Node3D"]\nscript = ExtResource("1")\n',encoding='utf8')
    apply_import_profile(out)
    (out/'source-snapshot.json').write_text(json.dumps({'source_project':str(GAME),'addon_hashes':records,'vrm_sha256':hashlib.sha256(a.vrm.read_bytes()).hexdigest()},indent=2),encoding='utf8')
    print(str(out))

if __name__=='__main__':main()
