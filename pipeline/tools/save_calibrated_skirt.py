"""Save a separate calibrated source, preserving geometry, UVs, skin and images."""
import bpy, addon_utils, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'projects/whale-maid/target-fit-v04'
addon_utils.enable('bl_ext.blender_org.vrm',default_set=True,persistent=False)
source=ROOT/'projects/whale-maid/target-fit-v03/whale_maid_target_fit_v03.blend'
target=OUT/'whale_maid_target_fit_v04.blend'
resume='--export-only' in sys.argv
assert Path(bpy.data.filepath)==(target if resume else source)
if not resume:assert not target.exists()
source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
rig=bpy.data.objects['WM_TargetVRoidRig_v01'];sb=rig.data.vrm_addon_extension.spring_bone1
def streams():
    result={}
    for obj in bpy.data.objects:
        if obj.type!='MESH':continue
        data={'positions':[list(v.co) for v in obj.data.vertices],
              'weights':[[(g.group,g.weight) for g in v.groups] for v in obj.data.vertices],
              'polygons':[list(p.vertices) for p in obj.data.polygons],
              'uv':[[list(v.uv) for v in layer.data] for layer in obj.data.uv_layers]}
        result[obj.name]=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
    result.update({'image:'+im.name:hashlib.sha256(bytes(im.packed_file.data)).hexdigest() for im in bpy.data.images if im.packed_file})
    return result
before=streams();changes=[]
for spring in sb.springs:
    if not spring.vrm_name.startswith('Skirt_'):continue
    for segment,joint in enumerate(spring.joints):
        joint.stiffness=.65 if segment<2 else .12
        joint.gravity_power=.12 if segment<2 else .28
        joint.drag_force=.65
        changes.append({'bone':joint.node.bone_name,'stiffness':joint.stiffness,'gravity':joint.gravity_power,'drag':joint.drag_force})
assert len(changes)==60 and streams()==before
sb.enable_animation=False;bpy.context.scene.frame_set(1)
for pose in rig.pose.bones:pose.matrix_basis.identity()
bpy.context.view_layer.update()
sb.enable_animation=True
if not resume:bpy.ops.wm.save_as_mainfile(filepath=str(target),compress=True,relative_remap=False)
final=OUT/'final-wear';final.mkdir(exist_ok=resume)
assert not (final/'whale_maid_calibrated_v04.xwear').exists()
exporter={'__name__':'calibrated_export'}
exec(compile((ROOT/'tools/export_target_xwear.py').read_text(encoding='utf8'),'export_target_xwear.py','exec'),exporter)
exporter['OUT']=final
try:
    sb.enable_animation=False
    for pose in rig.pose.bones:pose.matrix_basis.identity()
    bpy.context.view_layer.update()
    exporter['run']('whale_maid_calibrated_v04.xwear',all_parts=True)
finally:sb.enable_animation=True
assert streams()==before and hashlib.sha256(source.read_bytes()).hexdigest()==source_hash
(OUT/'source-calibration.json').write_text(json.dumps({'source':str(source),'source_sha256':source_hash,'target':str(target),'target_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'geometry_uv_skin_images_unchanged':True,'streams':before,'changes':changes},ensure_ascii=False,indent=2),encoding='utf8')
print('CALIBRATED_SOURCE_OK',str(target))
