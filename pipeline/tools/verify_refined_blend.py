"""Reuse source/UV/rig cold checks against the separately saved refined asset."""
from pathlib import Path
path=Path('D:/vroidmcp/tools/verify_target_fit.py')
source=path.read_text(encoding='utf8')
old="OUT=ROOT/'projects/whale-maid/target-fit-v01'"
assert old in source
exec(compile(source.replace(old,"OUT=ROOT/'projects/whale-maid/target-fit-v02'"),str(path),'exec'))
