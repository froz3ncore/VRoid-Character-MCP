"""Owned lab-test native regional camera acceptance; no character or garment saves."""
import argparse,asyncio,json,sys
from pathlib import Path
from capture_quality_acceptance import dump,digest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import clean_native_clothing as lifecycle

def verify(records):
    for item in records:
        f=item['framing']
        assert f['camera_readback_verified'] and f['angle_reference']=='observer_from_front'
        assert item['quality']['resource_state_restored']
    by_view={r['framing']['view']:r['framing'] for r in records}
    for region in ['body','face','head','upper','legs','feet']:
        for left,right in [('left','right'),('three_quarter_left','three_quarter_right')]:
            a=by_view.get(region+'_'+left);b=by_view.get(region+'_'+right)
            if a and b:
                assert a['target']==b['target'] and a['distance']==b['distance']
                assert abs(a['position'][0]+b['position'][0]-2*a['target'][0])<1e-5

async def main(out):
    out.mkdir(exist_ok=False);lifecycle.OUT=out
    original=lifecycle.StdioServerParameters
    def parameters(**kw):
        kw['args']=[str(Path(__file__).with_name('capture_quality_diagnostics_server.py')),*kw['args'][2:]]
        return original(**kw)
    lifecycle.StdioServerParameters=parameters
    source=lifecycle.LAB/'saves'/lifecycle.SOURCE;sha=digest(source)
    assembly=json.loads((ROOT/'projects/whale-maid/sleeve-cuff-v01/final-wear/refined-wear-acceptance.json').read_text(encoding='utf8'))['save']
    record={'ordinary':[],'source':str(source),'source_sha256':sha}
    angles=['front','back','left','right','three_quarter_left','three_quarter_right']
    async with lifecycle.client_for(source,'regional') as (client,call):
        tools=await client.list_tools();assert len(tools.tools)==49
        before=await call('list_face_params');token=before['model_token']
        for region in ['body','face','head','upper','legs','feet']:
            r=await call('capture_review',{'expected_model':token,'views':[region+'_'+a for a in angles],'size':512,'quality':'high'})
            verify([{'view':view,**item} for view,item in r['images'].items()])
            frames={item['framing']['reference_frame'] for item in r['images'].values()};assert len(frames)==1
            record['ordinary'].append(r)
            dump(out/'partial.json',record);print(region+'-native-passed',flush=True)
        base=record['ordinary'][1]
        record['same_model_baseline']=await call('capture_review',{'expected_model':token,'views':base['views'],'size':512,'quality':'high','baseline_id':base['capture_id']})
        assert record['same_model_baseline']['framing_mode']=='baseline_locked'
        assert record['same_model_baseline']['parameter_changes']==[]
        legacy=await call('capture_review',{'expected_model':token,'views':['front','side','back','three_quarter','full_front','full_side'],'size':256})
        assert all('framing' not in item for item in legacy['images'].values())
        record['legacy']=legacy
        assert before==await call('list_face_params')
        await call('set_preview_mode',{'expected_model':token,'mode':'photo'})
        await call('screenshot',{'expected_model':token,'view':'face_left','size':256},error=True)
        await call('set_preview_mode',{'expected_model':token,'mode':'edit'})
        status=await call('get_wear_status')
        status=await call('open_wear_project',{'expected_wear':status['wear_token'],'filename':Path(assembly['path']).name,'discard_unsaved':True})
        wt=status['wear_token'];snapshot=await call('get_wear_snapshot',{'expected_wear':wt})
        record['wear']=[]
        for region in ['upper','legs','feet']:
            r=await call('capture_wear_review',{'expected_wear':wt,'views':[region+'_'+a for a in angles],'size':512,'quality':'high'})
            verify(r['images']);record['wear'].append(r)
            assert len({item['framing']['reference_frame'] for item in r['images']})==1
            dump(out/'partial.json',record);print('wear-'+region+'-passed',flush=True)
        await call('set_wear_animation',{'expected_wear':wt,'playing':True})
        try:
            record['motion']=await call('capture_wear_motion',{'expected_wear':wt,'samples':3,'interval_seconds':.1,'view':'legs_three_quarter_right','size':512,'quality':'high'})
            verify(record['motion']['images'])
            positions=[i['framing']['position'] for i in record['motion']['images']]
            assert all(p==positions[0] for p in positions)
        finally:await call('set_wear_animation',{'expected_wear':wt,'playing':False})
        after=await call('get_wear_snapshot',{'expected_wear':wt});assert snapshot['base_model']==after['base_model']
        record['run_dir']=str(sorted((lifecycle.LAB/'runs').iterdir(),key=lambda p:p.stat().st_mtime)[-1])
    # Production server in another process: old reference must never leak across models/sessions.
    lifecycle.StdioServerParameters=original
    async with lifecycle.client_for(source,'cold-production') as (_,call):
        token=(await call('list_face_params'))['model_token']
        record['cold']=await call('capture_review',{'expected_model':token,'views':base['views'],'size':512,'quality':'high','baseline_id':base['capture_id']})
        assert record['cold']['framing_mode']=='current_model' and not record['cold']['baseline_same_model_token']
        assert all(i['framing']['camera_readback_verified'] for i in record['cold']['images'].values())
    record.update(source_unchanged=digest(source)==sha,assembly_unchanged=digest(assembly['path'])==assembly['sha256'],passed=True)
    assert record['source_unchanged'] and record['assembly_unchanged']
    dump(out/'acceptance.json',record);print(json.dumps({'passed':True,'output':str(out)}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    asyncio.run(main(p.parse_args().output))
