"""Compare actual native skin compositions before/after the diagnostic overlay."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'projects/whale-maid/diagnostics/nail-visibility-v01'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def rgba(path):return np.asarray(Image.open(path).convert('RGBA'))
a=rgba(read(D/'rendered-control.json')['path']);b=rgba(read(D/'rendered-Hand.json')['path']);mapping=read(ROOT/'projects/whale-maid/diagnostics/nail-targets-baked-color-v02/map-export.json')
mask=np.zeros(a.shape[:2],bool)
for item in mapping['masks']:mask|=rgba(item['path'])[:,:,3]>0
delta=np.max(np.abs(a.astype(int)-b.astype(int)),axis=2)
report={'changed_pixels':int((delta>0).sum()),'changed_outside_nail_masks':int(((delta>0)&~mask).sum()),'mask_pixels':int(mask.sum()),'maximum_channel_delta':int(delta.max()),'per_nail':{}}
for item in mapping['masks']:
    part=rgba(item['path'])[:,:,3]>0
    report['per_nail'][item['nail_id']]={'changed_pixels':int(((delta>0)&part).sum()),'total':int(part.sum())}
(D/'texture-composition-diff.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report,indent=2))
