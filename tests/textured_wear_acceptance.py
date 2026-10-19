"""Actual stdio tools: textured/spring clothing import, native views, save and cold reopen."""
import asyncio,base64,hashlib,json,os,shutil,sys,uuid
from datetime import timedelta
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[2];PROJECT=ROOT/'VRoid-MCP';LAB=ROOT/'lab-test'
OUT=ROOT/'projects/whale-maid/xwear-textured-v01'
INPUT=sys.argv[1] if len(sys.argv)>1 else 'whale_maid_skirt_sample_v02.xwear'
def summary(snapshot):
    assert snapshot['active'] and len(snapshot['items'])==1
    renderers=[r for item in snapshot['items'] for i in item['instances'] for r in i['renderers']]
    joints={b['name']:b['spring_joint'] for item in snapshot['items'] for s in item['skeletons'] for b in s['bones'] if b['spring_joint']}
    colliders={b['name']:b['spring_collider'] for item in snapshot['items'] for s in item['skeletons'] for b in s['bones'] if b['spring_collider']}
    colliders.update({c['name']:c for item in snapshot['items'] for s in item['skeletons'] for c in s['colliders'] if c['name'].startswith('WM_XWearCollider_')})
    textures=[m['main_texture'] for r in renderers for m in r['materials'] if m and m['main_texture']]
    assert len(joints)==68,(len(joints),snapshot)
    assert len(colliders)==5,(len(colliders),snapshot)
    assert all(t['width']>0 and t['height']>0 for t in textures)
    assert textures and all(r['enabled'] and r['active'] for r in renderers)
    return {'renderers':len(renderers),'triangles':sum(r['triangles'] for r in renderers),
            'textures':textures,'spring_joints':joints,'colliders':colliders}
async def phase(filename,edit):
    params=StdioServerParameters(command=sys.executable,args=['-m','vroid_mcp.server','--lab',str(LAB),'--model',str(LAB/'saves/whale_maid_03_test_base.vroid')],cwd=str(PROJECT),
        env=dict(os.environ,TEMP=str(ROOT/'work/temp'),TMP=str(ROOT/'work/temp')))
    label='edit' if edit else 'reopen'
    with (OUT/(INPUT+'.'+label+'.log')).open('w',encoding='utf8') as log:
        async with stdio_client(params,errlog=log) as (read,write):
            async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=240)) as client:
                await client.initialize();catalog=await client.list_tools()
                assert {'get_wear_snapshot','capture_wear_review'}<={t.name for t in catalog.tools}
                async def call(name,args=None,error=False):
                    result=await client.call_tool(name,args or {})
                    assert bool(result.isError)==error,(name,result)
                    if error:return str(result)
                    if name=='capture_wear_review':
                        manifest=json.loads(next(c.text for c in result.content if c.type=='text'))
                        assert len([c for c in result.content if c.type=='image'])==3
                        for record in manifest['images']:shutil.copy2(record['path'],OUT/(INPUT+'.'+label+'.'+record['view']+'.png'))
                        return manifest
                    return result.structuredContent or json.loads(result.content[0].text)
                status=await call('get_wear_status')
                status=await call('open_wear_project',{'filename':filename,'expected_wear':status['wear_token'],'discard_unsaved':True})
                if edit:status=await call('import_xwear',{'filename':INPUT,'expected_wear':status['wear_token']})
                token=status['wear_token']
                await call('get_wear_snapshot',{'expected_wear':'stale'},True)
                snap=await call('get_wear_snapshot',{'expected_wear':token})
                (OUT/(INPUT+'.'+label+'.snapshot.json')).write_text(json.dumps(snap,ensure_ascii=False,indent=2),encoding='utf8')
                measured=summary(snap)
                capture=await call('capture_wear_review',{'expected_wear':token,'views':['front','side','back'],'size':768})
                report={'snapshot':snap,'summary':measured,'capture':capture,'tools':len(catalog.tools)}
                if edit:
                    playing=await call('set_wear_animation',{'expected_wear':token,'playing':True})
                    assert playing['animation_ready']
                    await call('get_wear_snapshot',{'expected_wear':token},True)
                    await asyncio.sleep(2)
                    progressed=await call('get_wear_status')
                    advanced=None
                    if playing['animation_time'] is not None and progressed['animation_time'] is not None:
                        advanced=progressed['animation_time']>playing['animation_time']
                        assert advanced
                    report['preview']={'ready':playing['animation_ready'],'start_time':playing['animation_time'],
                        'end_time':progressed['animation_time'],'time_advanced':advanced}
                    await call('set_wear_animation',{'expected_wear':token,'playing':False})
                    report['save']=await call('save_wear_project',{'expected_wear':token,'filename':'textured-wear-'+uuid.uuid4().hex+'.xroid'})
                return report
async def main():
    source=ROOT/'projects/whale-maid/source/whale_maid_03_test_base.vroid';before=hashlib.sha256(source.read_bytes()).hexdigest()
    inp=OUT/INPUT;staged=LAB/'saves'/INPUT
    if staged.exists():assert staged.read_bytes()==inp.read_bytes()
    else:shutil.copy2(inp,staged)
    edit=await phase('whale_maid_03_test_base.vroid',True)
    reopen=await phase(Path(edit['save']['path']).name,False)
    assert edit['summary']==reopen['summary']
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
    report={'passed':True,'edit':edit,'cold_reopen':reopen,'source_unchanged':True,
      'limits':['Native static views must be inspected separately','Spring joint presence is not simulation quality proof',
                'No complete VRM export or Godot runtime acceptance']}
    (OUT/(INPUT+'.native-acceptance.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'passed':True,'tools':edit['tools'],'meshes':edit['summary']['renderers'],'joints':len(edit['summary']['spring_joints']),'save':edit['save']['path']}),flush=True)
asyncio.run(main())
