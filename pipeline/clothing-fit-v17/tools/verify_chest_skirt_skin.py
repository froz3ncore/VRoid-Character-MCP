"""Independent native BakeMesh reconstruction for every changed garment skin."""
import argparse,json
from pathlib import Path
import numpy as np
def load(p):return json.loads(Path(p).read_text(encoding='utf8'))
def main(a):
    build=load(a.build);wanted=set(build.get('verification_meshes',build.get('weight_meshes',[])));initial={};rows=[];readback=0.
    assert wanted,'No meshes requested for verification'
    for label in ('edit','sitting','walk25','walk75'):
        d=load(a.folder/(label+'-reference.json'));assert d['base_native_shoes']['triangle_count']==0;meshes=[]
        for g in d['garments']:
            if g['name'] not in wanted:continue
            raw=np.asarray(g['source_positions']);positions=np.asarray(g['positions']);world=np.asarray(g['world_matrix'])
            actual=positions@world[:3,:3].T+world[:3,3]
            matrices=np.asarray([np.asarray(d['bones'][i]['world_matrix'])@np.asarray(bind) for i,bind in zip(g['bone_ids'],g['bindposes'])])
            names=[d['bones'][i]['name'] for i in g['bone_ids']]
            indices=np.asarray([w['indices'] for w in g['weights']],dtype=int);weights=np.asarray([w['weights'] for w in g['weights']])
            assert np.isfinite(raw).all() and np.isfinite(actual).all() and np.max(abs(weights.sum(1)-1))<1e-5 and np.min(weights)>-1e-8
            homogeneous=np.c_[raw,np.ones(len(raw))];pred=np.zeros_like(raw)
            for slot in range(4):pred+=np.einsum('nij,nj->ni',matrices[indices[:,slot],:3,:],homogeneous)*weights[:,slot,None]
            error=float(np.max(np.linalg.norm(pred-actual,axis=1)));assert error<2e-6,(label,g['name'],error)
            semantic=[]
            for ii,ww in zip(indices,weights):
                row={}
                for i,w in zip(ii,ww):
                    if w<=1e-8:continue
                    name=names[i];name='J_Bip_C_Chest' if name=='J_Bip_C_UpperChest' else name
                    row[name]=row.get(name,0)+float(w)
                semantic.append(row)
            if label=='edit':initial[g['name']]=(raw,semantic,g['triangles'])
            else:
                old,old_skin,tri=initial[g['name']];assert tri==g['triangles']
                skin_delta=max((abs(a.get(n,0)-b.get(n,0)) for a,b in zip(old_skin,semantic) for n in set(a)|set(b)),default=0)
                assert skin_delta<1e-6,(label,g['name'],'semantic skin delta',skin_delta)
                delta=float(np.max(np.linalg.norm(old-raw,axis=1)));assert delta<1e-6,(label,g['name'],delta);readback=max(readback,delta)
            meshes.append({'name':g['name'],'vertices':len(raw),'maximum_skin_error_mm':error*1000,'maximum_nonzero_influences':int(np.max((weights>1e-8).sum(1)))})
        assert len(meshes)==len(wanted);rows.append({'label':label,'frame':d['frame'],'meshes':meshes,'maximum_skin_error_mm':max(m['maximum_skin_error_mm'] for m in meshes)})
    report={'passed':True,'affected_meshes':len(wanted),'poses':rows,'source_readback_maximum_delta_mm':readback*1000,
        'source_position_tolerance_m':1e-6,'skin_reconstruction_tolerance_m':2e-6,
        'scope':'Every changed skin is reconstructed from its own actual renderer bone IDs/bind matrices. Semantic nonzero weights accumulated after the observed native UpperChest-to-Chest preview remap (1e-6 tolerance); source positions and triangles compared across four native poses. Does not certify collisions or final art.'}
    with (a.folder/'skin-verification.json').open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps({'passed':True,'affected_meshes':len(wanted),'poses':4,'maximum_skin_error_mm':max(r['maximum_skin_error_mm'] for r in rows)}),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--folder',type=Path,required=True);main(p.parse_args())
