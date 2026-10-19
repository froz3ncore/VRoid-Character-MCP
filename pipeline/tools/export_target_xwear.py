"""Export an explicit fitted-clothing subset via the Blender MCP Python API."""
import bpy, importlib.util, json, hashlib
from pathlib import Path
from mathutils import Matrix
ROOT=Path('D:/vroidmcp')
OUT=ROOT/'projects/whale-maid/xwear-textured-v01'
OUT.mkdir(exist_ok=True)
def run(filename='whale_maid_skirt_sample_v01.xwear', all_parts=False):
    spec=importlib.util.spec_from_file_location('vroid_xwear_direct',ROOT/'blender-addons/vroid_xwear_direct/__init__.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    rig=bpy.data.objects['WM_TargetVRoidRig_v01']
    collection=bpy.data.collections['FITTED_服装工作副本']
    meshes=[o for o in collection.all_objects if o.type=='MESH' and (all_parts or o.name.startswith('FIT_T001__'))]
    if not meshes:raise ValueError('Fitted sample not found')
    coord=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1)))
    before={i.name:hashlib.sha256(bytes(i.packed_file.data)).hexdigest() for i in bpy.data.images if i.packed_file}
    result=module.export_xwear(OUT/filename,rig,meshes,item_name='Whale maid fitted clothing — local test',author='Local test asset',coordinate_matrix=coord)
    after={i.name:hashlib.sha256(bytes(i.packed_file.data)).hexdigest() for i in bpy.data.images if i.packed_file}
    assert before==after,'Source images changed'
    source_textures={}
    for obj in meshes:
        for mat in obj.data.materials:
            if not mat or not mat.use_nodes:continue
            for node in mat.node_tree.nodes:
                image=getattr(node,'image',None)
                if not image or not image.packed_file:continue
                data=bytes(image.packed_file.data);digest=hashlib.sha256(data).hexdigest()
                suffix='.png' if data.startswith(b'\x89PNG') else '.jpg'
                evidence=OUT/('source-texture-'+digest[:16]+suffix)
                if not evidence.exists():evidence.write_bytes(data)
                source_textures[image.name]={'path':str(evidence),'sha256':digest}
    result['source_textures']=source_textures
    result['source_images_unchanged']=True
    result['coordinate_system']='Unity: -BlenderY, BlenderZ, BlenderX; preserves captured native body orientation'
    (OUT/(filename+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False))
