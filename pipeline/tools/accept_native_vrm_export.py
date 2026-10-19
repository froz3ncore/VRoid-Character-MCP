"""Validate the public native VRM tool on the accepted XRoid, without saving it."""
import argparse,asyncio,hashlib,json,shutil,uuid
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1]
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

async def main(a):
    out=a.out.resolve();assert out.is_relative_to(ROOT/'projects/whale-maid');out.mkdir(parents=True,exist_ok=False);native.OUT=out
    saved=json.loads((ROOT/'projects/whale-maid/sleeve-cuff-v01/final-wear/refined-wear-acceptance.json').read_text(encoding='utf8'))['save']
    base=json.loads((ROOT/'projects/whale-maid/clean-wear-v01/clean-base-acceptance.json').read_text(encoding='utf8'))['save']
    assert digest(saved['path'])==saved['sha256'] and digest(base['path'])==base['sha256']
    record={'passed':False,'source':saved}
    def write(): (out/'acceptance.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
    async with native.client_for(Path(base['path']),'native-vrm-export') as (client,call):
        state=await call('get_wear_status');state=await call('open_wear_project',{'filename':Path(saved['path']).name,'expected_wear':state['wear_token'],'discard_unsaved':True});token=state['wear_token']
        before=await call('get_wear_snapshot',{'expected_wear':token})
        args={'expected_wear':token,'filename':'whale-maid-native-'+uuid.uuid4().hex+'.vrm','title':'Whale maid local validation','author':'Local test asset','version':'test-only'}
        errors={}
        errors['invalid_path']=await call('export_wear_vrm',{**args,'filename':'../bad.vrm'},True)
        errors['stale_wear']=await call('export_wear_vrm',{**args,'expected_wear':'stale'},True)
        await call('set_wear_animation',{'expected_wear':token,'playing':True})
        errors['playing']=await call('export_wear_vrm',args,True)
        await call('set_wear_animation',{'expected_wear':token,'playing':False})
        result=await call('export_wear_vrm',args);record['export']=result;write()
        assert result['exported'] and result['format']=='VRM1' and result['self_contained']
        assert (result['meshes'],result['skins'],result['images'],result['springs'],result['colliders'])==(73,73,86,32,27)
        assert all('Skirt_%02d'%i in result['spring_names'] for i in range(12))
        source=Path(result['path']);assert digest(source)==result['sha256']
        errors['overwrite']=await call('export_wear_vrm',args,True)
        assert digest(source)==result['sha256']
        after=await call('get_wear_snapshot',{'expected_wear':token})
        assert before['base_model']==after['base_model'] and before['items']==after['items']
        review=await call('capture_wear_review',{'expected_wear':token,'views':['body_front','legs_left','legs_right'],'size':768,'quality':'high'})
        target=out/'whale_maid_baseline_native_test.vrm';shutil.copy2(source,target)
        record.update(passed=True,errors=errors,snapshot_unchanged=True,source_files_unchanged=True,review=review,
            delivered=str(target),tools=len((await client.list_tools()).tools))
    assert digest(saved['path'])==saved['sha256'] and digest(base['path'])==base['sha256']
    write();print(json.dumps({'passed':True,'tools':record['tools'],'vrm':record['delivered'],'sha256':record['export']['sha256']},ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);asyncio.run(main(p.parse_args()))
