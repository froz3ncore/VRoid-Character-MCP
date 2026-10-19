import bpy,json,hashlib,importlib.util,argparse,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('skirt_contact',ROOT/'blender-addons/vroid_xwear_direct/skirt_contact.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
spec=importlib.util.spec_from_file_location('fit',ROOT/'blender-addons/vroid_xwear_direct/fit.py')
fit=importlib.util.module_from_spec(spec);spec.loader.exec_module(fit)
p=argparse.ArgumentParser();p.add_argument('--profile',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);profile=json.loads(a.profile.read_text(encoding='utf8'))
source=Path(profile['source_blend']);assert Path(bpy.data.filepath)==source and fit.digest(source)==profile['source_sha256']
assert not a.out.exists() and not a.report.exists()
before={o.name:fit.fingerprint(o) for o in bpy.data.objects if o.type=='MESH'}
result=module.configure(profile)
assert {o.name:fit.fingerprint(o) for o in bpy.data.objects if o.type=='MESH'}==before
previous=bpy.context.preferences.filepaths.save_version
try:
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(a.out.resolve()),copy=True,relative_remap=False,compress=True)
finally:bpy.context.preferences.filepaths.save_version=previous
assert fit.digest(source)==profile['source_sha256'] and a.out.is_file()
result.update(saved=True,path=str(a.out.resolve()),sha256=fit.digest(a.out),source_unchanged=True,all_meshes_unchanged=True)
with a.report.open('x',encoding='utf8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
print('REAR_CONTACT_BUILD '+json.dumps(result,ensure_ascii=False))
