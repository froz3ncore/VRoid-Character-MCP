"""Predict bounded longitudinal skin-weight changes in captured native poses.

Spring transforms stay frozen. Predictions require fresh native validation and
are never accepted as motion or contact proof.
"""
import argparse,importlib.util,json,sys
from collections import defaultdict
from pathlib import Path
from mathutils import Matrix,Vector
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('fit',ROOT/'blender-addons/vroid_xwear_direct/fit.py')
fit=importlib.util.module_from_spec(spec);spec.loader.exec_module(fit)

def shifted(weights,point,delta):
    if not weights or any(not n.startswith('WM_Skirt_') for n in weights):return weights
    factor=max(0,min(1,(-point[2]-.04)/.04))*max(0,min(1,(.9-point[1])/.15))
    if factor==0:return weights
    chains=defaultdict(lambda:[0.,0.])
    for name,w in weights.items():
        chain,segment=name.rsplit('_',1);chains[chain][0]+=w;chains[chain][1]+=w*int(segment)
    result=defaultdict(float)
    for chain,(total,weighted) in chains.items():
        q=max(0,min(3,weighted/total+delta*factor));index=int(q);mix=q-index
        result[chain+'_%02d'%index]+=total*(1-mix)
        result[chain+'_%02d'%min(index+1,3)]+=total*mix
    return {n:w for n,w in result.items() if w>1e-7}

def evaluate(path,deltas):
    d=json.loads(path.read_text(encoding='utf8'));g=d['garments'][0];surface=fit.Surface(d['body'])
    names=[d['bones'][i]['name'] for i in g['bone_ids']]
    matrices={d['bones'][i]['name']:Matrix(d['bones'][i]['world_matrix'])@Matrix(b) for i,b in zip(g['bone_ids'],g['bindposes'])}
    selected={i for i,p in enumerate(g['source_positions']) if -.8<p[2]<-.05 and .3<p[1]<.93}
    triangles=[tuple(g['triangles'][i:i+3]) for i in range(0,len(g['triangles']),3)]
    triangles=[t for t in triangles if all(i in selected for i in t)]
    edges={tuple(sorted((a,b))) for t in triangles for a,b in zip(t,t[1:]+t[:1])}
    rows=[]
    for delta in deltas:
        posed=[]
        for p,w in zip(g['source_positions'],g['weights']):
            named={names[i]:weight for i,weight in zip(w['indices'],w['weights']) if weight>1e-7}
            new=shifted(named,p,delta)
            posed.append(sum(((matrices[n]@Vector(p))*weight for n,weight in new.items()),Vector()))
        counts={};deepest=0.
        for kind,ids in [('vertices',[(i,) for i in selected]),('faces',triangles),('edges',edges)]:
            count=0
            for sample in ids:
                p=sum((posed[i] for i in sample),Vector())/len(sample)
                normal,signed,distance=surface.nearest(p)
                if signed<-.003 and distance<.12:count+=1;deepest=max(deepest,-signed)
            counts[kind]=count
        rows.append({'delta':delta,'screening':counts,'total':sum(counts.values()),'deepest_m':deepest})
    return {'reference':str(path),'predictions':rows}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--reference',type=Path,action='append',required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);assert not a.out.exists()
    rows=[evaluate(path,[-1,-.75,-.5,-.25,0,.25,.5,.75,1]) for path in a.reference]
    fit.write_new(a.out,{'predictions':rows,'scope':'Frozen spring transforms; prediction only; fresh native acceptance required'})
    for r in rows:print(json.dumps(r))
