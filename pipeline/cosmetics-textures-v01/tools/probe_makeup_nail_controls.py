"""Read-only cosmetics discovery on the isolated current high-heel base."""
import asyncio,hashlib,json,shutil
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'projects/whale-maid/diagnostics/makeup-nail-probe-v01'
native.PROJECT=ROOT/'work/clothing-mcp-v17b';native.LAB=ROOT/'lab-clothing-fit-v17';native.OUT=OUT
def write(p,d):
    with p.open('x',encoding='utf8') as f:json.dump(d,f,ensure_ascii=False,indent=2)
async def pages(call,name,args,key):
    rows=[];offset=0
    while True:
        r=await call(name,dict(args,offset=offset,limit=200));rows+=r[key]
        if r.get('next_offset') is None:return rows
        offset=r['next_offset']
async def main():
    OUT.mkdir(parents=True,exist_ok=False)
    source=json.loads((ROOT/'projects/whale-maid/accessory-refinement-v02/chest-skirt-v17b/isolated-base-record.json').read_text(encoding='utf8'))['save']
    model=Path(source['path']);assert hashlib.sha256(model.read_bytes()).hexdigest()==source['sha256']
    async with native.client_for(model,'cosmetics-probe') as (_,call):
        face=await call('list_face_params');await asyncio.sleep(8);token=face['model_token']
        write(OUT/'face.json',face)
        for domain in ('colors','body','general'):
            rows=await pages(call,'list_parameters',{'domain':domain},'parameters');write(OUT/(domain+'.json'),rows)
            print(json.dumps({'domain':domain,'count':len(rows),'cosmetic_matches':[r for r in rows if any(x in json.dumps(r).lower() for x in ('nail','lip','cheek','eyelash','eyeline','eyeshadow','makeup'))]},ensure_ascii=False),flush=True)
        presets=await pages(call,'list_presets',{'area':'face'},'presets');write(OUT/'face-presets.json',presets)
        print(json.dumps({'face_preset_categories':sorted({p.get('category','') for p in presets}),'count':len(presets)},ensure_ascii=False),flush=True)
        capture=await call('capture_review',{'expected_model':token,'views':['face_front','face_three_quarter_right','full_front'],'size':1024,'quality':'high','label':'Current high heel base before cosmetics'})
        write(OUT/'before-review.json',capture)
        for r in capture.get('images',[]):
            if 'path' in r:shutil.copy2(r['path'],OUT/('before-'+r.get('view','image')+'.png'))
    assert hashlib.sha256(model.read_bytes()).hexdigest()==source['sha256']
    write(OUT/'acceptance.json',{'passed':True,'read_only':True,'source_unchanged':True,'source':source})
if __name__=='__main__':asyncio.run(main())
