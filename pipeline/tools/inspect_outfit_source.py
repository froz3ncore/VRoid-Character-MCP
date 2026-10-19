"""Read-only fitted mesh dimensions and textured front detail from a saved source."""
import argparse, hashlib, json, sys
from pathlib import Path
import bpy
from mathutils import Matrix, Vector

C = Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1)))


def main(a):
    out = a.out.resolve()
    out.mkdir(exist_ok=False)
    source = Path(bpy.data.filepath)
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    rig = bpy.data.objects['WM_TargetVRoidRig_v01']
    rig.data.vrm_addon_extension.spring_bone1.enable_animation = False
    for pose in rig.pose.bones:
        pose.matrix_basis.identity()
    bpy.context.view_layer.update()
    fitted = [o for o in bpy.data.collections['FITTED_服装工作副本'].all_objects if o.type == 'MESH']
    rows = []
    for obj in fitted:
        pts = [C@obj.matrix_world@v.co for v in obj.data.vertices]
        bones = sorted({obj.vertex_groups[g.group].name for v in obj.data.vertices for g in v.groups if g.weight>1e-7})
        rows.append({'name': obj.name, 'vertices': len(pts), 'bounds': [[min(p[i] for p in pts), max(p[i] for p in pts)] for i in range(3)], 'materials': [m.name if m else None for m in obj.data.materials], 'bones': bones})
    with (out/'inspection.json').open('x', encoding='utf8') as stream:
        json.dump({'source': str(source), 'source_sha256': sha, 'meshes': rows, 'source_saved': False}, stream, ensure_ascii=False, indent=2)
    scene = bpy.data.scenes.new('OUTFIT_READ_ONLY_REVIEW')
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.color_type = 'TEXTURE'
    scene.display.shading.show_shadows = False
    scene.display.shading.background_type = 'WORLD'
    scene.world = bpy.data.worlds.new('OUTFIT_READ_ONLY_WORLD')
    scene.world.color = (.15,.15,.15)
    scene.render.resolution_x = 1000
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    data = bpy.data.cameras.new('OUTFIT_READ_ONLY_CAMERA')
    camera = bpy.data.objects.new('OUTFIT_READ_ONLY_CAMERA', data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    data.type = 'ORTHO'
    deps = bpy.context.evaluated_depsgraph_get()
    for obj in fitted:
        mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(deps), depsgraph=deps)
        copy = bpy.data.objects.new('Review '+obj.name, mesh)
        scene.collection.objects.link(copy)
        copy.matrix_world = obj.matrix_world.copy()
    for name, center, scale in [('upper', (0,1.235,.02), .48), ('skirt', (0,.65,.02), .72)]:
        target = C.inverted()@Vector(center)
        direction = C.inverted().to_3x3()@Vector((0,0,1))
        camera.location = target+direction*4
        camera.rotation_euler = (-direction).to_track_quat('-Z','Y').to_euler()
        data.ortho_scale = scale
        scene.render.filepath = str(out/(name+'.png'))
        bpy.ops.render.render(write_still=True, scene=scene.name)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == sha
    print(json.dumps({'source_unchanged': True, 'meshes': len(rows), 'out': str(out)}), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    main(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
