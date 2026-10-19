"""Measure native heel controls on an unsaved, isolated white-tights base."""
import asyncio,hashlib,json,shutil
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'projects/whale-maid/accessory-refinement-v02/heel-shape-probe-v01'
PRESET='clothing/Shoes/8575d9ea4502a37f903b7cf919dacc67d34298c2.transferablegroup'
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def world(m):
    return [[sum(m['world_matrix'][i][j]*p[j] for j in range(3))+m['world_matrix'][i][3] for i in range(3)] for p in m['positions']]
def describe(data):
    foot=next(m for m in data['meshes'] if m['name']=='Foot');p=world(foot)
    points=[q for q in p if q[0]>0];zmin=min(q[2] for q in points);zmax=max(q[2] for q in points)
    def band(lo,hi):
        ys=sorted(q[1] for q in points if lo<=q[2]<=hi)
        return {'samples':len(ys),'minimum_y_mm':ys[0]*1000,'lower_quartile_y_mm':ys[len(ys)//4]*1000}
    return {'height_cm':data['height_cm'],'foot_bounds_m':{'min':[min(q[k] for q in points) for k in range(3)],'max':[max(q[k] for q in points) for k in range(3)]},'heel':band(zmin,zmin+(zmax-zmin)*.25),'toe':band(zmax-(zmax-zmin)*.25,zmax)}
async def main():
    OUT.mkdir(exist_ok=False);native.OUT=OUT
    record=json.loads((OUT.parent/'footwear-base/base-acceptance.json').read_text(encoding='utf8'));base=record['save'];assert digest(base['path'])==base['sha256']
    rows=[]
    async with native.client_for(Path(base['path']),'heel-shape-unsaved') as (_,call):
        await asyncio.sleep(10);token=(await call('list_face_params'))['model_token']
        protected={d:await native.parameters(call,d) for d in ('face','body','colors')}
        async def capture(label):
            ref=await call('capture_body_reference',{'expected_model':token,'label':label})
            dest=OUT/(label+'.json');shutil.copy2(ref['path'],dest)
            row={'case':label,'reference':str(dest),**describe(json.loads(dest.read_text(encoding='utf8')))};rows.append(row);print(json.dumps(row),flush=True)
        await capture('barefoot')
        await call('apply_clothing_preset',{'expected_model':token,'preset_id':PRESET})
        listing=await call('list_clothing_params');params=listing['parameters'] if isinstance(listing,dict) else listing
        high=next(p for p in params if p.get('semantic_key','').endswith('Shoes.High'))
        await capture('mules-default')
        await call('set_clothing_params',{'expected_model':token,'changes':[{'id':high['id'],'value':100}]})
        await capture('mules-high-100')
        await call('apply_clothing_preset',{'expected_model':token,'preset_id':'clothing/Shoes/none'})
        await capture('removed-after-high')
        assert protected=={d:await native.parameters(call,d) for d in protected}
    assert digest(base['path'])==base['sha256']
    (OUT/'probe.json').write_text(json.dumps({'passed':True,'source':base,'source_unchanged':True,'saved':False,'cases':rows},ensure_ascii=False,indent=2),encoding='utf8')
if __name__=='__main__':asyncio.run(main())
