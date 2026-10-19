"""Bounded, metadata-only API exploration from a saved query plan."""
import argparse,asyncio,hashlib,json
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1]
async def main(a):
    out=a.out.resolve();out.mkdir(exist_ok=False);native.OUT=out;native.PROJECT=ROOT/'work/cosmetics-mcp-v01';native.LAB=ROOT/'lab-clothing-fit-v17'
    model=Path(json.loads((ROOT/'projects/whale-maid/accessory-refinement-v02/chest-skirt-v17b/isolated-base-record.json').read_text(encoding='utf8'))['save']['path']);sha=hashlib.sha256(model.read_bytes()).hexdigest();plan=json.loads(a.plan.read_text(encoding='utf8'));results={}
    async with native.client_for(model,'metadata') as (_,call):
        await call('list_face_params')
        for query in plan:
            key=query['tool']+':'+query['args'].get('class_name',query['args'].get('substring',''))
            try:results[key]=await call(query['tool'],query['args'])
            except Exception as e:results[key]={'error':str(e)[:500]}
            (out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
            print(key,flush=True)
    assert hashlib.sha256(model.read_bytes()).hexdigest()==sha
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--out',type=Path,required=True);asyncio.run(main(p.parse_args()))
