"""Freeze a consistent read-only source snapshot for clothing acceptance."""
import hashlib,json,shutil
from pathlib import Path
ROOT=Path('D:/vroidmcp');source=ROOT/'VRoid-MCP';dest=ROOT/'work/clothing-mcp-v17b'
assert not dest.exists()
files=[p for folder in ('vroid_mcp','agent') for p in (source/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc']
before={p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
dest.mkdir()
for p in files:
    q=dest/p.relative_to(source);q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
assert all(hashlib.sha256((source/p).read_bytes()).hexdigest()==h==hashlib.sha256((dest/p).read_bytes()).hexdigest() for p,h in before.items()),'Live source changed while copying; do not use this snapshot'
(dest/'SOURCE_ISOLATION.json').write_text(json.dumps({'source':str(source),'scope':'Read-only frozen MCP server/agent for clothing acceptance. Hair tool development remains in the original checkout.','files':before},indent=2),encoding='utf8')
print(json.dumps({'frozen':True,'files':len(files),'server_root':str(dest)}))
