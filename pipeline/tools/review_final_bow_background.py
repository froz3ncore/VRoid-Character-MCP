"""Read saved source in a disposable Blender, preserving source and prior evidence."""
import bpy,addon_utils,hashlib,json
from pathlib import Path
ROOT=Path('D:/vroidmcp');source=Path(bpy.data.filepath);before=hashlib.sha256(source.read_bytes()).hexdigest()
OUT=ROOT/'projects/whale-maid/target-fit-v03/final-pose-check'
if OUT.exists():raise FileExistsError('Do not overwrite pose evidence')
OUT.mkdir()
addon_utils.enable('bl_ext.blender_org.vrm',default_set=True,persistent=False)
ns={'__name__':'background_pose_review'};exec((ROOT/'tools/review_target_cloth.py').read_text(encoding='utf8'),ns);ns['OUT']=OUT
result=ns['review'](render=False)
assert hashlib.sha256(source.read_bytes()).hexdigest()==before
(OUT/'source-preserved.json').write_text(json.dumps({'path':str(source),'sha256':before,'unchanged':True,'live_blender_untouched':True}),encoding='utf8')
if not result['all_screening_thresholds_pass']:raise RuntimeError('Pose screening needs fitting review')
