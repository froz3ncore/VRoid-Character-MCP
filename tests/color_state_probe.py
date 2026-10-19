import argparse,asyncio,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
import clean_native_clothing as lifecycle
async def main(out):
    out.mkdir(exist_ok=False);lifecycle.OUT=out
    original=lifecycle.StdioServerParameters
    def parameters(**kw):
        kw['args']=[str(Path(__file__).with_name('color_state_probe_server.py')),*kw['args'][2:]]
        return original(**kw)
    lifecycle.StdioServerParameters=parameters
    async with lifecycle.client_for(lifecycle.LAB/'saves'/lifecycle.SOURCE,'probe') as (_,call):
        await call('list_face_params')
        data=await call('list_parameters',{'domain':'colors','limit':500})
        (out/'colors.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps({'total':data['total'],'output':str(out)}),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    asyncio.run(main(p.parse_args().output))
