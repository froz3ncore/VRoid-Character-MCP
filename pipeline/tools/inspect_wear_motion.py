"""Read native preview ownership in an isolated runtime; never alter saved assets."""
import asyncio,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'VRoid-MCP'))
from vroid_mcp.runtime import Runtime
OUT=ROOT/'projects/whale-maid/target-fit-v02'
async def main():
    base=json.loads((ROOT/'projects/whale-maid/clean-wear-v01/clean-base-acceptance.json').read_text(encoding='utf8'))['save']['path']
    saved=json.loads((OUT/'refined-wear-acceptance.json').read_text(encoding='utf8'))['save']['path']
    runtime=Runtime(ROOT/'lab-test')
    try:
        await asyncio.to_thread(runtime.start);await runtime.initialize(model_file=Path(base))
        status=await runtime.wear_status()
        status=await runtime.open_wear_project(Path(saved).name,status['wear_token'],True)
        stopped=await runtime._call('wear_debug')
        playing=await runtime.wear_edit('set_wear_animation',{'expected_wear':status['wear_token'],'playing':True})
        moving=await runtime._call('wear_debug')
        await asyncio.sleep(1)
        later=await runtime.wear_status()
        await runtime.wear_edit('set_wear_animation',{'expected_wear':status['wear_token'],'playing':False})
        (OUT/'native-motion-discovery.json').write_text(json.dumps({'stopped':stopped,'playing':playing,'moving':moving,'later':later},ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps({'playing':playing,'later':later,'preview':moving['preview'],'preview_model':moving['preview_model']},ensure_ascii=False),flush=True)
    finally:await asyncio.to_thread(runtime.close)
if __name__=='__main__':asyncio.run(main())
