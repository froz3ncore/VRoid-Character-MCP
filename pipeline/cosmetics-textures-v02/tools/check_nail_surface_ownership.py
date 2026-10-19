"""Independent UV/bone ownership audit; run with the bundled NumPy runtime."""
import json,sys,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'VRoid-MCP'))
from vroid_mcp.texture_mapping import raster_nails
D=ROOT/'projects/whale-maid/diagnostics';mapping=json.loads((D/'nail-targets-native-v05/nail-map.json').read_text());reference=json.loads(Path(mapping['reference']['path']).read_text());record=json.loads((D/'hand-texture-bindings-v01/surface.json').read_text());overlay=json.loads(Path(record['path']).read_text())['meshes'][0]
w=mapping['texture']['width'];h=mapping['texture']['height'];masks=raster_nails(mapping);foot=next(m for m in reference['meshes'] if m['name']=='Foot');foot_uv=np.array(foot['uv0']);tris=foot_uv[np.array(foot['triangles']).reshape(-1,3)]
result={}
for nail in mapping['nails']:
    pixels=np.array(sorted(masks[nail['id']]));points=np.stack([(pixels%w+.5)/w,1-(pixels//w+.5)/h],axis=1);hit=np.zeros(len(points),bool)
    for a,b,c in tris:
        denominator=np.cross(b-a,c-a)
        if abs(denominator)<1e-12:continue
        v=np.cross(points-a,c-a)/denominator;u=np.cross(b-a,points-a)/denominator;hit|=(v>=-1e-9)&(u>=-1e-9)&(u+v<=1+1e-9)
    # Every cap UV vertex must exist in the source BodySkin editable overlay.
    uv=np.array([p for island in nail['islands'] for tri in island['uv_triangles'] for p in tri]);source=np.array(overlay['uv0']);nearest=np.sqrt(((uv[:,None,:]-source[None,:,:])**2).sum(axis=2).min(axis=1)).max()
    result[nail['id']]={'distal_bone':nail['distal_bone'],'foot_uv_overlap_pixels':int(hit.sum()),'pixels':len(pixels),'editable_overlay_uv_vertex_max_error':float(nearest)}
assert all(v['foot_uv_overlap_pixels']==0 and v['editable_overlay_uv_vertex_max_error']<1e-6 for v in result.values()),result
output={'passed':True,'scope':'Actual Hand distal bones and cap UVs correspond to BodySkin overlay; zero Foot surface coverage at all nail-mask pixel centers. This alone does not prove visible color or native canvas orientation.','nails':result}
(D/'nail-targets-native-v05/surface-ownership.json').write_text(json.dumps(output,indent=2),encoding='utf8');print(json.dumps(output,indent=2))
