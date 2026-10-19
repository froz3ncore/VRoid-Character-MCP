"""Cold production-server smoke test; no test-only native injection."""
import argparse,asyncio,base64,json,sys
from pathlib import Path
from capture_quality_acceptance import dump,digest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import clean_native_clothing as lifecycle

async def main(out,baseline_file=None):
    out.mkdir(exist_ok=False);lifecycle.OUT=out
    source=lifecycle.LAB/'saves'/lifecycle.SOURCE;sha=digest(source)
    assembly=json.loads((ROOT/'projects/whale-maid/sleeve-cuff-v01/final-wear/refined-wear-acceptance.json').read_text(encoding='utf8'))['save']
    record={}
    if baseline_file:
        baseline=json.loads(baseline_file.read_text(encoding='utf8'))['default_after_reopen']
        async with lifecycle.client_for(source,'comparison') as (_,call):
            token=(await call('list_face_params'))['model_token']
            record['comparison']=await call('capture_review',{'expected_model':token,'views':['front'],'size':256,'baseline_id':baseline['capture_id']})
            assert record['comparison']['parameter_changes']==[]
            assert not record['comparison']['baseline_same_model_token']
        record.update(passed=True,source_unchanged=digest(source)==sha)
        dump(out/'acceptance.json',record);print('Cold baseline comparison passed',flush=True)
        return
    async with lifecycle.client_for(source,'production') as (client,call):
        before=await call('list_face_params');token=before['model_token']
        record['edit']=await call('capture_review',{'expected_model':token,'views':['front'],'size':2048,'quality':'high'})
        assert record['edit']['images']['front']['quality']['render_size']==2828
        await call('set_preview_mode',{'expected_model':token,'mode':'photo'})
        r=await client.call_tool('screenshot',{'expected_model':token,'view':'photo','quality':'high','size':512});assert not r.isError,r
        data=base64.b64decode(next(c.data for c in r.content if c.type=='image'))
        (out/'photo-high.png').write_bytes(data)
        assert int.from_bytes(data[16:20],'big')==512
        await call('set_preview_mode',{'expected_model':token,'mode':'edit'})
        assert before==await call('list_face_params')
        status=await call('get_wear_status')
        status=await call('open_wear_project',{'expected_wear':status['wear_token'],'filename':Path(assembly['path']).name,'discard_unsaved':True})
        wt=status['wear_token']
        record['wear']=await call('capture_wear_review',{'expected_wear':wt,'views':['front'],'quality':'high','size':512})
        await call('set_wear_animation',{'expected_wear':wt,'playing':True})
        try:record['motion']=await call('capture_wear_motion',{'expected_wear':wt,'samples':3,'interval_seconds':.1,'view':'side','size':512,'quality':'high'})
        finally:await call('set_wear_animation',{'expected_wear':wt,'playing':False})
    async with lifecycle.client_for(source,'cold-reopen') as (_,call):
        token=(await call('list_face_params'))['model_token']
        record['default_after_reopen']=await call('capture_review',{'expected_model':token,'views':['front'],'size':256})
        assert record['default_after_reopen']['images']['front']['quality']['msaa_samples']==4
    record.update(passed=True,source_unchanged=digest(source)==sha,assembly_unchanged=digest(assembly['path'])==assembly['sha256'])
    assert record['source_unchanged'] and record['assembly_unchanged']
    dump(out/'acceptance.json',record);print(json.dumps({'passed':True,'output':str(out)}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--baseline-file',type=Path)
    a=p.parse_args();asyncio.run(main(a.output,a.baseline_file))
