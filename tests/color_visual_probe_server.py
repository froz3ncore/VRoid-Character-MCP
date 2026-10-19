"""Test-only camera/renderer state around native color listing."""
import json,os,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vroid_mcp import server
from vroid_mcp.runtime import Runtime,PROJECT

class VisualRuntime(Runtime):
    def start(self):
        original=Path.read_text
        def read(path,*a,**kw):
            source=original(path,*a,**kw)
            if path==PROJECT/'agent/parameters.js' and os.environ.get('COLOR_SKIP_SELECTION')=='1':
                source=source.replace("        selectHairCategory(m,'HairSet');",'        // Test: keep current hair category')
            if path==PROJECT/'agent/operations.js':
                source=source.replace('const operations={',r'''const operations={test_color_visual_state(){
                    const m=model(),face=m.face.method('GetFaceSMR').invoke(),origin=face.method('get_transform').invoke().method('get_parent').invoke();
                    const body=m.main.method('get_GlobalBus').invoke().method('get_Common3D').invoke().method('get_AvatarCamera').invoke().field('_body').value;
                    const cam=body.field('_templateCamera').value.method('get_PrimaryCamera').invoke();
                    const hair=selector(m,'hair'),selected=hair.tryMethod('get_SelectedCategory')?hair.method('get_SelectedCategory').invoke():null;
                    const rows=[];
                    function walk(t){const go=t.method('get_gameObject').invoke(),r=go.method('GetComponent',1).overload('System.Type').invoke(core('SkinnedMeshRenderer').type.object);
                        if(!r.handle.isNull())rows.push({name:text(t.method('get_name').invoke()),enabled:r.method('get_enabled').invoke(),layer:go.method('get_layer').invoke(),active:go.method('get_activeInHierarchy').invoke()});
                        for(let i=0;i<t.method('get_childCount').invoke();i++)walk(t.method('GetChild').invoke(i));}
                    walk(origin);
                    return {frame:state.frame,mask:cam.method('get_cullingMask').invoke(),camera_enabled:cam.method('get_enabled').invoke(),
                        selected_hair:selected&&!selected.handle.isNull()?text(selected.method('get_TranslationKey').invoke()):null,renderers:rows};
                },''')
            return source
        with patch.object(Path,'read_text',read):super().start()
    async def parameter_call(self,*a,**kw):
        result=await super().parameter_call(*a,**kw)
        if (a[1] or {}).get('domain')=='colors':
            data=await self._call('test_color_visual_state')
            with (self.lab/'color-visual-states.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(data)+'\n')
        return result
server.Runtime=VisualRuntime
if __name__=='__main__':server.main()
