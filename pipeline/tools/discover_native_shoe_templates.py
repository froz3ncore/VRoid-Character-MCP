"""Read-only clothing-template API discovery in an isolated supported VRoid."""
import argparse,asyncio,json,os,sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'VRoid-MCP'))
os.environ['TEMP']=os.environ['TMP']=str(ROOT/'work/temp')
from vroid_mcp.runtime import Runtime,PROJECT
PROBE=r'''shoe_template_schema(args){
 const describe=c=>({name:c.type.name,fields:c.fields.filter(f=>!f.isStatic).map(f=>({name:f.name,type:f.type.name})),methods:c.methods.map(m=>({name:m.name,args:m.parameters.map(p=>({name:p.name,type:p.type.name})),returns:m.returnType.name}))});
 const m=model(),editor=m.root.method('get_ClothingEditor').invoke(),types=[];
 for(const a of Il2Cpp.domain.assemblies){
  if(!/VRoid/.test(a.name))continue;
  for(const c of a.image.classes){
   if(!/VRoid\.Studio\.ClothingEditor/.test(c.type.name)||/[<>]/.test(c.type.name))continue;
   if(/Template|Category|InstanceSelector|ViewModel$/.test(c.type.name))types.push(describe(c));
  }
 }
 const values={};
 for(const name of ['get_Categories','get_Templates','get_SelectedCategory','get_SelectedShapeParameterCategory','get_SelectedTemplate','get_Instances']){
  if(!editor.tryMethod(name))continue;
  try{const v=editor.method(name).invoke();values[name]={type:v.type?v.type.name:typeof v};if(v.handle&&!v.handle.isNull())values[name].schema=describe(v.class);}catch(e){values[name]={error:String(e)};}
 }
 return {read_only:true,editor:describe(editor.class),values,types};
},'''
class Probe(Runtime):
 def start(self):
  original=Path.read_text
  def read(path,*a,**kw):
   text=original(path,*a,**kw)
   if path==PROJECT/'agent/operations.js':text=text.replace('const operations={','const operations={'+PROBE,1)
   return text
  with patch.object(Path,'read_text',read):super().start()
async def main(a):
 out=a.out.resolve();assert out.is_relative_to(ROOT/'projects/whale-maid') and not out.exists();out.mkdir(parents=True)
 base=json.loads((ROOT/'projects/whale-maid/accessory-refinement-v02/footwear-base/base-acceptance.json').read_text(encoding='utf8'))['save']
 runtime=Probe(ROOT/'lab-test')
 try:
  await asyncio.to_thread(runtime.start);await runtime.initialize(model_file=Path(base['path']));await asyncio.sleep(5)
  result=await runtime._call('shoe_template_schema')
  (out/'schema.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
  print(json.dumps({'read_only':True,'editor':result['editor']['name'],'types':len(result['types']),'out':str(out)}),flush=True)
 finally:await asyncio.to_thread(runtime.close)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);asyncio.run(main(p.parse_args()))
