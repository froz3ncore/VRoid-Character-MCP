"""Read native capture capabilities in the owned lab-test process only."""
from pathlib import Path
import json,sys
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vroid_mcp import server
from vroid_mcp.runtime import Runtime,PROJECT

class ProbeRuntime(Runtime):
    async def _call(self,operation,args=None):
        for attempt in range(3):
            try:return await super()._call(operation,args)
            except Exception as error:
                if operation!='status' or 'MAIN_THREAD_TIMEOUT: not executed' not in str(error) or attempt==2:raise
    def start(self):
        original=Path.read_text
        def read(path,*a,**kw):
            source=original(path,*a,**kw)
            if path==PROJECT/'agent/operations.js':
                source=source.replace('const operations={', '''const operations={test_capture_probe(args){
                    const m=model(args.expected_model),photo=m.root.field('obsoleteLegacyPhotoBoothViewModel').value;
                    const describe=c=>({type:c.type.name,fields:c.fields.map(f=>({name:f.name,type:f.type.name})),
                        methods:c.methods.filter(v=>/descriptor|antiAliasing|allowMSAA|ResolveAnti|MSAASample|targetTexture|Render$|\.ctor|sRGB|bindMS/.test(v.name)).map(v=>({name:v.name,parameters:v.parameters.map(p=>p.type.name),returns:v.returnType.name}))});
                    const cam=photo.method('get_PhotoBoothCamera').invoke();
                    return {types:['RenderTexture','RenderTextureDescriptor','Camera','SystemInfo'].map(n=>describe(core(n))),photo:cam.handle.isNull()?null:describe(cam.class)};
                },''')
            return source
        with patch.object(Path,'read_text',read):super().start()
    async def initialize(self,*a,**kw):
        result=await super().initialize(*a,**kw)
        await self._call('set_preview_mode',{'expected_model':result['model_token'],'mode':'photo'})
        await self._settle()
        data=await self._call('test_capture_probe')
        (self.lab/'capture-quality-capabilities.json').write_text(json.dumps(data,indent=2),encoding='utf8')
        return result
server.Runtime=ProbeRuntime
if __name__=='__main__':server.main()
