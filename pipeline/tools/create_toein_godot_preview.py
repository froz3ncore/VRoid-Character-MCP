"""Create a standalone generic GLB animation viewer; does not alter VRM imports."""
import argparse,json,shutil
from pathlib import Path
SCRIPT=r'''extends Node3D

var avatar: Node3D
var player: AnimationPlayer
var skeleton: Skeleton3D
var camera: Camera3D
var floor_node: MeshInstance3D
var floor_marks: Array = []
var build: Dictionary
var expected: Array
var total_time := 0.0
var cycles := 0
var previous_phase := 0.0
var samples: Array = []
var auto_test := false
var close_view := false
var hold_pause := false
var snapshots_done := {}

func _ready() -> void:
    auto_test = "--validate" in OS.get_cmdline_user_args()
    build = JSON.parse_string(FileAccess.get_file_as_string("res://build.json"))
    expected = JSON.parse_string(FileAccess.get_file_as_string("res://expected-poses.json"))
    var state := GLTFState.new()
    var document := GLTFDocument.new()
    var result := document.append_from_file(ProjectSettings.globalize_path("res://avatar.glb"), state)
    if result != OK:
        push_error("GLB load failed: %s" % result)
        get_tree().quit(2)
        return
    var bake_fps := float(build.animations[0].frames - 1) / float(build.profile.duration)
    avatar = document.generate_scene(state, bake_fps)
    add_child(avatar)
    player = avatar.find_child("AnimationPlayer", true, false) as AnimationPlayer
    for node in avatar.find_children("*", "Skeleton3D", true, false):
        var s := node as Skeleton3D
        if s.find_bone("J_Bip_L_Foot") >= 0 and s.find_bone("J_Bip_R_Foot") >= 0:
            skeleton = s
            break
    if player == null or skeleton == null:
        push_error("Animated leg skeleton missing")
        get_tree().quit(3)
        return
    print("ANIMATIONS ", player.get_animation_list())
    player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
    for name in player.get_animation_list():
        if name.begins_with("Walk_"):
            player.get_animation(name).loop_mode = Animation.LOOP_LINEAR
    _scene()
    if auto_test:
        _key_checks()
        var saved := ResourceSaver.save(player.get_animation_library(""), "res://walk-animations.res")
        assert(saved == OK)
        var reopened := ResourceLoader.load("res://walk-animations.res", "AnimationLibrary", ResourceLoader.CACHE_MODE_IGNORE) as AnimationLibrary
        assert(reopened != null and reopened.get_animation_list().size() == 4)
        player.remove_animation_library("")
        player.add_animation_library("", reopened)
        _key_checks()
        _save("library-reopen.json", {"passed": true, "animations": reopened.get_animation_list(), "source": "Saved binary AnimationLibrary reopened with cache ignored; then used for actual playback"})
    _play("Walk_ToeIn_RootMotion")
    _save("viewer-ready.json", {"pid": OS.get_process_id(), "interactive": not auto_test, "animation": "Walk_ToeIn_RootMotion", "scope": "Standalone generic GLB animation viewer"})

func _scene() -> void:
    var environment := WorldEnvironment.new()
    environment.environment = Environment.new()
    environment.environment.background_mode = Environment.BG_COLOR
    environment.environment.background_color = Color(0.12, 0.14, 0.18)
    environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
    environment.environment.ambient_light_color = Color.WHITE
    environment.environment.ambient_light_energy = 0.8
    add_child(environment)
    var light := DirectionalLight3D.new()
    light.rotation_degrees = Vector3(-35, -25, 0)
    light.light_energy = 1.5
    add_child(light)
    var plane := MeshInstance3D.new()
    var mesh := PlaneMesh.new()
    mesh.size = Vector2(12, 24)
    plane.mesh = mesh
    var material := StandardMaterial3D.new()
    material.albedo_color = Color(0.24, 0.27, 0.32)
    material.roughness = 0.9
    plane.material_override = material
    plane.position = Vector3(0, build.profile.ground_estimate, 6)
    add_child(plane)
    floor_node = plane
    # Fixed floor markings make foot sliding visible during root-motion playback.
    for i in range(-2, 25):
        var mark := MeshInstance3D.new()
        var box := BoxMesh.new()
        box.size = Vector3(2.5, 0.001, 0.009)
        mark.mesh = box
        mark.position = Vector3(0, build.profile.ground_estimate + 0.0005, i * 0.35)
        add_child(mark)
        floor_marks.append(mark)
    camera = Camera3D.new()
    camera.fov = 32
    camera.near = 0.02
    add_child(camera)
    camera.current = true
    var canvas := CanvasLayer.new()
    add_child(canvas)
    var panel := HBoxContainer.new()
    panel.position = Vector2(20, 20)
    panel.add_theme_constant_override("separation", 12)
    canvas.add_child(panel)
    for label in ["轻度内八", "原步态", "查看脚步", "暂停 / 继续"]:
        var button := Button.new()
        button.text = label
        panel.add_child(button)
        match label:
            "轻度内八": button.pressed.connect(func(): _play("Walk_ToeIn_RootMotion"))
            "原步态": button.pressed.connect(func(): _play("Walk_Native_RootMotion"))
            "查看脚步": button.pressed.connect(func(): close_view = not close_view)
            _: button.pressed.connect(func(): hold_pause = not hold_pause)

func _play(name: String) -> void:
    player.play(name)
    player.advance(0)
    cycles = 0
    previous_phase = 0
    avatar.position = Vector3.ZERO

func _bone(name: String) -> Transform3D:
    var index := skeleton.find_bone(name)
    return skeleton.global_transform * skeleton.get_bone_global_pose(index)

func _key_checks() -> void:
    player.play("Walk_ToeIn_InPlace")
    var maximum := 0.0
    var comparisons := 0
    var errors: Array = []
    for frame in expected:
        player.seek(float(frame.seconds), true)
        player.advance(0)
        for name in frame.bones:
            var matrix: Array = frame.bones[name]
            var target := Vector3(float(matrix[0][3]), float(matrix[1][3]), float(matrix[2][3]))
            var actual := _bone(name).origin
            var error := actual.distance_to(target)
            maximum = maxf(maximum, error)
            if error > 0.001:
                errors.append({"time": frame.seconds, "bone": name, "mm": error * 1000, "actual": [actual.x, actual.y, actual.z], "expected": [target.x, target.y, target.z]})
            comparisons += 1
    _save("key-check.json", {"maximum_position_error_mm": maximum * 1000, "comparisons": comparisons, "errors": errors, "passed": maximum < 0.001, "scope": "Generic Godot GLB skeletal animation; no VRM plugin or physics acceptance"})
    print("KEY_CHECK_MM ", maximum * 1000)
    if maximum >= 0.001:
        get_tree().quit(4)

func _process(delta: float) -> void:
    if player == null or skeleton == null:
        return
    if hold_pause:
        return
    player.advance(delta)
    total_time += delta
    var phase := float(player.current_animation_position)
    if phase < previous_phase:
        cycles += 1
    previous_phase = phase
    var travel := float(build.profile.travel_per_cycle_m[2])
    avatar.position.z = cycles * travel if player.current_animation.ends_with("RootMotion") else 0
    var focus := _bone("J_Bip_C_Hips").origin
    floor_node.position.z = focus.z + 6
    for i in range(floor_marks.size()):
        floor_marks[i].position.z = (floorf(focus.z / 0.35) + float(i) - 2) * 0.35
    camera.position = Vector3(0.5 if close_view else 0.8, 0.42 if close_view else 1.1, focus.z + (1.9 if close_view else 3.3))
    camera.look_at(Vector3(0, 0.27 if close_view else 0.86, focus.z))
    if auto_test:
        var feet := {}
        var foot_matrices := {}
        for side in ["L", "R"]:
            var local_point: Array = build.profile.landmarks[side][0]
            var point := Vector3(-float(local_point[0]), float(local_point[1]), float(local_point[2]))
            var sole := _bone("J_Bip_" + side + "_Foot") * point
            feet[side] = [sole.x, sole.y, sole.z]
            var transform := _bone("J_Bip_" + side + "_Foot")
            foot_matrices[side] = [transform.basis.x.x, transform.basis.y.x, transform.basis.z.x, transform.origin.x, transform.basis.x.y, transform.basis.y.y, transform.basis.z.y, transform.origin.y, transform.basis.x.z, transform.basis.y.z, transform.basis.z.z, transform.origin.z]
        samples.append({"seconds": total_time, "phase": phase, "cycle": cycles, "feet": feet, "foot_matrices": foot_matrices})
        close_view = total_time > 1.3 and total_time < 2.6
        for threshold in [1.6, 2.3]:
            if total_time > threshold and not snapshots_done.has(threshold) and DisplayServer.get_name() != "headless":
                snapshots_done[threshold] = true
                _snapshot_frame.call_deferred("feet-%.1f.png" % threshold)
        if total_time > 3.9:
            _save("runtime-samples.json", {"frames": samples, "continuous_playback": true, "cycles_observed": cycles, "scope": "Standalone generic GLB AnimationPlayer test; not godot-vrm or AnotherMe integration"})
            if DisplayServer.get_name() != "headless":
                _screenshot.call_deferred()
            else:
                get_tree().quit()

func _screenshot() -> void:
    await RenderingServer.frame_post_draw
    get_viewport().get_texture().get_image().save_png(ProjectSettings.globalize_path("res://runtime-preview.png"))
    get_tree().quit()

func _snapshot_frame(path: String) -> void:
    await RenderingServer.frame_post_draw
    get_viewport().get_texture().get_image().save_png(ProjectSettings.globalize_path("res://" + path))

func _save(path: String, value: Variant) -> void:
    var file := FileAccess.open("res://" + path, FileAccess.WRITE)
    file.store_string(JSON.stringify(value))
'''
def main(a):
    a.out.mkdir(exist_ok=False)
    for name in ['build.json','expected-poses.json']:shutil.copy2(a.animation/name,a.out/name)
    shutil.copy2(a.animation/'whale-maid-toein-walk-v04.glb',a.out/'avatar.glb')
    (a.out/'main.gd').write_text(SCRIPT,encoding='utf8')
    (a.out/'main.tscn').write_text('[gd_scene load_steps=2 format=3]\n\n[ext_resource type="Script" path="res://main.gd" id="1"]\n\n[node name="ToeInPreview" type="Node3D"]\nscript = ExtResource("1")\n',encoding='utf8')
    (a.out/'project.godot').write_text('config_version=5\n\n[application]\nconfig/name="轻度内八 · 独立动画预览"\nrun/main_scene="res://main.tscn"\n\n[display]\nwindow/size/viewport_width=960\nwindow/size/viewport_height=960\n\n[rendering]\nrenderer/rendering_method="gl_compatibility"\nrenderer/rendering_method.mobile="gl_compatibility"\n',encoding='utf8')
    print(json.dumps(dict(project=str(a.out.resolve()),plugin_or_import_settings_modified=False,scope='Generic GLB animation only; not VRM importer/physics acceptance')))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--animation',type=Path,required=True);p.add_argument('--out',type=Path,required=True);main(p.parse_args())
