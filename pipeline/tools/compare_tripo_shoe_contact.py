"""Actual visible-foot triangle crossings against open original Tripo shoes."""
import argparse, json, sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'VRoid-MCP'))
from vroid_mcp.wear_fit import selected_surface,world,triangles
from measure_exact_contact import tri_tri_intersect

def measure(path):
    data=json.loads(path.read_text(encoding='utf8'));feet,_=selected_surface(data,'feet');rows=[]
    for side in ['L','R']:
        shoe=next(m for m in data['garments'] if m['name'].startswith('FIT_ACCESSORY_Shoe_'+side+'_') and m['name'].endswith(('T004','T005')))
        surface=np.asarray(triangles(shoe,world(shoe)));body=np.asarray(feet[side]['triangles'])
        # Native float BakeMesh can collapse a sub-micron sliver to zero area.
        # Such a triangle has no surface intersection; report it explicitly
        # rather than allowing the strict tri-tri primitive to abort the scan.
        degenerate=np.flatnonzero(np.linalg.norm(np.cross(surface[:,1]-surface[:,0],surface[:,2]-surface[:,0]),axis=1)<1e-18)
        surface=np.delete(surface,degenerate,axis=0);assert len(surface)
        low=surface.min(axis=1);high=surface.max(axis=1);crossings=[]
        for i,tri in enumerate(body):
            indices=np.flatnonzero(np.all(high>=tri.min(axis=0)-1e-8,axis=1)&np.all(low<=tri.max(axis=0)+1e-8,axis=1))
            if any(tri_tri_intersect(tri,surface[j]) for j in indices):crossings.append(i)
        rows.append({'side':side,'visible_foot_vertices':len(feet[side]['points']),'visible_foot_triangles':len(body),'intersecting_visible_foot_triangles':len(crossings),'foot_triangle_indices':crossings,'omitted_zero_area_shoe_triangle_indices':degenerate.tolist()})
    return {'reference':str(path),'frame':data['frame'],'body_occlusion':data.get('base_body_occlusion'),'rows':rows}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result={'before':measure(a.before),'after':measure(a.after),'scope':'Exact triangle crossings in captured native pose. Open original shoe surfaces do not support a closed-solid interior claim. Does not certify foot posture, all animation or art acceptance.'}
    with a.out.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({key:result[key]['rows'] for key in ['before','after']}),flush=True)
