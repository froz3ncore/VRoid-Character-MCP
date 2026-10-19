"""Capture actual selected native walk/sit geometry using MCP, preserving the source XRoid."""
import asyncio,argparse,hashlib,json,shutil
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1]
async def main(args):
    out=args.out.resolve();assert out.is_relative_to(ROOT/'projects')
    out.mkdir(parents=True,exist_ok=False);native.OUT=out
    record=json.loads(args.record.read_text(encoding='utf8'));saved=record['save']
    source=Path(saved['path']);assert hashlib.sha256(source.read_bytes()).hexdigest()==saved['sha256']
    base=str(args.base_model.resolve()) if args.base_model else json.loads((ROOT/'projects/whale-maid/clean-wear-v01/clean-base-acceptance.json').read_text(encoding='utf8'))['save']['path']
    results=[]
    async with native.client_for(Path(base),'pose-reference') as (client,call):
        state=await call('get_wear_status');state=await call('open_wear_project',{'filename':source.name,'expected_wear':state['wear_token'],'discard_unsaved':True})
        token=state['wear_token'];snap=await call('get_wear_snapshot',{'expected_wear':token})
        assert len(snap['items'])==1,'Choose an assembly containing exactly the intended garment item'
        item=snap['items'][0];available=[r['name'] for i in item['instances'] for r in i['renderers']]
        names=args.mesh or [name for name in available if name.startswith('FIT_T001')]
        assert names and len(set(names))==len(names) and all(name in available for name in names)
        await call('capture_wear_reference',{'expected_wear':token,'item_id':item['id'],'mesh_names':names,'preview':True},True)
        await call('set_wear_animation',{'expected_wear':token,'playing':True});await call('set_wear_animation',{'expected_wear':token,'playing':False})
        clips=(await call('list_wear_preview_clips',{'expected_wear':token}))['clips']
        try:
            for case,clip_name in [('sit','shot_sitting'),('walk','WALK00_F')]:
                if case not in args.cases:continue
                clip=next(c for c in clips if c['name']==clip_name)
                await call('select_wear_preview_clip',{'expected_wear':token,'clip_id':clip['id']})
                await call('set_wear_animation',{'expected_wear':token,'playing':True})
                await asyncio.sleep(args.settle_seconds)
                await call('capture_wear_reference',{'expected_wear':token,'item_id':item['id'],'mesh_names':names},True)
                captured=await call('capture_wear_reference',{'expected_wear':token,'item_id':item['id'],'mesh_names':names,'preview':True})
                shutil.copy2(captured['path'],out/(case+'-reference.json'))
                motion=await call('capture_wear_motion',{'expected_wear':token,'samples':5,'interval_seconds':.15,'view':'side','size':768})
                folder=out/case;folder.mkdir()
                for i,image in enumerate(motion['images']):shutil.copy2(image['path'],folder/('frame-%02d.png'%i))
                shutil.copy2(motion['manifest_path'],folder/'motion.json')
                results.append({'case':case,'reference':captured,'motion':motion['summary'],'selected':clip_name})
                await call('set_wear_animation',{'expected_wear':token,'playing':False})
        finally:
            state=await call('get_wear_status')
            if state['animation_playing']:await call('set_wear_animation',{'expected_wear':token,'playing':False})
            await call('select_wear_preview_clip',{'expected_wear':token,'clip_id':None})
    assert hashlib.sha256(source.read_bytes()).hexdigest()==saved['sha256']
    (out/'acceptance.json').write_text(json.dumps({'passed':True,'source_unchanged':True,'cases':results},ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'passed':True,'cases':[r['case'] for r in results],'out':str(out)},ensure_ascii=False),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--record',type=Path,default=ROOT/'projects/whale-maid/target-fit-v03/final-wear/refined-wear-acceptance.json')
    p.add_argument('--out',type=Path,required=True);p.add_argument('--cases',nargs='+',choices=['sit','walk'],default=['sit','walk'])
    p.add_argument('--mesh',action='append',help='Exact renderer name; repeat for multiple meshes')
    p.add_argument('--base-model',type=Path,help='Explicit startup model for a different character fixture')
    p.add_argument('--settle-seconds',type=float,default=1.)
    args=p.parse_args();assert 0<=args.settle_seconds<=10
    asyncio.run(main(args))
