"""Inject synchronous state checks and encode failure into owned native tests."""
from pathlib import Path
import json,sys
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vroid_mcp import server
from vroid_mcp.runtime import Runtime,PROJECT

STATE = r'''
    function captureTestState(){
        const find=core('Object').methods.find(m=>m.isStatic&&m.name==='FindObjectsOfType'&&m.parameters.length===1&&m.parameters[0].type.name==='System.Type');
        const objects=n=>[...find.invoke(core(n).type.object)],id=o=>o.handle.toString();
        const cameras=objects('Camera').map(c=>({id:id(c),enabled:c.method('get_enabled').invoke(),
            target:id(c.method('get_targetTexture').invoke()),mask:c.method('get_cullingMask').invoke(),
            clear:c.method('get_clearFlags').invoke().field('value__').value,fov:c.method('get_fieldOfView').invoke()})).sort((a,b)=>a.id.localeCompare(b.id));
        const lights=objects('Light').map(l=>({id:id(l),mask:l.method('get_cullingMask').invoke()})).sort((a,b)=>a.id.localeCompare(b.id));
        const renderers=objects('SkinnedMeshRenderer').map(r=>({id:id(r),enabled:r.method('get_enabled').invoke(),
            layer:r.method('get_gameObject').invoke().method('get_layer').invoke()})).sort((a,b)=>a.id.localeCompare(b.id));
        const temporary=['GameObject','RenderTexture','Texture2D'].flatMap(n=>objects(n).filter(o=>/MCP.*(capture|settings backup)/i.test(text(o.method('get_name').invoke())||'')).map(id)).sort();
        return {active:id(core('RenderTexture').method('get_active').invoke()),cameras,lights,renderers,temporary};
    }
'''

class DiagnosticRuntime(Runtime):
    def start(self):
        original=Path.read_text
        def read(path,*a,**kw):
            source=original(path,*a,**kw)
            if path==PROJECT/'agent/capture_quality.js':
                source=source.replace('encode(){',"encode(){if(globalThis.captureTestFailEncode)throw Error('TEST_CAPTURE_ENCODE_FAILURE');")
            if path==PROJECT/'agent/operations.js':
                source=source.replace('const operations={',STATE+'\nconst operations={')
                source=source.replace('return operations[name](args);',r'''
                    if(!['screenshot','wear_capture','wear_motion_sample'].includes(name))return operations[name](args);
                    const before=captureTestState();globalThis.captureTestFailEncode=!!args.test_fail_encode;
                    let result=null;
                    try{result=operations[name](args);return result;}
                    finally{
                        globalThis.captureTestFailEncode=false;
                        const after=captureTestState(),same=JSON.stringify(before)===JSON.stringify(after);
                        send({event:'capture-resource-validation',operation:name,injected_failure:!!args.test_fail_encode,passed:same,before,after});
                        if(!same)throw Error('CAPTURE_STATE_NOT_RESTORED: '+JSON.stringify({before,after}));
                        if(result)result.quality.resource_state_restored=true;
                    }
                ''')
            return source
        with patch.object(Path,'read_text',read):super().start()

    async def _call(self,operation,args=None):
        # Read-only startup polling may time out before the first UI frame.
        if operation=='status':
            for attempt in range(3):
                try:return await super()._call(operation,args)
                except Exception as error:
                    if 'MAIN_THREAD_TIMEOUT: not executed' not in str(error) or attempt==2:raise
        if operation in ('screenshot','wear_capture','wear_motion_sample'):
            key=(operation,args.get('view'))
            checked=getattr(self,'_failure_checked',set())
            if key not in checked:
                checked.add(key);self._failure_checked=checked
                try:await super()._call(operation,{**args,'test_fail_encode':True})
                except Exception as error:
                    if 'TEST_CAPTURE_ENCODE_FAILURE' not in str(error):raise
                else:raise AssertionError('Injected failure did not occur')
        result=await super()._call(operation,args)
        if operation=='screenshot':
            with (self.lab/'capture-quality-screenshots.jsonl').open('a',encoding='utf8') as f:
                f.write(json.dumps({k:v for k,v in result.items() if k!='base64'})+'\n')
        return result

server.Runtime=DiagnosticRuntime
if __name__=='__main__':server.main()
