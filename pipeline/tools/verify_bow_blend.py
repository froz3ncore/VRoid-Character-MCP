"""Cold source/skin/UV/rig validation for the 69-part bow reconstruction."""
from pathlib import Path
path=Path('D:/vroidmcp/tools/verify_target_fit.py');source=path.read_text(encoding='utf8')
source=source.replace("OUT=ROOT/'projects/whale-maid/target-fit-v01'","OUT=ROOT/'projects/whale-maid/target-fit-v03'")
assert "if len(fitted)!=73:" in source
source=source.replace("if len(fitted)!=73:","if len(fitted)!=69:")
exec(compile(source,str(path),'exec'))
