"""Read actual face blendshape identities before implementing temporary closed-eye captures."""
import asyncio,json
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'projects/whale-maid/diagnostics/makeup-eye-shapes-v01';native.PROJECT=ROOT/'VRoid-MCP';native.LAB=ROOT/'lab-clothing-fit-v17';native.OUT=OUT
async def main():
 OUT.mkdir(exist_ok=False);saved=json.loads((ROOT/'projects/whale-maid/diagnostics/local-makeup-native-v02/saved.json').read_text(encoding='utf8'))
 async with native.client_for(Path(saved['path']),'shapes') as (_,call):
  token=(await call('list_face_params'))['model_token'];result=await call('inspect_texture_renderers',{'expected_model':token});(OUT/'bindings.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
  face=next(r for r in result['renderers'] if r['name']=='Face');print(json.dumps([s for s in face['blend_shapes'] if 'close' in s['name'].lower()],ensure_ascii=False),flush=True)
if __name__=='__main__':asyncio.run(main())
