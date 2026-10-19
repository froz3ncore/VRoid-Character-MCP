"""Read-only native texture canvas API discovery, isolated from hair authoring."""
import asyncio,hashlib,json
from pathlib import Path
import clean_native_clothing as native
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'work/cosmetics-texture-api-v01'
native.PROJECT=ROOT/'work/cosmetics-mcp-v01';native.LAB=ROOT/'lab-clothing-fit-v17';native.OUT=OUT
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf8')
async def main():
    OUT.mkdir(exist_ok=False)
    model=Path(json.loads((ROOT/'projects/whale-maid/accessory-refinement-v02/chest-skirt-v17b/isolated-base-record.json').read_text(encoding='utf8'))['save']['path']);sha=hashlib.sha256(model.read_bytes()).hexdigest()
    searches={};inspected={}
    async with native.client_for(model,'texture-api') as (client,call):
        await call('list_face_params');await asyncio.sleep(5)
        assert 'inspect_native_api' in {t.name for t in (await client.list_tools()).tools}
        for assembly in ('VRoid.Studio','VRoidCore'):
            for word in ('textureeditor','texturelayer','paint','canvas','nail','overlay'):
                result=await call('search_native_classes',{'assembly':assembly,'substring':word});searches[assembly+':'+word]=result['matches'];write(OUT/'searches.json',searches)
                print(json.dumps({'search':assembly+':'+word,'count':len(result['matches'])}),flush=True)
        targets=[]
        for key,names in searches.items():
            for name in names:
                if '<' in name or name.endswith(('View','Test')):continue
                if any(x in name.lower() for x in ('viewmodel','layermodel','textureeditor','painteditor','layercommand','texturelayer','canvasmodel','texturemodel','overlaymodel','importtexture','exporttexture')):
                    pair=(key.split(':')[0],name)
                    if pair not in targets:targets.append(pair)
        for assembly,name in targets[:45]:
            try:inspected[assembly+':'+name]=await call('inspect_native_api',{'assembly':assembly,'class_name':name})
            except Exception as e:inspected[assembly+':'+name]={'error':str(e)[:300]}
            write(OUT/'inspected.json',inspected)
        print(json.dumps({'inspected':list(inspected)},ensure_ascii=True),flush=True)
    assert hashlib.sha256(model.read_bytes()).hexdigest()==sha
    write(OUT/'acceptance.json',{'passed':True,'read_only':True,'source_sha256':sha,'source_unchanged':True})
if __name__=='__main__':asyncio.run(main())
