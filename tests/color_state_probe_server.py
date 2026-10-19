"""Read native color/accessor metadata in the owned lab-test process."""
from pathlib import Path
import json,sys
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vroid_mcp import server
from vroid_mcp.runtime import Runtime,PROJECT

class ProbeRuntime(Runtime):
    def start(self):
        original=Path.read_text
        def read(path,*a,**kw):
            source=original(path,*a,**kw)
            if path==PROJECT/'agent/parameters.js':
                source=source.replace("    function colorEntries(vm,prefix,out){",r'''
                    function describeColor(o){
                        if(!o||o.handle.isNull())return null;
                        return {type:o.class.type.name,fields:o.class.fields.filter(f=>!f.isStatic).map(f=>({name:f.name,type:f.type.name})),
                            methods:o.class.methods.map(f=>({name:f.name,parameters:f.parameters.map(p=>p.type.name),returns:f.returnType.name}))};
                    }
                    function probeColor(s,c,sm){
                        const accessor=sm.tryMethod('get_Accessor')?sm.method('get_Accessor').invoke():null;
                        const keys={};
                        for(const name of ['_keysToSet','_keysToModify'])if(accessor&&accessor.tryField(name))keys[name]=seq(accessor.field(name).value).map(k=>({group:text(k.method('get_TransferableGroupType').invoke()),key:text(k.method('get_Key').invoke())}));
                        const values={};
                        for(const f of s.class.methods.filter(f=>f.name.startsWith('get_')&&f.parameters.length===0&&['System.Boolean','System.String','UnityEngine.Color'].includes(f.returnType.name))){
                            try{values[f.name]=read(s,f.name.slice(4),{'System.Boolean':'bool','System.String':'string','UnityEngine.Color':'color'}[f.returnType.name]);}catch(e){values[f.name]=String(e);}
                        }
                        const bindingValues=[];
                        for(const k of keys._keysToSet||[]){
                            try{
                                const single=cls('VRoid.Studio','VRoid.Studio.ColorSelection.Model.EditableElementColorAccessor').method('Create').overload('System.String','System.String','System.String').invoke(Il2Cpp.string(k.group),Il2Cpp.string(k.key),Il2Cpp.string(null));
                                const color=single.method('Get',1).invoke(model().engine);
                                bindingValues.push({...k,value:['r','g','b','a'].map(n=>color.field(n).value)});
                            }catch(e){bindingValues.push({...k,error:String(e)});}
                        }
                        return {selection:describeColor(c),sub:describeColor(s),model:describeColor(sm),accessor:describeColor(accessor),keys,values,bindingValues};
                    }
                    function colorEntries(vm,prefix,out){''')
                marker="format:'RGBA floats 0..1; sRGB'}));"
                source=source.replace(marker,marker+"\n                out[out.length-1].data.native_probe=probeColor(s,c,sm);",1)
            return source
        with patch.object(Path,'read_text',read):super().start()
    async def _call(self,operation,args=None):
        if operation=='status':
            for attempt in range(3):
                try:return await super()._call(operation,args)
                except Exception as error:
                    if 'MAIN_THREAD_TIMEOUT: not executed' not in str(error) or attempt==2:raise
        return await super()._call(operation,args)

server.Runtime=ProbeRuntime
if __name__=='__main__':server.main()
