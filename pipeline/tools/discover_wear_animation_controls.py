"""Read native export/preview animation surfaces without changing saved assets."""
import asyncio,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'VRoid-MCP'))
from vroid_mcp.runtime import Runtime
OUT=ROOT/'projects/whale-maid/target-fit-v03'
async def main():
    base=json.loads((ROOT/'projects/whale-maid/clean-wear-v01/clean-base-acceptance.json').read_text(encoding='utf8'))['save']['path']
    saved=json.loads((OUT/'refined-wear-acceptance.json').read_text(encoding='utf8'))['save']['path']
    r=Runtime(ROOT/'lab-test')
    try:
        await asyncio.to_thread(r.start);await r.initialize(model_file=Path(base))
        s=await r.wear_status();s=await r.open_wear_project(Path(saved).name,s['wear_token'],True)
        await r.wear_edit('set_wear_animation',{'expected_wear':s['wear_token'],'playing':True})
        result=await r._call('wear_motion_debug',{'expected_wear':s['wear_token']})
        (OUT/'wear-animation-discovery.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
        await r.wear_edit('set_wear_animation',{'expected_wear':s['wear_token'],'playing':False})
        print(json.dumps(result,ensure_ascii=True),flush=True)
    finally:await asyncio.to_thread(r.close)
if __name__=='__main__':asyncio.run(main())
