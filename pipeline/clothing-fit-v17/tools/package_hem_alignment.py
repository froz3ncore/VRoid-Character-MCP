"""Cold scope check and XWear package for the live hem alignment copy."""
import hashlib,importlib.util,json,sys
from pathlib import Path
import bpy
from mathutils import Matrix,Vector
ROOT=Path(__file__).resolve().parents[1]
C=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1)))
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def write(p,d):
 with p.open('x',encoding='utf8') as f:json.dump(d,f,ensure_ascii=False,indent=2)
def main():
 source=Path(bpy.data.filepath).resolve();out=source.parent;record=json.loads((out/'live-edit.json').read_text(encoding='utf8'));assert digest(source)==record['copy_sha256'];scope=load('hem_scope',ROOT/'tools/verify_rear_mirror_sources.py');after=scope.read();fitted=[o for o in bpy.data.collections['FITTED_服装工作副本'].all_objects if o.type=='MESH'];assert len(fitted)==97;matrices={o.name:o.matrix_world.copy() for o in fitted};normals={o.name:[tuple(n.vector) for n in o.data.corner_normals] for o in fitted if o.data.has_custom_normals};parts=set(record['parts']);assert len(parts)==40
 bpy.ops.wm.open_mainfile(filepath=record['source']);assert digest(record['source'])==record['source_sha256'];assert scope.read()==after,'Source mesh, skin, UV, images, bones or physical parameters changed';maximum=0.;protected=0.
 for n,actual in matrices.items():
  old=bpy.data.objects[n].matrix_world.copy();expected=old.copy()
  if n in parts:expected.translation+=C.inverted().to_3x3()@Vector((0,record['offset_m'],0))
  error=max(abs(actual[i][j]-expected[i][j]) for i in range(4) for j in range(4));maximum=max(maximum,error)
  if n not in parts:protected=max(protected,error)
 assert maximum<2e-6 and protected<2e-6
 assert all([tuple(n.vector) for n in bpy.data.objects[name].data.corner_normals]==values for name,values in normals.items())
 write(out/'cold-source-check.json',{'passed':True,'candidate':str(source),'candidate_sha256':digest(source),'input':record['source'],'input_sha256':record['source_sha256'],'all_source_coordinates_faces_uv_weights_materials_images_bones_springs_colliders_normals_preserved':True,'moved_original_hem_meshes':40,'protected_meshes':57,'protected_world_matrix_error':protected,'maximum_world_matrix_error':maximum,'offset_mm':record['offset_mm']})
 bpy.ops.wm.open_mainfile(filepath=str(source));rig=bpy.data.objects['WM_TargetVRoidRig_v01'];rig.data.vrm_addon_extension.spring_bone1.enable_animation=False
 for p in rig.pose.bones:p.matrix_basis.identity()
 bpy.context.view_layer.update();package=out/'whale_maid_hem_align_v22.xwear';exporter=load('hem_export',ROOT/'blender-addons/vroid_xwear_direct/__init__.py');result=exporter.export_xwear(package,rig,[o for o in bpy.data.collections['FITTED_服装工作副本'].all_objects if o.type=='MESH'],item_name=package.stem,author='Local creator',coordinate_matrix=C)
 write(package.with_suffix('.xwear.json'),result);write(out/'package.json',{'source':str(source),'source_sha256':digest(source),'package':str(package),'package_sha256':digest(package),'meshes':len(result['meshes']),'triangles':sum(m['triangles'] for m in result['meshes']),'verification_meshes':record['parts'],'coordinate_meshes':[],'weight_meshes':[],'object_transform_meshes':record['parts'],'offset_mm':record['offset_mm'],'native_acceptance':False});assert digest(source)==record['copy_sha256'];print(json.dumps({'cold_passed':True,'moved_meshes':40,'protected_meshes':57,'meshes':len(result['meshes']),'triangles':sum(m['triangles'] for m in result['meshes'])}),flush=True)
if __name__=='__main__':main()
