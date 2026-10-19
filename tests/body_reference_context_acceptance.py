import asyncio,json,os,sys
from pathlib import Path
from datetime import timedelta
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[2];PROJECT=ROOT/'VRoid-MCP';LAB=ROOT/'lab-test';OUT=ROOT/'projects/whale-maid/target-body'
async def main():
    params=StdioServerParameters(command=sys.executable,args=['-m','vroid_mcp.server','--lab',str(LAB),'--model',str(LAB/'saves/whale_maid_03_test_base.vroid')],cwd=str(PROJECT),env=dict(os.environ,TEMP=str(ROOT/'work/temp'),TMP=str(ROOT/'work/temp')))
    with (OUT/'mcp-body-context.log').open('w',encoding='utf8') as log:
        async with stdio_client(params,errlog=log) as (read,write):
            async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=240)) as client:
                await client.initialize()
                async def call(name,args=None):
                    result=await client.call_tool(name,args or {});assert not result.isError,result
                    return result.structuredContent or json.loads(result.content[0].text)
                face=await call('list_face_params');state=await call('get_wear_status')
                opened=await call('open_wear_project',{'filename':'whale_maid_03_test_base.vroid','expected_wear':state['wear_token'],'discard_unsaved':True})
                assert opened['active']
                rejected=await client.call_tool('capture_body_reference',{'expected_model':face['model_token']})
                error=' '.join(c.text for c in rejected.content if c.type=='text')
                assert rejected.isError and 'DRESS_UP_ACTIVE' in error,error
                result={'passed':True,'dress_up_body_reference_rejected':True,'error':error,'lab':str(LAB)}
                (OUT/'mcp-body-context-acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(result),flush=True)
asyncio.run(main())
