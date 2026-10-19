import asyncio,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
import clean_native_clothing as lifecycle

async def main():
    lifecycle.OUT=lifecycle.ROOT/'evidence/capture-quality-probe-v04'
    lifecycle.OUT.mkdir(exist_ok=False)
    original=lifecycle.StdioServerParameters
    def params(**kw):
        kw['args']=[str(Path(__file__).with_name('capture_quality_probe_server.py')),*kw['args'][2:]]
        return original(**kw)
    lifecycle.StdioServerParameters=params
    async with lifecycle.client_for(lifecycle.LAB/'saves'/lifecycle.SOURCE,'probe') as (_,call):
        print(await call('get_status'),flush=True)
asyncio.run(main())
