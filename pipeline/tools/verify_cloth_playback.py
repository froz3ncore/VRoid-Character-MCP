import bpy
import json
from pathlib import Path
OUT=Path(r'D:\vroidmcp\projects\whale-maid\tripo-source\cloth-springs-v01')
poses=json.loads((OUT/'simulated_pose_cache.json').read_text())
rig=bpy.data.objects['WM_ClothSpringRig_v01'];maximum=0
for f in [1,30,60,90,121]:
    bpy.context.scene.frame_set(f)
    for name,quat in poses[str(f)].items():
        maximum=max(maximum,max(abs(a-b) for a,b in zip(rig.pose.bones[name].rotation_quaternion,quat)))
result={'success':maximum<1e-5,'file':bpy.data.filepath,'checked_frames':[1,30,60,90,121],'max_quaternion_component_error':maximum,'VRM_addon_required_for_baked_playback':False}
(OUT/'playback_validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print('BAKED_PLAYBACK_VALIDATION '+json.dumps(result))
if not result['success']:raise RuntimeError('Baked playback does not match solver cache')
