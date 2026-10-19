"""Predict a smooth rear-only rest-shape offset in frozen native captures."""
import json,importlib.util
from pathlib import Path
from mathutils import Matrix,Vector
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('fit',ROOT/'blender-addons/vroid_xwear_direct/fit.py')
fit=importlib.util.module_from_spec(spec);spec.loader.exec_module(fit)

def factor(point):
    def smooth(x):
        x=max(0,min(1,x));return x*x*(3-2*x)
    return smooth((-point[2]-.06)/.08)*smooth((.8-point[1])/.25)

def evaluate(path,amounts):
    d=json.loads(Path(path).read_text(encoding='utf8'));g=d['garments'][0];surface=fit.Surface(d['body'])
    matrices=[Matrix(d['bones'][i]['world_matrix'])@Matrix(b) for i,b in zip(g['bone_ids'],g['bindposes'])]
    selected={i for i,p in enumerate(g['source_positions']) if -.8<p[2]<-.05 and .3<p[1]<.93}
    faces=[tuple(g['triangles'][i:i+3]) for i in range(0,len(g['triangles']),3)]
    faces=[t for t in faces if all(i in selected for i in t)]
    edges={tuple(sorted((a,b))) for t in faces for a,b in zip(t,t[1:]+t[:1])}
    rows=[]
    for amount in amounts:
        posed=[]
        for p,w in zip(g['source_positions'],g['weights']):
            q=Vector(p);q.z-=amount*factor(p)
            posed.append(sum(((matrices[i]@q)*weight for i,weight in zip(w['indices'],w['weights']) if weight>1e-7),Vector()))
        counts={};deepest=0.
        for kind,ids in [('vertices',[(i,) for i in selected]),('faces',faces),('edges',edges)]:
            count=0
            for ids_ in ids:
                p=sum((posed[i] for i in ids_),Vector())/len(ids_)
                normal,signed,distance=surface.nearest(p)
                if signed<-.003 and distance<.12:count+=1;deepest=max(deepest,-signed)
            counts[kind]=count
        rows.append({'amount_m':amount,'screening':counts,'total':sum(counts.values()),'deepest_m':deepest})
    return {'reference':str(path),'predictions':rows}
