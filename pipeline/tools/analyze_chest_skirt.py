"""Same-ROI chest ray coverage and skirt strain/penetration screening."""
import argparse,json,sys
from pathlib import Path
import numpy as np
from mathutils import Matrix,Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import barycentric_transform

def world(g):
    m=np.asarray(g['world_matrix']);p=np.asarray(g['positions']);return p@m[:3,:3].T+m[:3,3]
def main(a):
    edit=json.loads(a.edit.read_text(encoding='utf8'));eb=next(g for g in edit['base_meshes'] if g['name']=='Body');ep=world(eb)
    # Original anatomy vertex identities keep the compared chest region identical in every pose.
    roi=np.flatnonzero((abs(ep[:,0])>.075)&(abs(ep[:,0])<.155)&(ep[:,1]>1.16)&(ep[:,1]<1.265)&(ep[:,2]>-.02)&(ep[:,2]<.12)).tolist()
    assert roi
    results=[]
    for path in a.reference:
        d=json.loads(path.read_text(encoding='utf8'));body=next(g for g in d['base_meshes'] if g['name']=='Body');bp=world(body)
        m=Matrix(body['world_matrix']).to_3x3().inverted().transposed();bn=[(m@Vector(n)).normalized() for n in body['normals']]
        faces=[body['triangles'][i:i+3] for i in range(0,len(body['triangles']),3)];bpoints=[Vector(p) for p in bp]
        bt=BVHTree.FromPolygons(bpoints,faces,all_triangles=True)
        cloth=[g for g in d['garments'] if g['name'].startswith('FIT_T')]
        cp=[];cf=[]
        for g in cloth:
            pts=world(g);offset=len(cp);cp.extend(Vector(p) for p in pts);cf.extend(tuple(offset+i for i in g['triangles'][k:k+3]) for k in range(0,len(g['triangles']),3))
        tree=BVHTree.FromPolygons(cp,cf,all_triangles=True);covered=[];uncovered=[]
        for i in roi:
            hit,_,_,distance=tree.ray_cast(Vector(bp[i])+bn[i]*.0002,bn[i],.04)
            (covered if hit is not None else uncovered).append(i)
        lengths=[];inside=0;sample_count=0;worst=0.;mesh_rows=[]
        for g in cloth:
            source=np.asarray(g['source_positions']);p=world(g);tris=np.asarray(g['triangles']).reshape(-1,3)
            select=(source[:,1]>.38)&(source[:,1]<.94)
            selected=np.flatnonzero(select);local_bad=0;local_worst=0
            for i in selected:
                q,_,fi,distance=bt.find_nearest(Vector(p[i]));ids=faces[fi]
                n=barycentric_transform(q,*(bpoints[j] for j in ids),*(bn[j] for j in ids)).normalized();signed=(Vector(p[i])-q).dot(n)
                if signed<-.003 and distance<.12:local_bad+=1;local_worst=max(local_worst,-signed)
            inside+=local_bad;sample_count+=len(selected);worst=max(worst,local_worst)
            e=np.unique(np.sort(np.concatenate([tris[:,[0,1]],tris[:,[1,2]],tris[:,[2,0]]]),axis=1),axis=0)
            e=e[select[e].all(axis=1)];old=np.linalg.norm(source[e[:,0]]-source[e[:,1]],axis=1);valid=old>.002;e=e[valid];old=old[valid]
            ratios=np.linalg.norm(p[e[:,0]]-p[e[:,1]],axis=1)/old if len(e) else np.array([]);lengths.extend(ratios.tolist())
            if len(selected):mesh_rows.append({'name':g['name'],'screened_vertices':len(selected),'inside_vertices':local_bad,'max_depth_mm':local_worst*1000,'max_edge_stretch':float(max(ratios,default=0))})
        arr=np.asarray(lengths);results.append({'reference':str(path),'pose_source':d['pose_source'],'chest_roi_samples':len(roi),'chest_outward_ray_covered':len(covered),'chest_uncovered_vertex_ids':uncovered,
            'skirt_screened_vertices':sample_count,'skirt_inside_vertices':inside,'skirt_max_inside_depth_mm':worst*1000,
            'skirt_edges':len(arr),'edge_stretch_p95':float(np.percentile(arr,95)),'edge_stretch_p99':float(np.percentile(arr,99)),'edge_stretch_max':float(max(arr)),
            'edges_stretched_over_2x':int(sum(arr>2)),'edges_stretched_over_4x':int(sum(arr>4)),'meshes':mesh_rows})
    report={'original_edit_reference':str(a.edit),'chest_roi_vertex_ids':roi,'results':results,
        'scope':'Fixed anatomical ROI, outward 40mm ray coverage, rest-to-posed edge strain (>2mm rest edges), and nearest-normal skirt screening (<-3mm and distance<120mm). Not whole-surface collision proof or cloth simulation.'}
    with a.out.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps([{k:v for k,v in r.items() if k not in ('meshes','chest_uncovered_vertex_ids','reference')} for r in results]),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--edit',type=Path,required=True);p.add_argument('--reference',type=Path,action='append',required=True);p.add_argument('--out',type=Path,required=True);main(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
