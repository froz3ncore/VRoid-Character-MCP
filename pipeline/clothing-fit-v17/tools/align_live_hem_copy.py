"""Lift only existing hem parts in the user's live Blender; preserve a full input copy."""
import bpy,json,hashlib,statistics
from pathlib import Path
from mathutils import Matrix,Vector
ROOT=Path('D:/vroidmcp/projects/whale-maid/accessory-refinement-v02');out=ROOT/'hem-align-v22'
assert not out.exists();assert bpy.context.mode=='OBJECT'
C=Matrix(((0,-1,0,0),(0,0,1,0),(1,0,0,0),(0,0,0,1)))
bpy.context.view_layer.update();fitted=[o for o in bpy.data.collections['FITTED_服装工作副本'].all_objects if o.type=='MESH'];assert len(fitted)==97
base=json.loads((ROOT/'chest-skirt-inspection-v17/source-main.json').read_text(encoding='utf8'));main=bpy.data.objects[base['name']];old=base['co'];assert len(main.data.vertices)==len(old)
points=[C@main.matrix_world@v.co for v in main.data.vertices];ids=[i for i,p in enumerate(old) if p[1]<.85];dy=[points[i].y-old[i][1] for i in ids];offset=statistics.median(dy)
assert .04<offset<.08 and max(dy)-min(dy)<1e-6,(offset,max(dy)-min(dy))
parts=[]
for obj in fitted:
 if not obj.name.startswith('FIT_T') or obj==main:continue
 p=[C@obj.matrix_world@v.co for v in obj.data.vertices]
 if min(q.y for q in p)>.30 and max(q.y for q in p)<1.015:parts.append(obj)
assert len(parts)==40,len(parts)
protected=[o for o in fitted if o not in parts]
local={o.name:[tuple(v.co) for v in o.data.vertices] for o in fitted};normal={o.name:[tuple(n.vector) for n in o.data.corner_normals] for o in fitted if o.data.has_custom_normals}
world={o.name:[C@o.matrix_world@v.co for v in o.data.vertices] for o in fitted};matrices={o.name:[list(r) for r in o.matrix_world] for o in parts};live=bpy.data.filepath
out.mkdir();initial=out/'input_user_current.blend';bpy.ops.wm.save_as_mainfile(filepath=str(initial),copy=True,compress=True,relative_remap=False);assert bpy.data.filepath==live
plan={'user_request':'我忘记调裙边了，你帮我调一下','live_file':live,'source':str(initial),'source_sha256':hashlib.sha256(initial.read_bytes()).hexdigest(),'accepted_upper_source':str(ROOT/'manual-upper-fit-v20/whale_maid_manual_upper_fit_v20.blend'),'offset_m':offset,'offset_mm':offset*1000,'parts':list(matrices),'before_world_matrices':matrices,'protected_meshes':len(protected),'method':'Uniform world translation of the 40 original independent skirt ruffles and lower-skirt ornaments to match the measured main-skirt lift. Main garment and all local mesh data remain unchanged.'}
(out/'edit-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf8')
delta=C.inverted().to_3x3()@Vector((0,offset,0))
for obj in parts:
 m=obj.matrix_world.copy();m.translation+=delta;obj.matrix_world=m
bpy.context.view_layer.update();maximum=0.;protected_error=0.
for obj in fitted:
 assert [tuple(v.co) for v in obj.data.vertices]==local[obj.name],obj.name
 if obj.name in normal:assert [tuple(n.vector) for n in obj.data.corner_normals]==normal[obj.name],obj.name
 for v,p in zip(obj.data.vertices,world[obj.name]):
  actual=C@obj.matrix_world@v.co;expected=p+(Vector((0,offset,0)) if obj in parts else Vector());error=(actual-expected).length
  if obj in parts:maximum=max(maximum,error)
  else:protected_error=max(protected_error,error)
assert maximum<2e-6 and protected_error<2e-6,(maximum,protected_error)
target=out/'whale_maid_hem_align_v22.blend';bpy.ops.wm.save_as_mainfile(filepath=str(target),copy=True,compress=True,relative_remap=False);assert bpy.data.filepath==live
plan.update(copy=str(target),copy_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),maximum_rigid_translation_error_mm=maximum*1000,protected_mesh_world_error_mm=protected_error*1000,all_mesh_local_coordinates_and_custom_normals_preserved=True,protected_meshes_unchanged=True,live_blender_keeps_manual_file=True,originals_not_overwritten=True)
(out/'live-edit.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in plan.items() if k not in ('parts','before_world_matrices')},ensure_ascii=False))
