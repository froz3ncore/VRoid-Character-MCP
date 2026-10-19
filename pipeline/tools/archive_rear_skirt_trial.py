"""Preserve an unresolved rear-skirt trial, sources and evidence in a checked ZIP.

Original files stay in place. Does not archive the chat or modify system state.
"""
import argparse
import hashlib
import json
import os
import subprocess
import zipfile
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EXPERIMENT=ROOT/'projects/whale-maid/rear-skirt-contact-v03-20261017'
EXCLUDE={'.godot','.git','__pycache__','.venv','node_modules'}


def collect(paths):
    files={}
    for source in paths:
        assert source.resolve().is_relative_to(ROOT)
        if source.is_file():
            files[source.relative_to(ROOT).as_posix()]=source
            continue
        assert source.is_dir(),source
        for parent,dirs,names in os.walk(source,followlinks=False):
            dirs[:]=[d for d in dirs if d not in EXCLUDE and not (Path(parent)/d).is_symlink()]
            for name in names:
                path=Path(parent)/name
                if path.is_symlink():raise ValueError('Symbolic source requires explicit preservation: '+str(path))
                assert path.resolve().is_relative_to(ROOT)
                files[path.relative_to(ROOT).as_posix()]=path
    return dict(sorted(files.items()))


def main(a):
    decision=json.loads(a.decision.read_text(encoding='utf8'))
    assert decision['status']=='archived-unresolved' and decision['adopted'] is False
    assert decision['user_requested_pause_after_final_round'] is True
    out=a.out.resolve()
    assert out.is_relative_to(ROOT/'archives') and not out.exists()
    paths=[EXPERIMENT,ROOT/'projects/whale-maid/sleeve-cuff-v01',
        ROOT/'projects/whale-maid/clean-wear-v01',ROOT/'tools',ROOT/'blender-addons/vroid_xwear_direct',
        ROOT/'docs',ROOT/'AGENTS.md']
    for part in ('agent','vroid_mcp','tests','pipeline','README.md','README.zh-TW.md','pyproject.toml','launch.py'):
        path=ROOT/'VRoid-MCP'/part
        if path.exists():paths.append(path)
    for relative in ('work/exact-contact-compare-20261017/pred-D2-nudge.report.json',
                     'work/contact-geometry-crosscheck-20261017.json','work/vroid-closet-key-backup-20261017.reg'):
        path=ROOT/relative
        if path.exists():paths.append(path)
    paths.extend((ROOT/'work').glob('long-hem-f-*.log'))
    for row in decision.get('runtime_attempts',[]):
        path=ROOT/row['path']
        if path.exists():paths.append(path)
    # Preserve the exact native inputs addressed by acceptance records as well.
    for record in (ROOT/'projects/whale-maid/clean-wear-v01/clean-base-acceptance.json',
                   ROOT/'projects/whale-maid/sleeve-cuff-v01/final-wear/refined-wear-acceptance.json'):
        paths.append(Path(json.loads(record.read_text(encoding='utf8'))['save']['path']))
    files=collect(paths)
    out.mkdir(parents=True)
    partial=out/'rear-skirt-resume.zip.partial'
    records=[]
    with zipfile.ZipFile(partial,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as archive:
        for index,(relative,path) in enumerate(files.items()):
            before=path.stat();digest=hashlib.sha256();size=0
            with path.open('rb') as source,archive.open('workspace/'+relative,'w',force_zip64=True) as target:
                while chunk:=source.read(1024*1024):
                    digest.update(chunk);size+=len(chunk);target.write(chunk)
            after=path.stat()
            assert (before.st_mtime_ns,before.st_size)==(after.st_mtime_ns,after.st_size),(path,'changed during archive')
            records.append({'path':relative,'bytes':size,'sha256':digest.hexdigest()})
            if index%250==0:print(json.dumps({'packed_files':index+1,'total_files':len(files)}),flush=True)
        manifest={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'archived-unresolved',
            'workspace':str(ROOT),'originals_preserved_in_place':True,'excluded_cache_directories':sorted(EXCLUDE),
            'decision':str(a.decision.resolve()),'files':records,
            'git_head':subprocess.check_output(['git','-C',str(ROOT/'VRoid-MCP'),'rev-parse','HEAD'],text=True).strip(),
            'git_status':subprocess.check_output(['git','-C',str(ROOT/'VRoid-MCP'),'status','--porcelain'],text=True),
            'scope':'Experimental rear-skirt sources/evidence, formal sleeve source, reusable code and exact native inputs. Original Tripo assets outside this scope remain in the workspace.'}
        archive.writestr('ARCHIVE-MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    # Independently read every packed file and match its SHA256 to the manifest.
    with zipfile.ZipFile(partial) as archive:
        for index,row in enumerate(records):
            digest=hashlib.sha256()
            with archive.open('workspace/'+row['path']) as source:
                while chunk:=source.read(1024*1024):digest.update(chunk)
            assert digest.hexdigest()==row['sha256'],row['path']
            if index%500==0:print(json.dumps({'verified_files':index+1,'total_files':len(records)}),flush=True)
    target=out/'rear-skirt-resume.zip'
    assert not target.exists()
    partial.replace(target)
    digest=hashlib.sha256()
    with target.open('rb') as stream:
        while chunk:=stream.read(1024*1024):digest.update(chunk)
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    result={'archive':str(target),'sha256':digest.hexdigest(),'bytes':target.stat().st_size,
        'files_verified':len(records),'source_bytes':sum(r['bytes'] for r in records),
        'all_entries_sha256_verified':True,'originals_preserved_in_place':True,
        'status':'archived-unresolved','chat_archived':False}
    (out/'archive-acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--decision',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    main(parser.parse_args())
