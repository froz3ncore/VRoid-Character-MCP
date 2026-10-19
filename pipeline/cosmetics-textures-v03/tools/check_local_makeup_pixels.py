"""Independent Pillow/NumPy checks of native brush pixels and material locality."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'projects/whale-maid/diagnostics/local-makeup-native-v02'
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def rgba(p):return np.asarray(Image.open(p).convert('RGBA'))
report={'parts':{},'rendered_locality':{}}
for part in ('Cheek','MouthLine','Eyelid'):
    mask=rgba(read(D/(part+'-mask.json'))['mask_path'])[:,:,3]>0
    preview=rgba(read(D/(part+'-preview.json'))['path']);native=rgba(read(D/(part+'-native-layer.json'))['path']);cold=rgba(read(D/(part+'-cold-layer.json'))['path'])
    active=preview[:,:,3]>0
    result={'input_native_rgba_equal':bool(np.array_equal(preview,native)),'native_cold_rgba_equal':bool(np.array_equal(native,cold)),'painted_pixels':int(active.sum()),'paint_outside_mask_pixels':int((active&~mask).sum())}
    assert result['input_native_rgba_equal'] and result['native_cold_rgba_equal'] and result['paint_outside_mask_pixels']==0
    report['parts'][part]=result
for part,before_record,after_record in [('MouthLine','Cheek-rendered-skin.json','MouthLine-rendered-skin.json'),('Eyelid','eyelid-material-before.json','Eyelid-rendered-eyelid.json')]:
    before=rgba(read(D/before_record)['path']);after=rgba(read(D/after_record)['path']);mask=rgba(read(D/(part+'-mask.json'))['mask_path'])[:,:,3]>0
    delta=np.max(np.abs(before.astype(int)-after.astype(int)),axis=2)
    assert delta.shape==mask.shape
    result={'changed_pixels':int((delta>0).sum()),'changed_outside_mask_pixels':int(((delta>0)&~mask).sum()),'maximum_channel_change':int(delta.max())};report['rendered_locality'][part]=result
    assert result['changed_pixels']>0 and result['changed_outside_mask_pixels']==0
(D/'pixel-acceptance.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2))
