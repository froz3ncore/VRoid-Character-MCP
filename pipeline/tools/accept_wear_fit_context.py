"""Exercise the 3D context MCP on real shoes, back mounts and blue head bow."""
import argparse,asyncio,hashlib,json,shutil
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1]
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
async def main(a):
    out=a.out.resolve();assert out.is_relative_to(ROOT/'projects/whale-maid');out.mkdir(parents=True,exist_ok=False);native.OUT=out
    record=json.loads(a.record.read_text(encoding='utf8'));saved=record['save'];assert digest(saved['path'])==saved['sha256']
    base=json.loads(Path(record['base_record']).read_text(encoding='utf8'))['save'];rows=[]
    async with native.client_for(Path(base['path']),'fit-context-acceptance') as (client,call):
        await asyncio.sleep(a.initial_settle_seconds);state=await call('get_wear_status');state=await call('open_wear_project',{'expected_wear':state['wear_token'],'filename':Path(saved['path']).name,'discard_unsaved':True})
        token=state['wear_token'];snapshot=await call('get_wear_snapshot',{'expected_wear':token});item=snapshot['items'][0]
        tools=await client.list_tools();assert any(t.name=='inspect_wear_fit_context' for t in tools.tools)
        names=[r['name'] for inst in item['instances'] for r in inst['renderers']]
        main_mesh=next(n for n in names if n.startswith('FIT_T001'))
        cases=[('shoes','feet',[n for n in names if n.startswith('FIT_ACCESSORY_Shoe_')],None),
               ('back','waist_back',[main_mesh]+[n for n in names if n.startswith(('FIT_NEW_Bow','FIT_ACCESSORY_WhaleTail_'))],main_mesh),
               ('head-bow','head',[n for n in names if n.startswith('FIT_ACCESSORY_Head_BackBow_')],None)]
        cases=[case for case in cases if case[0] in a.cases]
        for label,region,selected,target in cases:
            args={'expected_wear':token,'item_id':item['id'],'mesh_names':selected,'region':region,'sample_limit':128}
            if target:args['target_mesh_name']=target
            report=await call('inspect_wear_fit_context',args)
            assert not report['model_modified'] and report['pose_source']=='native_edit'
            assert all(g['renderer_id'] and g['thickness']['attempted_rays']>0 for g in report['garments'])
            assert digest(report['debug_glb']['path'])==report['debug_glb']['sha256']
            shutil.copy2(report['report_path'],out/(label+'.json'));shutil.copy2(report['debug_glb']['path'],out/(label+'.glb'))
            shutil.copy2(report['raw_reference']['path'],out/(label+'-raw-reference.json'))
            rows.append({'case':label,'meshes':len(report['garments']),'snapshot_frame':report['frame'],'report':str(out/(label+'.json')),'diagnostic_3d':str(out/(label+'.glb'))})
    assert digest(saved['path'])==saved['sha256']
    (out/'acceptance.json').write_text(json.dumps({'passed':True,'mcp_tool':'inspect_wear_fit_context','native_tools':len(tools.tools),'source_saved':saved,'source_unchanged':True,'screenshot_calls':0,'cases':rows},ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'passed':True,'native_tools':len(tools.tools),'cases':rows},ensure_ascii=False),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--record',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--initial-settle-seconds',type=float,default=5.)
    p.add_argument('--cases',nargs='+',choices=['shoes','back','head-bow'],default=['shoes','back','head-bow'],help='Measure only changed regions; default retains all three')
    a=p.parse_args();assert 0<=a.initial_settle_seconds<=10;asyncio.run(main(a))
