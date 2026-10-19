import argparse,asyncio,json,sys
from pathlib import Path
from capture_quality_acceptance import dump
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import clean_native_clothing as lifecycle
async def main(args):
    out=args.output.resolve();out.mkdir(exist_ok=False);lifecycle.OUT=out
    original=lifecycle.StdioServerParameters
    def parameters(**kw):
        kw['args']=[str(Path(__file__).with_name('color_visual_probe_server.py')),*kw['args'][2:]]
        kw['env']['COLOR_SKIP_SELECTION']='1' if args.skip_selection else '0'
        return original(**kw)
    lifecycle.StdioServerParameters=parameters
    record={}
    async with lifecycle.client_for(args.model,'probe') as (_,call):
        token=(await call('list_face_params'))['model_token']
        record['before']=await call('capture_review',{'expected_model':token,'views':['front'],'size':1024,'quality':'high'})
        record['colors']=await call('list_parameters',{'domain':'colors','limit':500})
        record['after']=await call('capture_review',{'expected_model':token,'views':['front'],'size':1024,'quality':'high'})
        record['repeat']=await call('capture_review',{'expected_model':token,'views':['front'],'size':1024,'quality':'high'})
    for phase in ['before','after','repeat']:
        data=Path(record[phase]['images']['front']['path']).read_bytes();(out/(phase+'.png')).write_bytes(data)
        print(phase,len(data),flush=True)
    dump(out/'probe.json',record)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--skip-selection',action='store_true')
    asyncio.run(main(p.parse_args()))
