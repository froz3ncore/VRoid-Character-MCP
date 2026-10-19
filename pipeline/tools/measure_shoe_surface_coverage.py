"""Compare outward-ray coverage on intended covered native foot regions.

Open insteps are excluded. These are directional surface probes, not a closed
volume penetration verdict or a visual/high-heel acceptance certificate.
"""
import argparse,json,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'VRoid-MCP'))
from vroid_mcp.wear_fit import Surface,world,triangles,foot_side,cross,dot,mul,stats
def measure(path):
    data=json.loads(path.read_text(encoding='utf8'));rows=[]
    for side in ('L','R'):
        surfaces=[m for m in data['garments'] if m['name'].startswith('FIT_ACCESSORY_Shoe_'+side+'_') and m['name'].endswith(('T004','T005'))]
        assert len(surfaces)==1;shoe=surfaces[0];surface=Surface(triangles(shoe,world(shoe)));samples=[]
        for base in data['base_meshes']:
            if base['name'] not in ('Body','Foot'):continue
            points=world(base);m=base['world_matrix'];matrix=[m[i][:3] for i in range(3)];co=[cross(matrix[1],matrix[2]),cross(matrix[2],matrix[0]),cross(matrix[0],matrix[1])];sign=1 if dot(matrix[0],co[0])>=0 else -1
            for i,weight in enumerate(base['weights']):
                mass=sum(w for slot,w in zip(weight['indices'],weight['weights']) if foot_side(data['bones'][base['bone_ids'][slot]]['name'])==side)
                if mass<.35:continue
                n=tuple(sign*dot(row,base['normals'][i]) for row in co);length=math.sqrt(dot(n,n))
                if length>1e-10:samples.append((points[i],mul(n,1/length)))
        assert samples;ymin=min(p[1] for p,n in samples);zmin=min(p[2] for p,n in samples);zmax=max(p[2] for p,n in samples)
        bands={'sole':lambda p,n:n[1]<-.5 and p[1]<ymin+.035,'rear_heel':lambda p,n:n[2]<-.5 and p[2]<zmin+.045 and p[1]<ymin+.070,'low_side':lambda p,n:abs(n[0])>.6 and p[1]<ymin+.035,'toe_cap':lambda p,n:n[1]>.5 and p[2]>zmax-.065}
        for band,choose in bands.items():
            distances=[];missing=[];total=0
            for p,n in samples:
                if not choose(p,n):continue
                total+=1;distance=surface.ray(p,n)
                if distance is not None and distance<=.060:distances.append(distance)
                else:missing.append(p)
            rows.append({'side':side,'region':band,'samples':total,'outward_surface_hits_within_60mm':len(distances),'missing_outward_hits':len(missing),'distance':stats(distances),'missing_positions_world_m':missing})
    return {'reference':str(path),'frame':data['frame'],'rows':rows}
def main(a):
    result={'schema':'shoe-directional-coverage-v1','before':measure(a.before),'after':measure(a.after),'method':'All actual base Foot/Toe weighted vertices in normal-selected sole/rear/lower-side/toe-cap bands; exact first outward-ray hit on corresponding main shoe shell within 60mm','limitations':'Intentional open instep excluded. Misses indicate no surface along that ray; not a closed-volume penetration test. Does not certify high-heel posture, material thickness, dynamic fit or visual restoration.'}
    with a.out.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({stage:[{k:v for k,v in r.items() if k in ('side','region','samples','missing_outward_hits')} for r in result[stage]['rows']] for stage in ('before','after')}),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True);p.add_argument('--out',type=Path,required=True);main(p.parse_args())
