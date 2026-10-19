"""Physical app/profile isolation; never writes to the other development lab."""
import hashlib,json,shutil
from pathlib import Path
ROOT=Path('D:/vroidmcp');source=ROOT/'lab-test';lab=ROOT/'lab-clothing-fit-v17';out=ROOT/'projects/whale-maid/accessory-refinement-v02/chest-skirt-v17b'
assert not lab.exists();lab.mkdir();shutil.copytree(source/'app',lab/'app');(lab/'saves').mkdir()
manifest=json.loads((source/'source-manifest.json').read_text(encoding='utf8'));checks=[]
for r in manifest:
    p=lab/'app'/r['path'];assert p.stat().st_size==r['size'] and hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256'];checks.append(r)
(lab/'source-manifest.json').write_text(json.dumps(checks,indent=2),encoding='utf8')
edit=json.loads((out/'refined-wear-edit.json').read_text(encoding='utf8'));basefile=ROOT/'projects/whale-maid/accessory-refinement-v02/tripo-shoe-rigid-v12/high-heel-base-record.json';base=json.loads(basefile.read_text(encoding='utf8'))
for s in (edit['save'],base['save']):
    p=Path(s['path']);assert hashlib.sha256(p.read_bytes()).hexdigest()==s['sha256'];q=lab/'saves'/p.name;shutil.copy2(p,q);assert hashlib.sha256(q.read_bytes()).hexdigest()==s['sha256']
base['original_save']=base['save'].copy();base['save']['path']=str(lab/'saves'/Path(base['save']['path']).name);base['relocation_only']=True
(out/'isolated-base-record.json').write_text(json.dumps(base,ensure_ascii=False,indent=2),encoding='utf8')
record={'physical_lab':str(lab),'physical_app_files_verified':len(checks),'source_lab_read_only':str(source),'source_clothing_saved_xroid':edit['save'],'frozen_server':str(ROOT/'work/clothing-mcp-v17b'),'profile_fresh':True,'hair_development_untouched':True}
(out/'TEST_ISOLATION.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({'isolated_lab_ready':True,'app_files':len(checks)}))
