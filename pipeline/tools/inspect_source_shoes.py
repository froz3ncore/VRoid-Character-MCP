"""Render preserved Tripo shoes/legs and sample their material boundaries."""
import bpy,json,sys,math
from pathlib import Path
from mathutils import Vector,Matrix
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'projects/whale-maid/accessory-refinement-v02/inspection-source-shoes';out.mkdir(exist_ok=False)
manifest=json.loads((ROOT/'projects/whale-maid/tripo-source/parts_manifest_v01.json').read_text(encoding='utf8'))
scene=bpy.data.scenes.new('Source shoe review');scene.render.engine='BLENDER_WORKBENCH'
scene.display.shading.light='STUDIO';scene.display.shading.color_type='TEXTURE';scene.display.shading.show_shadows=False
scene.render.resolution_x=900;scene.render.resolution_y=650;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG'
for row in manifest['parts']:
 if row['source_id'] not in (4,5) and not row['collection'].startswith('14_'):continue
 original=bpy.data.objects[row['object']];points=[original.matrix_world@v.co for v in original.data.vertices]
 center=Vector(tuple((min(p[k] for p in points)+max(p[k] for p in points))/2 for k in range(3)))
 canonical=(Vector(row['bounds'][0])+Vector(row['bounds'][1]))/2
 data=original.data.copy();ob=bpy.data.objects.new(original.name+' review',data);scene.collection.objects.link(ob)
 for v,p in zip(data.vertices,points):v.co=p+canonical-center
 ob.hide_viewport=False;ob.hide_render=False
camera_data=bpy.data.cameras.new('Shoe review');camera=bpy.data.objects.new('Shoe review',camera_data);scene.collection.objects.link(camera);scene.camera=camera
camera_data.type='ORTHO';camera_data.ortho_scale=.31
center=Vector((.02,0,.065))
for label,direction in [('threequarter',Vector((1,-1,.4)).normalized()),('side',Vector((0,-1,.12)).normalized()),('front',Vector((1,0,.12)).normalized())]:
 camera.location=center+direction;camera.rotation_euler=(-direction).to_track_quat('-Z','Y').to_euler();scene.render.filepath=str(out/(label+'.png'));bpy.ops.render.render(write_still=True,scene=scene.name)
print('Source shoe review complete',flush=True)
