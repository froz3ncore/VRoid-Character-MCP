"""Package the independently implemented Blender addon; no vendor binaries."""
import hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];source=ROOT/'blender-addons/vroid_xwear_direct/__init__.py'
path=ROOT/'blender-addons/vroid_xwear_direct-0.2.0.zip'
with zipfile.ZipFile(path,'x',zipfile.ZIP_DEFLATED) as archive:
    archive.write(source,'vroid_xwear_direct/__init__.py')
with zipfile.ZipFile(path) as archive:assert archive.testzip() is None and archive.read('vroid_xwear_direct/__init__.py')==source.read_bytes()
report={'version':'0.2.0','path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
    'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
path.with_suffix('.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
