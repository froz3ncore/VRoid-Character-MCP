"""Cold-load actual Blender data, addon configuration and source integrity."""
import bpy
import addon_utils
import json
import hashlib
from pathlib import Path

BASE=Path(r'D:\vroidmcp\projects\whale-maid\tripo-source')
OUT=BASE/'cloth-springs-v01'
# Transient preferences entry required by this add-on; never save user preferences.
addon_utils.enable('bl_ext.blender_org.vrm',default_set=True,persistent=False)
assert hasattr(bpy.types.Armature,'vrm_addon_extension'),'VRM addon unavailable'
ns={'__name__':'cloth_spring_verification'}
exec(compile(Path(r'D:\vroidmcp\tools\blender_cloth_springs.py').read_text(encoding='utf-8'),'blender_cloth_springs.py','exec'),ns)
status=ns['inspect_status']()
plan=json.loads((OUT/'cloth_spring_plan.json').read_text(encoding='utf-8'))
source=json.loads((BASE/'parts_manifest_v01.json').read_text(encoding='utf-8'))
errors=[]
if not status['ok'] or status['bones']!=71 or status['spring_chains']!=14 or status['colliders']!=3 or status['bound_meshes']!=50:errors.append('configuration or weights mismatch')
rig=bpy.data.objects[ns['RIG']];spring=rig.data.vrm_addon_extension.spring_bone1
if not spring.enable_animation:errors.append('live solver not enabled in primary file')
ns['reset_pose']()
mesh_digest=ns['helpers']()['mesh_digest']
objects={o.get('source_part_id'):o for o in bpy.context.scene.objects if o.type=='MESH'}
if len(objects)!=151:errors.append('source mesh count changed')
images=set()
for row in source['parts']:
    o=objects[row['source_id']]
    if mesh_digest(o)!=row['source_digest']:errors.append('geometry/UV/rest transform changed:'+o.name)
    found={n.image for m in o.data.materials if m and m.use_nodes for n in m.node_tree.nodes if n.type=='TEX_IMAGE' and n.image}
    images.update(found)
    hashes={im['name']:im['packed_sha256'] for im in row['images']}
    if not all(im.packed_file and hashlib.sha256(im.packed_file.data).hexdigest()==hashes.get(im.name) for im in found):errors.append('texture changed:'+o.name)
    if len(found)!=len(hashes):errors.append('texture reference missing:'+o.name)
for actual,expected in zip(spring.springs,plan['chains']):
    if [j.node.bone_name for j in actual.joints]!=expected['bones']:errors.append('chain identity mismatch')
    if not actual.collider_groups:errors.append('missing collision group')
    for joint in actual.joints:
        for key in ['stiffness','drag_force','gravity_power','hit_radius']:
            if abs(getattr(joint,key)-expected[key])>1e-6:errors.append('physics parameter mismatch:'+actual.vrm_name)
for actual,expected in zip(spring.colliders,plan['colliders']):
    shape=actual.shape.sphere if expected['type']=='sphere' else actual.shape.capsule
    if abs(shape.radius-expected['radius'])>1e-6 or max(abs(a-b) for a,b in zip(shape.offset,expected['offset']))>1e-6:errors.append('temporary collider test was not restored')
    if expected['tail'] is not None and max(abs(a-b) for a,b in zip(shape.tail,expected['tail']))>1e-6:errors.append('capsule tail changed')
groups={g.uuid for g in spring.collider_groups}
colliders={c.uuid for c in spring.colliders}
if any(r.collider_uuid not in colliders for g in spring.collider_groups for r in g.colliders):errors.append('invalid collider reference')
if any(r.collider_group_uuid not in groups for s in spring.springs for r in s.collider_groups):errors.append('invalid collider group reference')
if len(images)!=151:errors.append('image count mismatch')
result={'success':not errors,'errors':errors,'status':status,'source_mesh_uv_rest_transform_unchanged':not errors,'source_packed_image_bytes_unchanged':not errors,'scope':'Saved Blender clothing spring configuration only; no XWear/VRM/Godot acceptance'}
(OUT/'cold_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print('CLOTH_COLD_VALIDATION '+json.dumps(result,ensure_ascii=False))
if errors:raise RuntimeError(str(errors))
ns['OUT']=OUT/'cold-solver-recheck';ns['OUT'].mkdir(exist_ok=True)
physics=ns['review']()
if not physics['success']:raise RuntimeError('Cold-loaded solver failed')
print('COLD_LOADED_SOLVER_PASSED')
