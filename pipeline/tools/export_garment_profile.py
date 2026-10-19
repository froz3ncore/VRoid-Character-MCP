"""Export an explicit collection/rig from a saved source without scene mutation."""
import argparse,bpy,hashlib,importlib.util,json,sys
from pathlib import Path
from mathutils import Matrix
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--rig',required=True)
p.add_argument('--collection',required=True);p.add_argument('--front-axis',choices=['+X','-Y'],default='+X');p.add_argument('--out',type=Path,required=True)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
assert Path(bpy.data.filepath).resolve()==a.source.resolve() and not a.out.exists()
original_hash=hashlib.sha256(a.source.read_bytes()).hexdigest()
spec=importlib.util.spec_from_file_location('vroid_xwear_direct',ROOT/'blender-addons/vroid_xwear_direct/__init__.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
rig=bpy.data.objects[a.rig];meshes=[o for o in bpy.data.collections[a.collection].all_objects if o.type=='MESH']
spring=rig.data.vrm_addon_extension.spring_bone1
enabled=spring.enable_animation;poses={p.name:p.matrix_basis.copy() for p in rig.pose.bones}
coord=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1))) if a.front_axis=='+X' else module.COORD
try:
    spring.enable_animation=False
    for pose in rig.pose.bones:pose.matrix_basis.identity()
    bpy.context.view_layer.update()
    result=module.export_xwear(a.out,rig,meshes,item_name='Original garment — bounded multi-pose fit',author='Local creator',coordinate_matrix=coord)
    textures={}
    for obj in meshes:
        for material in obj.data.materials:
            if not material or not material.use_nodes:continue
            for node in material.node_tree.nodes:
                image=getattr(node,'image',None)
                if not image or not image.packed_file:continue
                data=bytes(image.packed_file.data);digest=hashlib.sha256(data).hexdigest()
                path=a.out.parent/('source-texture-'+digest[:16]+('.png' if data.startswith(b'\x89PNG') else '.jpg'))
                if not path.exists():path.write_bytes(data)
                assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
                textures[image.name]={'path':str(path.resolve()),'sha256':digest}
    result.update(source_textures=textures,source_blend=str(a.source.resolve()),source_sha256=original_hash,source_images_unchanged=True)
    with a.out.with_suffix('.xwear.json').open('x',encoding='utf8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
finally:
    for pose in rig.pose.bones:pose.matrix_basis=poses[pose.name]
    spring.enable_animation=enabled
assert hashlib.sha256(a.source.read_bytes()).hexdigest()==original_hash
print('GARMENT_PROFILE_EXPORT_OK '+json.dumps({'path':str(a.out),'meshes':len(meshes),'sha256':result['sha256']}))
