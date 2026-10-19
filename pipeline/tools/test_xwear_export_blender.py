"""Blender regression tests in an unsaved independent process, then full clothing export."""
import bpy, importlib.util, json, sys,addon_utils
from pathlib import Path
ROOT=Path('D:/vroidmcp');OUT=ROOT/'projects/whale-maid/xwear-textured-v01'
addon_utils.enable('bl_ext.blender_org.vrm',default_set=True,persistent=False)
exec(compile((ROOT/'tools/export_target_xwear.py').read_text(encoding='utf8'),'export_target_xwear.py','exec'))
spec=importlib.util.spec_from_file_location('direct',ROOT/'blender-addons/vroid_xwear_direct/__init__.py')
direct=importlib.util.module_from_spec(spec);spec.loader.exec_module(direct)
rig=bpy.data.objects['WM_TargetVRoidRig_v01'];obj=bpy.data.objects['FIT_T001__上衣主裙围裙_连体待拆']
results=[]
def rejects(label,fn,expected):
    try:fn()
    except expected:results.append(label)
    else:raise AssertionError('Did not reject '+label)
rejects('overwrite',lambda:direct.export_xwear(OUT/'whale_maid_skirt_sample_v02.xwear',rig,[obj]),FileExistsError)
pb=rig.pose.bones['J_Bip_C_Hips'];old=pb.matrix_basis.copy()
pb.rotation_mode='XYZ';pb.rotation_euler.x=.1
rejects('posed skeleton',lambda:direct.export_xwear(OUT/'must-not-write-posed.xwear',rig,[obj]),ValueError)
pb.matrix_basis=old
mat=obj.data.materials[0];bsdf=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
alpha=bsdf.inputs['Alpha'].default_value;bsdf.inputs['Alpha'].default_value=.5
rejects('transparent material',lambda:direct.material_resource(mat,{},{}),ValueError)
bsdf.inputs['Alpha'].default_value=alpha
link=bsdf.inputs['Base Color'].links[0];source=link.from_socket;dest=link.to_socket
mat.node_tree.links.remove(link);mix=mat.node_tree.nodes.new('ShaderNodeMixRGB');mat.node_tree.links.new(mix.outputs['Color'],dest)
rejects('unsupported procedural material',lambda:direct.material_resource(mat,{},{}),ValueError)
mat.node_tree.nodes.remove(mix);mat.node_tree.links.new(source,dest)
run('whale_maid_fitted_full_v02.xwear',all_parts=True)
(OUT/'exporter-regression.json').write_text(json.dumps({'passed':True,'rejections':results,'full_export':True},indent=2),encoding='utf8')
print('EXPORT_REGRESSION_PASSED '+json.dumps(results))
