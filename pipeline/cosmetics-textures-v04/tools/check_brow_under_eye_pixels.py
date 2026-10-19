"""Independent Pillow/NumPy pixel check of native layers and actual rendered atlases."""
import argparse,json
from pathlib import Path
import numpy as np
from PIL import Image
def rgba(path):return np.asarray(Image.open(path).convert('RGBA'))
def main(folder):
 results={}
 for part in ('Eyebrow','FaceSkin'):
  mask=rgba(folder/(part+'-mask.png'))[:,:,3]>0;overlay=rgba(folder/(part+'-overlay.png'));native=rgba(folder/(part+'-native-layer.png'))
  record=json.loads((folder/(part+'-cold-layer.json')).read_text(encoding='utf8'));cold=rgba(record['path'])
  before=rgba(folder/(part+'-rendered-before.png'));after=rgba(folder/(part+'-rendered-after.png'));cold_atlas=rgba(folder/(part+'-cold-rendered.png'))
  changed=np.any(before!=after,axis=2)
  assert overlay.shape==native.shape==cold.shape and np.array_equal(overlay,native) and np.array_equal(native,cold)
  assert changed.shape==mask.shape and changed.sum()>0 and not changed[~mask].any() and np.array_equal(after,cold_atlas)
  assert not (overlay[:,:,3][~mask]>0).any()
  results[part]={'painted_pixels':int((overlay[:,:,3]>0).sum()),'rendered_changed_pixels':int(changed.sum()),'rendered_changed_outside_mask':int(changed[~mask].sum()),'paint_outside_mask':int((overlay[:,:,3][~mask]>0).sum()),'input_native_cold_rgba_equal':True,'rendered_cold_rgba_equal':True}
 (folder/'pixel-acceptance.json').write_text(json.dumps({'passed':True,'parts':results},indent=2),encoding='utf8');print(json.dumps(results))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('folder',type=Path);main(p.parse_args().folder)
