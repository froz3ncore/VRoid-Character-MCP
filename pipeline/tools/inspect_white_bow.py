"""Read saved bow grid coordinates and render garment-only comparison views."""
import argparse, hashlib, json, sys
from pathlib import Path
import bpy
from mathutils import Matrix, Vector

C=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1)))

def render(out, prefix='before'):
    rig=bpy.data.objects['WM_TargetVRoidRig_v01']
    rig.data.vrm_addon_extension.spring_bone1.enable_animation=False
    for p in rig.pose.bones:p.matrix_basis.identity()
    bpy.context.view_layer.update()
    scene=bpy.data.scenes.new('WHITE_BOW_REVIEW')
    scene.render.engine='BLENDER_WORKBENCH'
    scene.display.shading.light='STUDIO'
    scene.display.shading.color_type='TEXTURE'
    scene.display.shading.show_shadows=True
    scene.display.shading.show_cavity=True
    scene.display.shading.cavity_type='BOTH'
    scene.display.shading.background_type='WORLD'
    scene.world=bpy.data.worlds.new('WHITE_BOW_WORLD');scene.world.color=(.11,.11,.13)
    scene.render.resolution_x=1000;scene.render.resolution_y=1000
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'
    data=bpy.data.cameras.new('WHITE_BOW_CAMERA');camera=bpy.data.objects.new('WHITE_BOW_CAMERA',data)
    scene.collection.objects.link(camera);scene.camera=camera;data.type='ORTHO'
    deps=bpy.context.evaluated_depsgraph_get()
    for obj in bpy.data.collections['FITTED_服装工作副本'].all_objects:
        if obj.type!='MESH':continue
        mesh=bpy.data.meshes.new_from_object(obj.evaluated_get(deps),depsgraph=deps)
        copy=bpy.data.objects.new('Review '+obj.name,mesh);scene.collection.objects.link(copy)
        copy.matrix_world=obj.matrix_world.copy()
    for name,center,scale,direction in [
        ('back',(0,.865,-.09),.53,(0,0,-1)),
        ('side',(0,.865,-.09),.53,(1,0,-.25)),
        ('whole-back',(0,.88,0),1.25,(0,0,-1))]:
        target=C.inverted()@Vector(center);d=C.inverted().to_3x3()@Vector(direction).normalized()
        camera.location=target+d*4;camera.rotation_euler=(-d).to_track_quat('-Z','Y').to_euler()
        data.ortho_scale=scale;scene.render.filepath=str(out/(prefix+'-'+name+'.png'))
        bpy.ops.render.render(write_still=True,scene=scene.name)

def main(a):
    out=a.out.resolve();out.mkdir(exist_ok=False)
    source=Path(bpy.data.filepath);sha=hashlib.sha256(source.read_bytes()).hexdigest();rows=[]
    for obj in bpy.data.objects:
        if not obj.name.startswith('FIT_NEW_Bow'):continue
        nr,nc=(24,12) if 'Wing' in obj.name else (40,10) if 'Tail' in obj.name else (12,12)
        pts=[C@obj.matrix_world@v.co for v in obj.data.vertices];count=(nr+1)*(nc+1)
        samples=[]
        for i in (0,nr//4,nr//2,3*nr//4,nr):
            samples.append({'row':i,'left':list(pts[i*(nc+1)]),'center':list(pts[i*(nc+1)+nc//2]),'right':list(pts[i*(nc+1)+nc])})
        rows.append({'name':obj.name,'vertices':len(pts),'custom_normals':obj.data.has_custom_normals,'samples':samples,
            'bounds':[[min(p[i] for p in pts),max(p[i] for p in pts)] for i in range(3)]})
    (out/'inspection.json').write_text(json.dumps({'source':str(source),'sha256':sha,'meshes':rows},indent=2),encoding='utf8')
    render(out)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==sha
    print(json.dumps({'inspected':len(rows),'source_unchanged':True}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    main(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
