"""Check four real bow skins against measured native bone/bind matrices."""
import argparse, json
from pathlib import Path
import numpy as np

def main(a):
    refs=[a.folder/(n+'-reference.json') for n in ('static','walk25','walk75','sitting')]
    rows=[];original={};source_error=0.;bind_error=0.
    for path in refs:
        d=json.loads(path.read_text(encoding='utf8'));maximum=0.;meshes=[]
        assert d['base_native_shoes']['triangle_count']==0
        for g in d['garments']:
            if not g['name'].startswith('FIT_NEW_Bow'):continue
            raw=np.asarray(g['source_positions']);points=np.c_[np.asarray(g['positions']),np.ones(len(raw))]
            actual=(points@np.asarray(g['world_matrix']).T)[:,:3]
            bones=[np.asarray(d['bones'][i]['world_matrix'])@np.asarray(bind) for i,bind in zip(g['bone_ids'],g['bindposes'])]
            names=[d['bones'][i]['name'] for i in g['bone_ids']]
            assert np.isfinite(raw).all() and np.isfinite(actual).all()
            pred=[];used=set();canonical_weights=[];used_slots=set()
            for p,weights in zip(raw,g['weights']):
                m=np.zeros((4,4));total=0
                for slot,w in zip(weights['indices'],weights['weights']):
                    if w>1e-8:m+=bones[slot]*w;total+=w;used.add(names[slot]);used_slots.add(slot)
                assert abs(total-1)<1e-5
                canonical_weights.append(tuple(sorted((names[slot],round(w,7)) for slot,w in zip(weights['indices'],weights['weights']) if w>1e-8)))
                pred.append((m@np.r_[p,1])[:3])
            err=float(np.max(np.linalg.norm(actual-np.asarray(pred),axis=1)));maximum=max(maximum,err)
            if 'Tail' in g['name']:
                assert all(n=='J_Bip_C_Hips' or n.startswith('WM_BackRibbon_') for n in used)
            else:assert used=={'J_Bip_C_Hips'}
            used_binds={names[i]:np.asarray(g['bindposes'][i]) for i in used_slots};assert len(used_binds)==len(used_slots)
            identity=(raw,canonical_weights,used_binds,g['triangles'])
            if path==refs[0]:original[g['name']]=identity
            else:
                prior=original[g['name']];assert prior[1]==identity[1] and prior[3]==identity[3] and prior[2].keys()==used_binds.keys()
                delta=float(np.max(np.linalg.norm(prior[0]-raw,axis=1)));source_error=max(source_error,delta)
                delta_bind=max(float(np.max(abs(prior[2][n]-m))) for n,m in used_binds.items());bind_error=max(bind_error,delta_bind)
                assert delta<1e-6,(path,g['name'],delta)
            meshes.append({'name':g['name'],'vertices':len(raw),'used_bones':sorted(used),'maximum_skin_reconstruction_error_mm':err*1000})
        assert len(meshes)==5 and maximum<2e-6,(path,maximum)
        rows.append({'reference':str(path),'pose_source':d['pose_source'],'frame':d['frame'],'meshes':meshes,'maximum_skin_error_mm':maximum*1000})
    report={'passed':True,'poses':rows,'five_bow_skins_validated':True,'source_positions_semantic_weights_topology_stable':True,
        'source_readback_maximum_delta_mm':source_error*1000,'edit_vs_synthesized_preview_bind_matrix_maximum_component_difference':bind_error,
        'source_position_tolerance_m':1e-6,'skin_reconstruction_tolerance_m':2e-6,
        'bone_palette_handling':'Preview omits unused edit bones and rebases bind matrices to its synthesized skeleton. Compare nonzero semantic influences, source positions and topology across captures; reconstruct each BakeMesh independently from its own actual renderer bone IDs and bind matrices. Native source floats compared at 1 micrometer.',
        'scope':'Four native edit/held poses and real BakeMesh skin reconstruction. Does not certify self collision, sitting skirt, all motion or Godot.'}
    with (a.folder/'skin-verification.json').open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps({'passed':True,'poses':4,'maximum_skin_error_mm':max(r['maximum_skin_error_mm'] for r in rows)}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',type=Path,required=True);main(p.parse_args())
