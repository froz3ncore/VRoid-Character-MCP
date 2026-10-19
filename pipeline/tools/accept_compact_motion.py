"""Final wire-level smoke after compacting the motion MCP response."""
import asyncio,json,hashlib
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'projects/whale-maid/target-fit-v02';native.OUT=OUT
async def main():
    saved=json.loads((OUT/'refined-wear-acceptance.json').read_text(encoding='utf8'))['save']
    base=json.loads((ROOT/'projects/whale-maid/clean-wear-v01/clean-base-acceptance.json').read_text(encoding='utf8'))['save']['path']
    async with native.client_for(Path(base),'compact-motion') as (_,call):
        status=await call('get_wear_status')
        status=await call('open_wear_project',{'filename':Path(saved['path']).name,'expected_wear':status['wear_token'],'discard_unsaved':True})
        token=status['wear_token'];await call('set_wear_animation',{'expected_wear':token,'playing':True})
        try:
            result=await call('capture_wear_motion',{'expected_wear':token,'samples':3,'size':256})
            assert 'samples' not in result and len(result['images'])==3
            evidence=json.loads(Path(result['manifest_path']).read_text(encoding='utf8'))
            assert len(evidence['samples'])==3 and all(s['bones'] for s in evidence['samples'])
        finally:await call('set_wear_animation',{'expected_wear':token,'playing':False})
    assert hashlib.sha256(Path(saved['path']).read_bytes()).hexdigest()==saved['sha256']
    (OUT/'compact-motion-acceptance.json').write_text(json.dumps({'passed':True,'response':result,'saved_xroid_unchanged':True},ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'passed':True,'compact_images':len(result['images']),'full_transform_artifact':result['manifest_path']}),flush=True)
if __name__=='__main__':asyncio.run(main())
