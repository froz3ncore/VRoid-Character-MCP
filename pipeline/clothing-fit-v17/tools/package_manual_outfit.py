"""Cold audit/package of the user's approved live Blender copy. Never edits source."""
import argparse,hashlib,importlib.util,json,sys
from pathlib import Path
import bpy,numpy as np
from mathutils import Matrix,Vector
ROOT=Path(__file__).resolve().parents[1]
C=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1)))
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def write(p,value):
 with p.open('x',encoding='utf8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
def main(a):
 source=Path(bpy.data.filepath).resolve();out=source.parent;freeze=json.loads((out/'live-source-freeze.json').read_text(encoding='utf8'));assert digest(source)==freeze['copy_sha256'];scope=load('manual_outfit_scope',ROOT/'tools/verify_rear_mirror_sources.py')
 fitted=[o for o in bpy.data.collections['FITTED_服装工作副本'].all_objects if o.type=='MESH'];assert len(fitted)==97
 before=scope.read();matrices={o.name:[list(r) for r in o.matrix_world] for o in fitted};rig=bpy.data.objects['WM_TargetVRoidRig_v01'];assert not freeze['nonidentity_pose_bones'];rig.data.vrm_addon_extension.spring_bone1.enable_animation=False;bpy.context.view_layer.update();deps=bpy.context.evaluated_depsgraph_get();rows=[]
 for o in fitted:
  evaluated=o.evaluated_get(deps);mesh=evaluated.to_mesh()
  try:
   assert len(mesh.vertices)==len(o.data.vertices),(o.name,'evaluated topology changed')
   raw=np.asarray([list(C@o.matrix_world@v.co) for v in o.data.vertices]);actual=np.asarray([list(C@evaluated.matrix_world@v.co) for v in mesh.vertices]);delta=np.linalg.norm(actual-raw,axis=1)
   rows.append({'name':o.name,'vertices':len(raw),'visible_vs_raw_maximum_mm':float(max(delta))*1000,'visible_bounds':np.array([actual.min(0),actual.max(0)]).tolist()})
  finally:evaluated.to_mesh_clear()
 report={'source':str(source),'source_sha256':digest(source),'meshes':rows,'maximum_visible_vs_raw_mm':max(r['visible_vs_raw_maximum_mm'] for r in rows),'source_unchanged':True}
 if a.export:
  assert report['maximum_visible_vs_raw_mm']<.002,'Raw exporter differs from approved visible mesh; preserve source and resolve binding before native import.'
  package=out/'whale_maid_manual_upper_fit_v20.xwear';assert not package.exists();exporter=load('manual_outfit_exporter',ROOT/'blender-addons/vroid_xwear_direct/__init__.py');result=exporter.export_xwear(package,rig,fitted,item_name=package.stem,author='Local creator',coordinate_matrix=C);write(package.with_suffix('.xwear.json'),result);write(out/'package.json',{'source':str(source),'source_sha256':digest(source),'package':str(package),'package_sha256':digest(package),'meshes':len(result['meshes']),'triangles':sum(m['triangles'] for m in result['meshes']),'source_not_modified':True,'visible_geometry_matches_raw':True});assert digest(source)==freeze['copy_sha256'];print(json.dumps({'packaged':True,'meshes':97,'triangles':sum(m['triangles'] for m in result['meshes'])}),flush=True);return
 baseline=ROOT/'projects/whale-maid/accessory-refinement-v02/white-bow-v16b/whale_maid_white_bow_v16b.blend';bpy.ops.wm.open_mainfile(filepath=str(baseline));old=scope.read();assert digest(baseline)=='1c1884adff3353f5c3e71d25b10629e4218df2698ceaa7f1b9e5a6c0205a36c3'
 assert old['meshes'].keys()==before['meshes'].keys() and old['weights']==before['weights']
 for key in old:
  if key not in ('meshes','weights'):assert old[key]==before[key],key
 changes=[]
 for name,value in before['meshes'].items():
  previous=old['meshes'][name];assert {k:v for k,v in value.items() if k!='co'}=={k:v for k,v in previous.items() if k!='co'},name
  if value['co']!=previous['co']:changes.append(name)
 matrix_changes=[]
 for name,value in matrices.items():
  if value!=[list(r) for r in bpy.data.objects[name].matrix_world]:matrix_changes.append(name)
 report.update(passed=True,source_topology_uv_weights_material_assignments_images_bones_physics_preserved=True,changed_mesh_coordinates=changes,changed_object_world_transforms=matrix_changes,baseline=str(baseline));write(out/'cold-source-check.json',report);assert digest(source)==freeze['copy_sha256'];print(json.dumps({'cold_passed':True,'changed_coordinate_meshes':changes,'changed_world_transforms':matrix_changes,'visible_vs_raw_maximum_mm':report['maximum_visible_vs_raw_mm']}),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--export',action='store_true');main(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
