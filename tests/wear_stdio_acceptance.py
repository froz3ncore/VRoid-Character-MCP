"""Real MCP -> native Dress-up -> save -> fresh-process reopen acceptance.

Uses only lab-test, pre-existing local fixtures, and unique output filenames.
"""
import asyncio,json,os,sys,uuid
from datetime import timedelta
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT=Path(__file__).resolve().parents[2]
PROJECT=ROOT/'VRoid-MCP'
LAB=ROOT/'lab-test'
OUTPUT=ROOT/'projects/whale-maid/xwear-test'

async def phase(filename, reopen=False):
    env=dict(os.environ,TEMP=str(ROOT/'work/temp'),TMP=str(ROOT/'work/temp'))
    params=StdioServerParameters(command=sys.executable,args=['-m','vroid_mcp.server','--lab',str(LAB)],cwd=str(PROJECT),env=env)
    with (OUTPUT/('wear-stdio-reopen.log' if reopen else 'wear-stdio-edit.log')).open('w',encoding='utf8') as log:
        async with stdio_client(params,errlog=log) as (read,write):
            async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=240)) as client:
                await client.initialize()
                listing=await client.list_tools()
                required={'get_wear_status','open_wear_project','import_xwear','set_wear_fit','set_wear_animation','save_wear_project'}
                assert required<={t.name for t in listing.tools}
                if '--catalog-only' in sys.argv:
                    return {'tool_count':len(listing.tools),'wear_tools':sorted(required)}
                async def call(name,args=None,error=False):
                    result=await client.call_tool(name,args or {})
                    assert bool(result.isError)==error,(name,result)
                    if error:return
                    return result.structuredContent or json.loads(result.content[0].text)
                initial=await call('get_wear_status')
                await call('open_wear_project',{'filename':'../outside.xroid','expected_wear':initial['wear_token'],'discard_unsaved':True},True)
                status=await call('open_wear_project',{'filename':filename,'expected_wear':initial['wear_token'],'discard_unsaved':True})
                initial_count=0 if filename.lower().endswith('.vroid') else (2 if reopen else 1)
                assert status['active'] and len(status['items'])==initial_count,status
                if '--vroid-open-only' in sys.argv:
                    return {'opened_vroid_in_dress_up':True,'state':status}
                expected_parts={'ApronPanel_NEW','ApronRuffle_NEW','ApronWaistBand_NEW'}
                assert all(set(item['parts'])==expected_parts for item in status['items'])
                if reopen:return {'reopened':True,'state':status,'tool_count':len(listing.tools)}
                token=status['wear_token']
                await call('set_wear_fit',{'expected_wear':initial['wear_token'],'item_id':status['items'][0]['id'],'fit_y':1.,'fit_z':1.2},True)
                status=await call('import_xwear',{'filename':'apron_wear_acceptance_v04.xwear','expected_wear':token})
                assert len(status['added_item_ids'])==1 and len(status['items'])==2
                item_id=status['added_item_ids'][0];token=status['wear_token']
                await call('set_wear_fit',{'expected_wear':token,'item_id':'wrong-id','fit_y':1.,'fit_z':1.2},True)
                fitted=await call('set_wear_fit',{'expected_wear':token,'item_id':item_id,'fit_y':1.,'fit_z':1.2})
                assert abs(next(i for i in fitted['items'] if i['id']==item_id)['fit_z']-1.2)<1e-5
                playing=await call('set_wear_animation',{'expected_wear':token,'playing':True})
                assert playing['animation_playing']
                same=await call('set_wear_animation',{'expected_wear':token,'playing':True})
                assert same['animation_playing']  # An idempotent setter, not blind toggle.
                await call('set_wear_fit',{'expected_wear':token,'item_id':item_id,'fit_y':1.,'fit_z':1.1},True)
                stopped=await call('set_wear_animation',{'expected_wear':token,'playing':False})
                assert not stopped['animation_playing']
                name='mcp-wear-acceptance-'+uuid.uuid4().hex+'.xroid'
                saved=await call('save_wear_project',{'filename':name,'expected_wear':token})
                assert saved['saved'] and Path(saved['path']).stat().st_size==saved['bytes']
                await call('save_wear_project',{'filename':name,'expected_wear':token},True)
                return {'saved':saved,'fitted_state':fitted,'tool_count':len(listing.tools),
                    'rejections':['path traversal','stale token','unknown item','fit during animation','overwrite'],
                    'animation_idempotent':True}

async def main():
    edited=await phase('whale_maid_03_test_base.vroid' if '--vroid-open-only' in sys.argv else 'whale_maid_apron_fit_v05.xroid')
    if '--vroid-open-only' in sys.argv:
        (OUTPUT/'mcp-vroid-base-acceptance.json').write_text(json.dumps(edited,indent=2),encoding='utf8')
        print(json.dumps(edited),flush=True);return
    if '--catalog-only' in sys.argv:
        print(json.dumps(edited),flush=True);return
    reopened=await phase(Path(edited['saved']['path']).name,True)
    result={'passed':True,'edit':edited,'cold_reopen':reopened,
        'limits':['Does not establish visual quality or collision freedom','VRM export and Godot runtime not tested',
                  'Fit sliders normalize to 1 on XRoid load; numeric slider equality is not a persistence test']}
    (OUTPUT/'mcp-wear-acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'passed':True,'tools':edited['tool_count'],'saved':edited['saved']['path'],'reopened_items':len(reopened['state']['items'])}),flush=True)

if __name__=='__main__':asyncio.run(main())
