"""Production-server smoke on a second fixture and remaining wear regions."""
import argparse,asyncio,base64,json,sys
from pathlib import Path
from capture_quality_acceptance import dump,digest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import clean_native_clothing as lifecycle

async def main(out):
    out.mkdir(exist_ok=False);lifecycle.OUT=out
    source=lifecycle.LAB/'saves/heterochromia-state-a80c98e7591943fa982bcf4bdbdb8635.vroid'
    sha=digest(source)
    assembly=json.loads((ROOT/'projects/whale-maid/sleeve-cuff-v01/final-wear/refined-wear-acceptance.json').read_text(encoding='utf8'))['save']
    record={}
    async with lifecycle.client_for(source,'production') as (client,call):
        token=(await call('list_face_params'))['model_token']
        result=await client.call_tool('screenshot',{'expected_model':token,'view':'face_front','size':768,'quality':'high'})
        assert not result.isError
        data=base64.b64decode(next(c.data for c in result.content if c.type=='image'))
        (out/'face-front.png').write_bytes(data);assert int.from_bytes(data[16:20],'big')==768
        record['ordinary']=await call('capture_review',{'expected_model':token,'views':['face_left','face_right'],'size':512})
        record['invalid_view']=await call('screenshot',{'expected_model':token,'view':'face:left','size':256},error=True)
        status=await call('get_wear_status')
        status=await call('open_wear_project',{'expected_wear':status['wear_token'],'filename':Path(assembly['path']).name,'discard_unsaved':True})
        wt=status['wear_token']
        record['dress_guard']=await call('screenshot',{'expected_model':token,'view':'face_left','size':256},error=True)
        assert 'DRESS_UP_ACTIVE' in record['dress_guard']
        record['wear']=[]
        for region in ['body','face','head']:
            r=await call('capture_wear_review',{'expected_wear':wt,'views':[region+'_'+a for a in ['front','back','left','right','three_quarter_left','three_quarter_right']],'size':512,'quality':'high'})
            assert all(i['framing']['camera_readback_verified'] for i in r['images'])
            record['wear'].append(r);dump(out/'partial.json',record)
            print('production-wear-'+region+'-passed',flush=True)
    record.update(passed=True,source_unchanged=digest(source)==sha,assembly_unchanged=digest(assembly['path'])==assembly['sha256'])
    assert record['source_unchanged'] and record['assembly_unchanged']
    dump(out/'acceptance.json',record);print(json.dumps({'passed':True,'output':str(out)}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    asyncio.run(main(p.parse_args().output))
