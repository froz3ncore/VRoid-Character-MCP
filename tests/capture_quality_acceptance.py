"""Owned lab-test capture regression; never saves the character or garment."""
import argparse,asyncio,base64,hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import clean_native_clothing as lifecycle

def dump(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

async def main(out):
    out.mkdir(exist_ok=False);lifecycle.OUT=out
    original=lifecycle.StdioServerParameters
    def parameters(**kw):
        kw['args']=[str(Path(__file__).with_name('capture_quality_diagnostics_server.py')),*kw['args'][2:]]
        return original(**kw)
    lifecycle.StdioServerParameters=parameters
    source=lifecycle.LAB/'saves'/lifecycle.SOURCE;before_hash=digest(source)
    record={'source':str(source),'source_sha256':before_hash,'captures':[]}
    async with lifecycle.client_for(source,'capture') as (client,call):
        before=await call('list_face_params');token=before['model_token']
        for quality in ('legacy','balanced','high'):
            start=time.monotonic()
            r=await call('capture_review',{'expected_model':token,'views':['front','full_front'],'size':768,'quality':quality})
            record['captures'].append({'mode':'edit','wall_seconds':time.monotonic()-start,**r})
            for view,item in r['images'].items():
                (out/(quality+'-'+view+'.png')).write_bytes(Path(item['path']).read_bytes())
            print(json.dumps({'phase':quality,'images':r['images']},ensure_ascii=True),flush=True)
            dump(out/'partial.json',record)
        capped=await call('capture_review',{'expected_model':token,'views':['front'],'size':2048,'quality':'high'})
        q=capped['images']['front']['quality'];assert q['clamped'] and q['render_size']==2828 and q['msaa_samples']==4
        record['capped']=capped
        for i in range(4):
            await call('capture_review',{'expected_model':token,'views':['side'],'size':256,'quality':'high'})
        assert before==await call('list_face_params')
        baseline=record['captures'][-1]
        await call('capture_review',{'expected_model':token,'views':['front','full_front'],'size':768,'quality':'legacy','baseline_id':baseline['capture_id']},error=True)
        await call('set_preview_mode',{'expected_model':token,'mode':'photo'})
        for quality in ('legacy','balanced','high'):
            r=await client.call_tool('screenshot',{'expected_model':token,'view':'photo','size':512,'quality':quality})
            assert not r.isError,r
            data=base64.b64decode(next(c.data for c in r.content if c.type=='image'))
            assert int.from_bytes(data[16:20],'big')==512
            (out/('photo-'+quality+'.png')).write_bytes(data)
        await call('set_preview_mode',{'expected_model':token,'mode':'edit'})
        assert before==await call('list_face_params')
        print('photo-and-edit-passed',flush=True)
        assembly=json.loads((ROOT/'projects/whale-maid/sleeve-cuff-v01/final-wear/refined-wear-acceptance.json').read_text(encoding='utf8'))['save']
        assert digest(assembly['path'])==assembly['sha256']
        status=await call('get_wear_status')
        status=await call('open_wear_project',{'expected_wear':status['wear_token'],'filename':Path(assembly['path']).name,'discard_unsaved':True})
        wt=status['wear_token'];snapshot=await call('get_wear_snapshot',{'expected_wear':wt})
        record['wear']=[]
        for quality in ('legacy','balanced','high'):
            start=time.monotonic()
            r=await call('capture_wear_review',{'expected_wear':wt,'views':['front','back'],'size':768,'quality':quality})
            record['wear'].append({'wall_seconds':time.monotonic()-start,**r})
            for item in r['images']:
                assert item['quality']['msaa_samples']==(1 if quality=='legacy' else 4)
                assert item['quality']['resource_state_restored']
                (out/('wear-'+quality+'-'+item['view']+'.png')).write_bytes(Path(item['path']).read_bytes())
            dump(out/'partial.json',record)
            print('wear-'+quality+'-passed',flush=True)
        await call('set_wear_animation',{'expected_wear':wt,'playing':True})
        record['motion']=await call('capture_wear_motion',{'expected_wear':wt,'samples':3,'interval_seconds':.1,'view':'side','size':512,'quality':'high'})
        await call('set_wear_animation',{'expected_wear':wt,'playing':False})
        after=await call('get_wear_snapshot',{'expected_wear':wt})
        assert snapshot['base_model']==after['base_model']
        record['assembly_unchanged']=digest(assembly['path'])==assembly['sha256'];assert record['assembly_unchanged']
        record['run_dir']=str(sorted((lifecycle.LAB/'runs').iterdir(),key=lambda p:p.stat().st_mtime)[-1])
    record['source_unchanged']=digest(source)==before_hash;assert record['source_unchanged']
    record['passed']=True;dump(out/'acceptance.json',record)
    print(json.dumps({'passed':True,'output':str(out)}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    asyncio.run(main(p.parse_args().output))
