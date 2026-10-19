"""Refresh named source-only snapshot files and verify the whole manifest."""
import argparse,hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];PIPELINE=ROOT/'VRoid-MCP/pipeline'
def main():
    parser=argparse.ArgumentParser();parser.add_argument('paths',nargs='+');args=parser.parse_args()
    manifest_path=PIPELINE/'source-snapshot.json';manifest=json.loads(manifest_path.read_text(encoding='utf8'))
    files={r['path']:r for r in manifest['files']}
    for value in args.paths:
        relative=Path(value)
        if relative.is_absolute() or '..' in relative.parts or relative.parts[0] not in ('tools','blender-addons') or relative.suffix!='.py':raise ValueError('Only explicit Python source files in pipeline roots')
        source=ROOT/relative;destination=PIPELINE/relative;raw=source.read_bytes()
        destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)
        files[relative.as_posix()]={'path':relative.as_posix(),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
            'git_lf_sha256':hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()}
    manifest['files']=[files[k] for k in sorted(files)]
    for row in manifest['files']:
        raw=(PIPELINE/row['path']).read_bytes()
        assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
        assert hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()==row['git_lf_sha256']
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'verified_sources':len(files),'refreshed':len(args.paths)}))
if __name__=='__main__':main()
