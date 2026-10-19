"""Render baked solver frames in a disposable background Blender, without live-app changes."""
import bpy
import math
from pathlib import Path
from mathutils import Matrix,Vector

OUT=Path(r'D:\vroidmcp\projects\whale-maid\tripo-source\cloth-springs-v01')
frames=OUT/'preview-frames';frames.mkdir(exist_ok=True)
source=bpy.context.scene
objects=[o for o in source.objects if o.type=='MESH' and 'source_part_id' in o]
assert len(objects)==151
scene=bpy.data.scenes.new('CLOTH_PREVIEW_RENDER_TEMP')
scene.render.engine='BLENDER_WORKBENCH'
scene.display.shading.light='STUDIO'
scene.display.shading.color_type='TEXTURE'
scene.display.shading.show_shadows=False
scene.display.shading.show_cavity=False
scene.display.shading.background_type='WORLD'
scene.world=bpy.data.worlds.new('CLOTH_PREVIEW_WORLD');scene.world.color=(.11,.11,.11)
scene.render.resolution_x=1000;scene.render.resolution_y=700;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
camera=bpy.data.objects.new('PREVIEW_CAMERA',bpy.data.cameras.new('PREVIEW_CAMERA'))
scene.collection.objects.link(camera);camera.location=(3,0,.50)
camera.rotation_euler=Vector((-1,0,0)).to_track_quat('-Z','Y').to_euler()
camera.data.type='ORTHO';camera.data.ortho_scale=1.65;scene.camera=camera
temp=[]
for f in range(1,122,3):
    source.frame_set(f);bpy.context.view_layer.update()
    deps=bpy.context.evaluated_depsgraph_get()
    for ob in temp:
        mesh=ob.data;bpy.data.objects.remove(ob,do_unlink=True)
        if mesh.users==0:bpy.data.meshes.remove(mesh)
    temp=[]
    for original in objects:
        mesh=bpy.data.meshes.new_from_object(original.evaluated_get(deps),depsgraph=deps)
        for sign in [-1,1]:
            ob=bpy.data.objects.new('PreviewPart',mesh);scene.collection.objects.link(ob)
            rotate=Matrix.Rotation(math.pi if sign>0 else 0,4,'Z')
            ob.matrix_world=Matrix.Translation((0,sign*.36,0))@rotate@original.matrix_world
            temp.append(ob)
    scene.render.filepath=str(frames/f'{f:03d}.png')
    bpy.ops.render.render(write_still=True,scene=scene.name)
    print(f'PREVIEW_FRAME {f}',flush=True)
print('CLOTH_PREVIEW_RENDER_COMPLETE',flush=True)
