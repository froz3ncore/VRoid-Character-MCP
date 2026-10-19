"""Real stdio MCP body reference, stale-token rejection, immutable source identity."""
import asyncio,json,os,sys,hashlib,shutil,uuid
from pathlib import Path
from datetime import timedelta
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[2];PROJECT=ROOT/'VRoid-MCP';LAB=ROOT/'lab-test'
OUT=ROOT/'projects/whale-maid/target-body';OUT.mkdir(exist_ok=True)
async def main():
    source=LAB/'saves/whale_maid_03_test_base.vroid';before=hashlib.sha256(source.read_bytes()).hexdigest()
    params=StdioServerParameters(command=sys.executable,args=['-m','vroid_mcp.server','--lab',str(LAB),'--model',str(source)],cwd=str(PROJECT),env=dict(os.environ,TEMP=str(ROOT/'work/temp'),TMP=str(ROOT/'work/temp')))
    with (OUT/'mcp-body-reference.log').open('w',encoding='utf8') as log:
        async with stdio_client(params,errlog=log) as (read,write):
            async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=180)) as client:
                await client.initialize();catalog=await client.list_tools()
                assert 'capture_body_reference' in {t.name for t in catalog.tools}
                face=await client.call_tool('list_face_params',{});assert not face.isError
                state=face.structuredContent or json.loads(face.content[0].text);token=state['model_token']
                stale=await client.call_tool('capture_body_reference',{'expected_model':'stale','label':'must fail'});assert stale.isError
                result=await client.call_tool('capture_body_reference',{'expected_model':token,'label':'Whale maid saved VRoid base for clothing fitting'});assert not result.isError,result
                result=result.structuredContent or json.loads(result.content[0].text)
                snapshot=Path(result['path']);target=OUT/'whale_maid_vroid_body_reference.json'
                recheck=target.exists()
                if recheck:target=OUT/('body-reference-recheck-'+uuid.uuid4().hex+'.json')
                shutil.copy2(snapshot,target)
                assert hashlib.sha256(target.read_bytes()).hexdigest()==result['sha256']
                assert hashlib.sha256(source.read_bytes()).hexdigest()==before
                report={'passed':True,'tools':len(catalog.tools),'stale_token_rejected':True,'source_vroid_sha256':before,'source_unchanged':True,'artifact':str(target),'capture':result}
                (OUT/('mcp-body-reference-recheck.json' if recheck else 'mcp-body-reference-acceptance.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
                print(json.dumps(report,ensure_ascii=False),flush=True)
asyncio.run(main())
