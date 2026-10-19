"""Native MCP-only old clothing removal with saved-copy and cold-reopen evidence."""
import asyncio,hashlib,json,os,shutil,sys,uuid
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1];PROJECT=ROOT/'VRoid-MCP';LAB=ROOT/'lab-test';OUT=ROOT/'projects/whale-maid/clean-wear-v01'
SOURCE='whale_maid_03_test_base.vroid'
@asynccontextmanager
async def client_for(model,label):
    params=StdioServerParameters(command=sys.executable,args=['-m','vroid_mcp.server','--lab',str(LAB),'--model',str(model)],cwd=str(PROJECT),env=dict(os.environ,TEMP=str(ROOT/'work/temp'),TMP=str(ROOT/'work/temp')))
    with (OUT/(label+'.log')).open('w',encoding='utf8') as log:
        async with stdio_client(params,errlog=log) as (read,write):
            async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=240)) as client:
                await client.initialize()
                async def call(name,args=None,error=False):
                    result=await client.call_tool(name,args or {})
                    assert bool(result.isError)==error,(name,result)
                    if error:return str(result)
                    if name in ('capture_review','capture_wear_review'):
                        manifest=json.loads(next(c.text for c in result.content if c.type=='text'))
                        # Normal review has a compact protocol summary; wear review includes all images.
                        if name=='capture_wear_review':
                            for image in manifest['images']:shutil.copy2(image['path'],OUT/(label+'-'+image['view']+'.png'))
                        return manifest
                    return result.structuredContent or json.loads(result.content[0].text)
                yield client,call

async def selected(call,category):
    result=await call('list_clothing_presets',{'category':category,'limit':200})
    return [p['id'] for p in result['presets'] if p['selected']]

async def parameters(call,domain):
    result=await call('list_parameters',{'domain':domain,'limit':500})
    assert result.get('next_offset') is None,result
    return {p['id']:p['value'] for p in result['parameters']}

async def clean_base():
    model=LAB/'saves'/SOURCE
    before_hash=hashlib.sha256(model.read_bytes()).hexdigest()
    async with client_for(model,'clear-base') as (_,call):
        token=(await call('list_face_params'))['model_token']
        before={d:await parameters(call,d) for d in ('face','body','colors')}
        protected={cat:await selected(call,cat) for cat in ('Socks','Shoes','InnerTop','InnerBottom')}
        removed=[]
        for cat in ('Onepiece','ArmAccessory'):
            chosen=await selected(call,cat);assert len(chosen)==1,(cat,chosen)
            result=await call('apply_clothing_preset',{'expected_model':token,'preset_id':'clothing/'+cat+'/none'})
            assert result['confirmation']=='groups_removed' and len(result['removed_groups'])==1,result
            assert await selected(call,cat)==[]
            removed.append(result)
        # A repeated explicit clear is an idempotent no-op, not a fabricated mutation.
        same=await call('apply_clothing_preset',{'expected_model':token,'preset_id':'clothing/Onepiece/none'})
        assert not same['changed'] and same['removed_groups']==[]
        assert before=={d:await parameters(call,d) for d in before}
        assert protected=={cat:await selected(call,cat) for cat in protected}
        saved=await call('save_as',{'expected_model':token,'filename':'whale-maid-clean-base-'+uuid.uuid4().hex+'.vroid'})
        record={'passed':True,'removed':removed,'protected':protected,'parameters':before,'save':saved,'repeated_clear_noop':True}
        (OUT/'clean-base-edit.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
    assert hashlib.sha256(model.read_bytes()).hexdigest()==before_hash
    target=OUT/'whale_maid_04_clean_base.vroid';assert not target.exists();shutil.copy2(saved['path'],target)
    async with client_for(Path(saved['path']),'clean-base-reopen') as (_,call):
        assert before=={d:await parameters(call,d) for d in before}
        assert protected=={cat:await selected(call,cat) for cat in protected}
        assert await selected(call,'Onepiece')==[] and await selected(call,'ArmAccessory')==[]
        token=(await call('list_face_params'))['model_token']
        body=await call('capture_body_reference',{'expected_model':token,'label':'Clean base body, socks and shoes retained'})
        shutil.copy2(body['path'],OUT/'clean_body_reference.json')
        record.update(cold_reopen_passed=True,source_unchanged=True,source_sha256=before_hash,body_reference=body)
    (OUT/'clean-base-acceptance.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
    return Path(saved['path'])

async def wear(base):
    filename='whale_maid_fitted_full_v02.xwear'
    async with client_for(base,'clean-wear-edit') as (_,call):
        status=await call('get_wear_status')
        status=await call('open_wear_project',{'filename':base.name,'expected_wear':status['wear_token'],'discard_unsaved':True})
        status=await call('import_xwear',{'filename':filename,'expected_wear':status['wear_token']})
        token=status['wear_token'];snap=await call('get_wear_snapshot',{'expected_wear':token})
        capture=await call('capture_wear_review',{'expected_wear':token,'views':['front','side','back'],'size':1024})
        saved=await call('save_wear_project',{'expected_wear':token,'filename':'whale-maid-clean-wear-'+uuid.uuid4().hex+'.xroid'})
        record={'edit':snap,'capture':capture,'save':saved}
    async with client_for(base,'clean-wear-reopen') as (_,call):
        status=await call('get_wear_status')
        status=await call('open_wear_project',{'filename':Path(saved['path']).name,'expected_wear':status['wear_token'],'discard_unsaved':True})
        snap=await call('get_wear_snapshot',{'expected_wear':status['wear_token']})
        assert snap['base_model']==record['edit']['base_model']
        assert len(snap['items'])==1
        meshes=[r for item in snap['items'] for instance in item['instances'] for r in instance['renderers']]
        assert len(meshes)==73 and sum(r['triangles'] for r in meshes)==26651
        assert any(r['name']=='Body' and r['active'] and r['enabled'] for r in snap['base_model']['renderers'])
        capture=await call('capture_wear_review',{'expected_wear':status['wear_token'],'views':['front','side','back'],'size':1024})
        record.update(passed=True,reopen=snap,reopen_capture=capture)
    dest=OUT/'whale_maid_clean_wear_v01.xroid';assert not dest.exists();shutil.copy2(saved['path'],dest)
    (OUT/'clean-wear-acceptance.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'passed':True,'base':str(base),'xroid':str(dest),'meshes':73}),flush=True)

async def main():
    OUT.mkdir(exist_ok=True)
    if '--wear-only' in sys.argv:
        record=json.loads((OUT/'clean-base-acceptance.json').read_text(encoding='utf8'))
        assert record['passed'] and record['cold_reopen_passed']
        base=Path(record['save']['path'])
        assert hashlib.sha256(base.read_bytes()).hexdigest()==record['save']['sha256']
    else:base=await clean_base()
    await wear(base)
if __name__=='__main__':asyncio.run(main())
