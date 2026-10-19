"""Read-only renderer/material and saved base-part inspection for native heels."""
import argparse,asyncio,json,os,sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'VRoid-MCP'))
os.environ['TEMP']=os.environ['TMP']=str(ROOT/'work/temp')
from vroid_mcp.runtime import Runtime,PROJECT
PROBE=r'''native_heel_parts(args){
 const describe=c=>({name:c.type.name,fields:c.fields.filter(f=>!f.isStatic).map(f=>({name:f.name,type:f.type.name})),methods:c.methods.map(m=>({name:m.name,args:m.parameters.map(p=>p.type.name),returns:m.returnType.name}))});
 function renderer(r){const mesh=r.method('get_sharedMesh').invoke();return {name:text(r.method('get_name').invoke()),id:r.handle.toString(),vertices:mesh.method('get_vertexCount').invoke(),triangles:mesh.method('get_triangles').invoke().length/3,submeshes:mesh.method('get_subMeshCount').invoke(),materials:[...r.method('get_sharedMaterials').invoke()].map(m=>({name:text(m.method('get_name').invoke()),shader:text(m.method('get_shader').invoke().method('get_name').invoke()),textures:[...m.method('GetTexturePropertyNames').invoke()].map(n=>{const t=m.method('GetTexture',1).overload('System.String').invoke(n);return {property:text(n),name:t.handle.isNull()?null:text(t.method('get_name').invoke())};})}))};}
 const ref=state.refs['VRoid.Studio.XWear.Edit.ViewModel'];
 if(args.wear){
  const vm=new Il2Cpp.Object(ptr(ref)),base=vm.method('get_CurrentBaseModel').invoke();
  return {read_only:true,parts:[...base.method('get_SubContents').invoke()].map(s=>({renderer:renderer(s.field('_renderer').value),schema:describe(s.class)}))};
 }
 const m=model(),face=m.face.method('GetFaceSMR').invoke(),origin=face.method('get_transform').invoke().method('get_parent').invoke(),renderers=[];
 function walk(t){const r=t.method('get_gameObject').invoke().method('GetComponent',1).overload('System.Type').invoke(core('SkinnedMeshRenderer').type.object);if(!r.handle.isNull())renderers.push(renderer(r));for(let i=0;i<t.method('get_childCount').invoke();i++)walk(t.method('GetChild').invoke(i));}
 walk(origin);return {read_only:true,renderers};
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
 record=json.loads((ROOT/'projects/whale-maid/accessory-refinement-v02/high-heel-retained-081-v01/acceptance.json').read_text(encoding='utf8'));saved=record['heel_saved_model'];runtime=Probe(ROOT/'lab-test')
 try:
  await asyncio.to_thread(runtime.start);await runtime.initialize(model_file=Path(saved['path']));await asyncio.sleep(5)
  ordinary=await runtime._call('native_heel_parts',{});(out/'ordinary.json').write_text(json.dumps(ordinary,ensure_ascii=False,indent=2),encoding='utf8')
  status=await runtime.wear_status();status=await runtime.open_wear_project(Path(record['wear_save']['path']).name,status['wear_token'],True)
  wear=await runtime._call('native_heel_parts',{'wear':True});(out/'wear.json').write_text(json.dumps(wear,ensure_ascii=False,indent=2),encoding='utf8')
  snapshot=await runtime._call('get_wear_snapshot',{'expected_wear':status['wear_token']});(out/'snapshot.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding='utf8')
  print(json.dumps({'ordinary':[(r['name'],r['vertices']) for r in ordinary['renderers']],'wear':[(r['renderer']['name'],r['renderer']['vertices']) for r in wear['parts']]},ensure_ascii=False),flush=True)
 finally:await asyncio.to_thread(runtime.close)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);asyncio.run(main(p.parse_args()))
