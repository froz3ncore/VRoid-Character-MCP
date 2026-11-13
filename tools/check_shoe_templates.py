"""Shoe template acceptance on a new model in an exclusive prepared lab.

Removes only the generated test model's shoes, adds a listed native template
once, verifies history and saves a NEW file for cold persistence. No user
window or existing model is selected. --out must not exist. An optional
--baseline is a previous report from this tool, for exact template-ID comparison.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from vroid_mcp import bridge
from vroid_mcp.runtime import Runtime
SCRIPT=r'''
rpc.exports.removeshoes=()=>schedule(()=>{
 const root=new Il2Cpp.Object(ptr(state.refs['VRoid.Studio.EditRootScreen.ViewModel']));
 const context=root.field('_engineModel').value.method('get_Context').invoke();
 const delegate=Il2Cpp.corlib.class('System.Delegate'),types=Il2Cpp.corlib.class('System.Type');
 const method=Il2Cpp.corlib.class('System.Threading.Thread').type.object.method('GetMethod')
  .overload('System.String','System.Type[]').invoke(Il2Cpp.string('MemoryBarrier'),Il2Cpp.array(types,0));
 const error=cls('UnityEngine.CoreModule','UnityEngine.Debug').type.object.method('GetMethod')
  .overload('System.String','System.Type[]').invoke(Il2Cpp.string('LogException'),Il2Cpp.array(types,[Il2Cpp.corlib.class('System.Exception').type.object]));
 const create=(type,info)=>delegate.method('CreateDelegate').overload('System.Type','System.Reflection.MethodInfo').invoke(type.type.object,info);
 const ok=create(Il2Cpp.corlib.class('System.Action'),method),fail=create(Il2Cpp.corlib.class('System.Action`1').inflate(Il2Cpp.corlib.class('System.Exception')),error);
 globalThis.shoeTestCallbacks=[retain(ok),retain(fail)];
 const id=context.method('GetTransferableGroupIdOfType').invoke(Il2Cpp.string('TransferableGroupType.N00.Level1.Shoes'));
 if(id.handle.isNull())return {removed:false};
 context.method('RemoveTransferableGroupAndChildren').invoke(id,ok,fail);
 return {removed:true,id:id.content};
});
'''
async def check(args):
    variant=args.variant
    out=args.out.resolve()
    out.mkdir(parents=True,exist_ok=False)
    lab=args.lab.resolve()
    runtime=Runtime(lab)
    original=bridge.script_text
    bridge.script_text=lambda *a,**kw:original(*a,**kw)+SCRIPT
    report={'checks':{},'variant':variant,'lab':str(lab)}
    def passed(name,value=True):report['checks'][name]=value;print('PASS '+name,flush=True)
    try:
        await asyncio.to_thread(runtime.start)
        status=await runtime.initialize(variant=variant)
        token=status['model_token']
        rows=(await runtime.list_shoe_templates(token))['templates']
        report['templates']=[row['id'] for row in rows]
        assert rows and len(set(report['templates']))==len(rows)
        passed('native_template_ids_unique',len(rows))
        if args.baseline:
            baseline=json.loads(args.baseline.read_text(encoding='utf8'))['templates']
            assert set(report['templates'])==set(baseline)
            passed('same_native_template_ids_as_baseline')
        removed=await asyncio.to_thread(runtime.script.exports_sync.removeshoes)
        await runtime._settle()
        without=(await runtime.list_parts(token))['parts']
        assert not any(p['type']=='Shoes' for p in without),without
        passed('test_fixture_has_no_native_shoes',removed)
        selected=rows[0]['id']
        added=await runtime.add_shoe_template(token,selected)
        assert added['ok'],added
        after=(await runtime.list_parts(token))['parts']
        protected={p['id'] for p in without}
        assert protected <= {p['id'] for p in after}
        assert len([p for p in after if p['type']=='Shoes'])==1
        passed('single_add_verified_other_groups_preserved',added)
        await runtime.history('undo',token)
        assert {p['id'] for p in (await runtime.list_parts(token))['parts']}==protected
        await runtime.history('redo',token)
        assert {p['id'] for p in (await runtime.list_parts(token))['parts']}=={p['id'] for p in after}
        passed('native_undo_redo')
        saved=await runtime.save_as('shoe-template-'+variant.lower()+'-'+uuid.uuid4().hex+'.vroid',token)
        report['saved']=saved
        await asyncio.to_thread(runtime.close)
        runtime=Runtime(lab)
        await asyncio.to_thread(runtime.start)
        status=await runtime.initialize(model_file=Path(saved['path']))
        parts=(await runtime.list_parts(status['model_token']))['parts']
        assert {p['id'] for p in parts}=={p['id'] for p in after}
        passed('cold_native_group_persistence')
        report['passed']=True
    except BaseException as error:
        report.update(passed=False,error=repr(error))
        raise
    finally:
        bridge.script_text=original
        await asyncio.to_thread(runtime.close)
        (out/'checks.json').write_text(json.dumps(report,indent=2),encoding='utf8')
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lab',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--variant',choices=['F00','M00'],default='F00')
    parser.add_argument('--baseline',type=Path)
    asyncio.run(check(parser.parse_args()))
