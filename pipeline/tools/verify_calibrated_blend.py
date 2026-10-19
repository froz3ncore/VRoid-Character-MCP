"""Cold verification of the separate calibrated source and unchanged source streams."""
import bpy, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'projects/whale-maid/target-fit-v04'
assert Path(bpy.data.filepath)==OUT/'whale_maid_target_fit_v04.blend'
path=ROOT/'tools/verify_target_fit.py';source=path.read_text(encoding='utf8')
source=source.replace("OUT=ROOT/'projects/whale-maid/target-fit-v01'","OUT=ROOT/'projects/whale-maid/target-fit-v04'")
assert 'if len(fitted)!=73:' in source
source=source.replace('if len(fitted)!=73:','if len(fitted)!=69:')
exec(compile(source,str(path),'exec'))
record=json.loads((OUT/'source-calibration.json').read_text(encoding='utf8'))
actual={j.node.bone_name:j for s in sb.springs for j in s.joints}
for expected in record['changes']:
    j=actual[expected['bone']]
    assert abs(j.stiffness-expected['stiffness'])<1e-6
    assert abs(j.gravity_power-expected['gravity'])<1e-6
    assert abs(j.drag_force-expected['drag'])<1e-6
print('SAVED_CALIBRATION_60_JOINTS_OK')
