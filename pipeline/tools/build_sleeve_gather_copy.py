import bpy,json,hashlib,importlib.util,argparse,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('sleeve_gather',ROOT/'blender-addons/vroid_xwear_direct/sleeve_gather.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
p=argparse.ArgumentParser();p.add_argument('--profile',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);profile=json.loads(a.profile.read_text(encoding='utf8'))
source=Path(profile['source_blend']);digest=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
assert Path(bpy.data.filepath)==source and digest(source)==profile['source_sha256'] and not a.out.exists() and not a.report.exists()
results=[]
for cuff in profile['cuffs']:
    info=module.inspect_cuff(cuff['mesh'],profile['rig'],cuff['start_bone'],cuff['end_bone'])
    results.append(module.gather_cuff(cuff['mesh'],profile['rig'],profile['body_mesh'],cuff['start_bone'],cuff['end_bone'],info['fingerprint'],**profile['parameters']))
old=bpy.context.preferences.filepaths.save_version
try:
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(a.out.resolve()),copy=True,relative_remap=False,compress=True)
finally:bpy.context.preferences.filepaths.save_version=old
assert a.out.is_file() and digest(source)==profile['source_sha256']
with a.report.open('x',encoding='utf8') as stream:json.dump({'saved':True,'path':str(a.out.resolve()),'sha256':digest(a.out),'source_unchanged':True,'cuffs':results},stream,ensure_ascii=False,indent=2)
print('SLEEVE_GATHER_COPY '+json.dumps(results,ensure_ascii=False))
