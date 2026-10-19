"""Read-only native shoe/heel/body-mask schema discovery in an owned lab."""
import argparse,asyncio,json,os,sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'VRoid-MCP'))
os.environ['TEMP']=os.environ['TMP']=str(ROOT/'work/temp')
from vroid_mcp.runtime import Runtime,PROJECT
PROBE=r'''shoe_constraints_probe(args){
    const describe=c=>({name:c.type.name,fields:c.fields.filter(f=>!f.isStatic).map(f=>({name:f.name,type:f.type.name})),
        methods:c.methods.map(m=>({name:m.name,static:m.isStatic,args:m.parameters.map(p=>({name:p.name,type:p.type.name})),returns:m.returnType.name,available:!m.virtualAddress.isNull()}))});
    const types=[];
    for(const assembly of Il2Cpp.domain.assemblies){
        if(/^(mscorlib|System|Unity|Mono|netstandard|Microsoft)/.test(assembly.name))continue;
        for(const c of assembly.image.classes){
            if(!/DrawableMesh|Mesh.*(Erase|Delete|Edit)|Erase.*Mesh|EditContext|EditPart|BaseModel.*Content|MeshAliveMark|BaseModelViewModel/i.test(c.type.name)||/[<>]/.test(c.type.name))continue;
            types.push({assembly:assembly.name,...describe(c)});
        }
    }
    const ref=state.refs['VRoid.Studio.XWear.Edit.ViewModel'];
    let wear=null;
    if(ref){const e=new Il2Cpp.Object(ptr(ref));wear={root:describe(e.class),context:describe(e.field('EditContext').value.class)};}
    return {types,wear,assemblies:Il2Cpp.domain.assemblies.map(a=>a.name),read_only:true};
},'''
class ProbeRuntime(Runtime):
    def start(self):
        original=Path.read_text
        def read(path,*args,**kwargs):
            source=original(path,*args,**kwargs)
            if path==PROJECT/'agent/operations.js':source=source.replace('const operations={','const operations={'+PROBE,1)
            return source
        with patch.object(Path,'read_text',read):super().start()
async def main(a):
    out=a.out.resolve();assert out.is_relative_to(ROOT/'projects/whale-maid') and not out.exists();out.mkdir(parents=True)
    record=json.loads((ROOT/'projects/whale-maid/accessory-refinement-v02/footwear-base/base-acceptance.json').read_text(encoding='utf8'))
    runtime=ProbeRuntime(ROOT/'lab-test')
    try:
        await asyncio.to_thread(runtime.start);await runtime.initialize(model_file=Path(record['save']['path']));result=await runtime._call('shoe_constraints_probe')
        (out/'types.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
        await asyncio.sleep(10)
        saved=json.loads((ROOT/'projects/whale-maid/accessory-refinement-v02/volume-candidate-v06/refined-wear-acceptance.json').read_text(encoding='utf8'))['save']
        status=await runtime.wear_status();await runtime.open_wear_project(Path(saved['path']).name,status['wear_token'],True)
        result=await runtime._call('shoe_constraints_probe')
        (out/'wear-types.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps({'read_only':True,'types':len(result['types']),'out':str(out)}),flush=True)
    finally:await asyncio.to_thread(runtime.close)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);asyncio.run(main(p.parse_args()))
