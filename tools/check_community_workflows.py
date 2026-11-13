"""Native community-workflow cancellation on a NEW test-owned attached window.

The fixture delays observation of completion on the actual retained native tasks.
It does not replace their work or results. A real MCP cancellation notification
then exercises source pins, review/ack, detach refusal and unpublished exports.
Its separate startup guard protects the disposable profile throughout handoff.
"""
from __future__ import annotations

import argparse
import asyncio
import ctypes
from ctypes import wintypes
from contextlib import suppress
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import frida
from mcp import ClientSession, McpError, StdioServerParameters, types
from mcp.client.stdio import stdio_client
import prepare_lab
from vroid_mcp import bridge
from vroid_mcp.runtime import Runtime
from check_attached_editing import FIXTURE_RPC

TASK_PREFIX=r'''
const communityFixture={arm:null,stage:null,targets:new Map(),wrapped:new WeakSet()};
function communityFixtureRetained(o){
 if(!communityFixture.stage||!o?.handle||o.handle.isNull()||!o.tryMethod?.('get_IsCompleted',0)||!o.tryMethod?.('get_IsFaulted',0))return;
 const key=o.handle.toString(),arm=communityFixture.stage;
 const original=o.method.bind(o);
 communityFixture.targets.set(key,{operation:arm.operation,until:Date.now()+arm.ms,observations:0,
  completed_at_dispatch:original('get_IsCompleted',0).invoke()});
 if(communityFixture.wrapped.has(o))return;
 communityFixture.wrapped.add(o);
 // Only the JS observation on this retained task is delayed. Its actual
 // native work, completion state, result and exception remain unchanged.
 o.method=function(name,...args){
  const method=original(name,...args);
  if(name!=='get_IsCompleted')return method;
  return new Proxy(method,{get(target,property){
   if(property==='invoke')return (...values)=>{
    const value=method.invoke(...values),state=communityFixture.targets.get(key);
    if(state){state.actual_completed=value;state.observations++;if(Date.now()<state.until)return false;}
    return value;
   };
   const value=Reflect.get(target,property,target);return typeof value==='function'?value.bind(target):value;
  }});
 };
}
'''

TASK_SUFFIX=r'''
const communityFixtureDispatch=vroid.dispatch;
vroid.dispatch=function(operation,args){
 const arm=communityFixture.arm;
 if(arm?.operation===operation){communityFixture.stage=arm;communityFixture.arm=null;}
 try{return communityFixtureDispatch(operation,args);}
 finally{communityFixture.stage=null;}
};
rpc.exports.communityfixturearm=(operation,ms)=>{
 if(!['open_from_menu','custom_item_validate_begin','apply_registered_custom_item','start_vrm_export'].includes(operation)||!Number.isInteger(ms)||ms<1000||ms>30000)throw Error('INVALID_FIXTURE_ARM');
 communityFixture.arm={operation,ms};return {armed:true};
};
rpc.exports.communityfixturestate=()=>[...communityFixture.targets.entries()].map(([task,state])=>({task,...state}));
rpc.exports.communityfixturerelease=operation=>{
 for(const state of communityFixture.targets.values())if(state.operation===operation)state.until=0;
 return {released:true};
};
rpc.exports.communityfixturemenu=()=>schedule(()=>{
 const main=new Il2Cpp.Object(ptr(state.refs['VRoid.Studio.MainViewModel']));
 const screen=main.method('get_GlobalBus').invoke().method('get_ScreenNavigation').invoke().method('get_ActiveScreen').invoke();
 if(screen.class.type.name!=='VRoid.Studio.StartScreen.ViewModel')throw Error('FIXTURE_START_SCREEN_REQUIRED');
 screen.method('SetStartScreenMode',1).invoke(cls('VRoid.Studio','VRoid.Studio.StartScreen.StartScreenMode').field('ModelSelection').value);
 return {fixture_only:true,agreements_accepted:false};
});
'''

BOOT=r'''
import asyncio,json
from pathlib import Path
from vroid_mcp import bridge
from vroid_mcp.runtime import Runtime
from vroid_mcp.server import main
folder=Path(__file__).parent
original_text=bridge.script_text
def script_text(*a,**kw):
 text=original_text(*a,**kw)
 needle='const retain = function (object) { return keep(object); };'
 if text.count(needle)!=1:raise RuntimeError('FIXTURE_RETAIN_SEAM_CHANGED')
 return (folder/'task-prefix.js').read_text()+text.replace(needle,
  'const retain = function (object) { const h=keep(object); communityFixtureRetained(object); return h; };')+(folder/'task-suffix.js').read_text()
bridge.script_text=script_text
original_call=Runtime._call
async def call(self,operation,args=None):
 release=self.lab/'community-interrupt.release.json'
 if release.is_file():
  released=json.loads(release.read_text());release.unlink()
  await asyncio.to_thread(self.script.exports_sync.communityfixturerelease,released['operation'])
 arm=self.lab/'community-interrupt.arm.json'
 armed=arm.is_file() and json.loads(arm.read_text())['operation']==operation
 if armed:
  settings=json.loads(arm.read_text());arm.unlink()
  await asyncio.to_thread(self.script.exports_sync.communityfixturearm,operation,settings['ms'])
 result=await original_call(self,operation,args)
 if armed:
  tasks=await asyncio.to_thread(self.script.exports_sync.communityfixturestate)
  (self.lab/'community-interrupt.dispatched.json').write_text(json.dumps(dict(operation=operation,args=args,tasks=tasks,force_host_exit=bool(settings.get('force_host_exit')))))
  if settings.get('force_host_exit'):
   import os
   os._exit(73)
 return result
Runtime._call=call
original_wait=Runtime._await_session
async def wait(self,operation,args,dispatched):
 result=await original_wait(self,operation,args,dispatched)
 if operation=='return_to_main_menu' and result.get('start_screen_mode')=='InitialAgreements':
  # Test-only ModelSelection fixture, without accepting or persisting agreements.
  await asyncio.to_thread(self.script.exports_sync.communityfixturemenu)
  for _ in range(100):
   result=await self._call('status')
   if result.get('menu_ready'):return result
   await asyncio.sleep(.1)
  raise TimeoutError('FIXTURE_MENU_DID_NOT_SETTLE')
 return result
Runtime._await_session=wait
main()
'''


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class FixtureProcess:
    """Retained exact-process handle prevents cleanup from following PID reuse."""
    def __init__(self,pid):
        self.api=ctypes.WinDLL('kernel32',use_last_error=True)
        self.api.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        self.api.OpenProcess.restype=wintypes.HANDLE
        self.api.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        self.api.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT]
        self.api.CloseHandle.argtypes=[wintypes.HANDLE]
        self.handle=self.api.OpenProcess(0x00100001,False,pid)
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
    def alive(self):return self.api.WaitForSingleObject(self.handle,0)==258
    def stop(self):
        if self.alive():
            if not self.api.TerminateProcess(self.handle,0):raise ctypes.WinError(ctypes.get_last_error())
            if self.api.WaitForSingleObject(self.handle,10000)!=0:raise TimeoutError('fixture did not stop')
    def close(self):self.api.CloseHandle(self.handle)


async def check(source:Path,out:Path,variant='F00',hold_ms=30000,force_host_exit=False):
    if out.exists():raise FileExistsError('Use a NEW output directory')
    prepare_lab.check_directories(source.resolve(),out.resolve())
    out.mkdir(parents=True);(out/'temp').mkdir()
    os.environ['TEMP']=os.environ['TMP']=os.environ['TMPDIR']=str(out/'temp');tempfile.tempdir=None
    target=out/'target'
    await asyncio.to_thread(prepare_lab.main,['--source',str(source),'--lab',str(target)])
    fixture=Runtime(target);fixture.run_dir.mkdir(parents=True,exist_ok=True)
    lab=target/'clients'/'client';(lab/'saves').mkdir(parents=True)
    (out/'task-prefix.js').write_text(TASK_PREFIX,encoding='utf8')
    (out/'task-suffix.js').write_text(TASK_SUFFIX,encoding='utf8')
    boot=out/'server_boot.py';boot.write_text('import sys\nsys.path.insert(0,'+repr(str(ROOT))+')\n'+BOOT,encoding='utf8')
    params=StdioServerParameters(command=sys.executable,args=[str(boot),'--lab',str(lab)],cwd=str(ROOT),env=dict(os.environ))
    report={'scope':'owned external fixture; delayed observation of genuine native task completion','variant':variant,'checks':{},'calls':[]}
    def save(): (out/'checks.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    def passed(name,evidence=True):report['checks'][name]=evidence;save();print('PASS '+name,flush=True)
    dev=frida.get_local_device();pid=None;guard_session=None;controller=None;process=None
    def alive():return process is not None and process.alive()
    forced=False;item=None
    try:
        pid=dev.spawn([str(fixture.exe),'-logFile',str(fixture.run_dir/'Player.log'),'-screen-fullscreen','0','-screen-width','960','-screen-height','720'],cwd=str(fixture.exe.parent),env=bridge._environment(fixture),stdio='pipe')
        report['pid']=pid
        process=FixtureProcess(pid)
        guard_session=dev.attach(pid)
        guard=guard_session.create_script('const PROBE='+json.dumps(bridge._probe_config(fixture))+';\n'+'\n'.join((ROOT/'agent'/name).read_text(encoding='utf8') for name in ['native_traps.js','registry_guard.js','profile_guard.js']))
        guard.load();dev.resume(pid);await asyncio.sleep(10)
        controller=Runtime(out/'controller');original=bridge.script_text
        bridge.script_text=lambda *a,**kw:original(*a,**kw)+FIXTURE_RPC
        try:await asyncio.to_thread(controller.attach,pid)
        finally:bridge.script_text=original
        for _ in range(200):
            if (await asyncio.to_thread(controller.script.exports_sync.health))['ready']:break
            await asyncio.sleep(.1)
        await asyncio.to_thread(controller.script.exports_sync.fixture,'new_model',{'variant':variant})
        deadline=time.monotonic()+90
        while True:
            try:status=await controller._settle();break
            except Exception as error:
                if 'MAIN_THREAD_TIMEOUT: not executed' not in str(error) or time.monotonic()>deadline:raise
                await asyncio.sleep(.5)
        await controller.set_face_params(status['model_token'],[{'id':'face/FaceSet/006','value':.37}])
        original_file=lab/'saves'/'original.vroid'
        await asyncio.to_thread(controller.script.exports_sync.fixture,'manual_save',{'path':str(original_file)})
        original_hash=sha(original_file)
        closed=await asyncio.to_thread(controller.close);assert closed.get('detached') and alive(),closed
        controller=None
        try:
          with (out/'server.log').open('w',encoding='utf8') as log:
            async with stdio_client(params,errlog=log) as (read,write):
              async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=240)) as client:
                    async def call(name,args=None,error=None):
                        reply=await client.call_tool(name,args or {})
                        texts=[b.text for b in reply.content if b.type=='text']
                        data=reply.structuredContent
                        if data is None:
                            try:data=json.loads(texts[0]) if len(texts)==1 else texts
                            except ValueError:data=texts
                        if isinstance(data,dict) and set(data)=={'result'}:data=data['result']
                        report['calls'].append(dict(tool=name,args=args or {},result=data,error=reply.isError));save()
                        if error:
                            expected=(error,) if isinstance(error,str) else error
                            assert reply.isError and any(e in '\n'.join(texts) for e in expected),(name,texts)
                        elif reply.isError:raise RuntimeError(name+': '+'\n'.join(texts))
                        return data
                    await client.initialize()
                    status=await call('attach_open_vroid',{'pid':pid});token=status['model_token']
                    await call('set_face_params',{'expected_model':token,'changes':[{'id':'face/FaceSet/006','value':.38}]})
                    await call('return_to_main_menu',{'expected_model':token},'EXPLICIT_DISCARD_REQUIRED')
                    await call('exit_vroid',{'expected_model':token,'close_attached':True},'EXPLICIT_DISCARD_REQUIRED')
                    assert (await call('get_status'))['model_token']==token and alive()
                    passed('dirty_menu_return_and_exit_refuse_before_dispatch')
                    await call('return_to_main_menu',{'expected_model':token,'discard_unsaved':True})
                    menu=await call('get_status');assert menu['menu_ready']
                    await call('create_from_menu',{'expected_menu':menu['menu_token'],'variant':variant},'CONFIRM_ATTACHED')
                    await call('create_from_menu',{'expected_menu':menu['menu_token'],'variant':variant,'confirm_attached':True})
                    status=await call('get_status');token=status['model_token'];assert status['pid']==pid and status['model_variant']==variant
                    passed('attached_menu_confirmation_and_same_pid_creation')
                    await call('return_to_main_menu',{'expected_model':token,'discard_unsaved':True})
                    menu=await call('get_status');assert menu['menu_ready']

                    async def interrupt(label,operation,tool,args,pinned=None,unpublished=None):
                        marker=lab/'community-interrupt.dispatched.json'
                        if marker.exists():marker.unlink()
                        (lab/'community-interrupt.arm.json').write_text(json.dumps(dict(operation=operation,ms=hold_ms)))
                        request_id=client._request_id
                        task=asyncio.create_task(client.call_tool(tool,args,read_timeout_seconds=timedelta(seconds=240)))
                        try:
                            deadline=time.monotonic()+180
                            while not marker.exists():
                                if task.done():raise AssertionError('native dispatch marker missing: '+str(await task))
                                if time.monotonic()>deadline:raise TimeoutError('native dispatch marker missing')
                                await asyncio.sleep(.05)
                            dispatched=json.loads(marker.read_text())
                            assert any(t['operation']==operation for t in dispatched['tasks']),dispatched
                            await client.send_notification(types.ClientNotification(types.CancelledNotification(params=types.CancelledNotificationParams(requestId=request_id,reason='owned native acceptance cancellation'))))
                            with suppress(Exception):await asyncio.wait_for(task,5)
                            await call('get_attached_state',error='ATTACHED_NATIVE_WORK_PENDING')
                            # A native export dialog can be the earlier guard.
                            # Both refusals precede receipt/pin release.
                            await call('acknowledge_attached_state',{'recovery_token':'not-issued'},('ATTACHED_NATIVE_WORK_PENDING','ATTACHED_UI_BLOCKED'))
                            detached=await call('detach_open_vroid');assert detached.get('close_blocked') and alive(),detached
                            if pinned:
                                try:stream=Path(pinned).open('r+b')
                                except PermissionError:pass
                                else:stream.close();raise AssertionError('pending source file was not pinned')
                            passed(label+'_pending_refuses_review_ack_detach_and_preserves_pin',dispatched)
                            (lab/'community-interrupt.release.json').write_text(json.dumps(dict(operation=operation)))
                            deadline=time.monotonic()+90
                            while True:
                                reply=await client.call_tool('get_attached_state',{})
                                if not reply.isError:
                                    review=reply.structuredContent or json.loads(reply.content[0].text)
                                    acknowledged=await client.call_tool('acknowledge_attached_state',{'recovery_token':review['recovery_token']})
                                    if not acknowledged.isError:
                                        ack=acknowledged.structuredContent or json.loads(acknowledged.content[0].text)
                                        report['calls'].append(dict(tool='acknowledge_attached_state',result=ack,error=False));save();break
                                    message='\n'.join(c.text for c in acknowledged.content if c.type=='text')
                                    # These exact guards precede receipt release. Re-inspect
                                    # a transiently busy/changed model; never replay its edit.
                                    if not any(k in message for k in ['STATE_NOT_IDLE','STALE_ATTACHED_REVIEW','NATIVE_WORK_PENDING']):raise RuntimeError(message)
                                    if time.monotonic()>deadline:raise TimeoutError('native review/ack did not settle: '+message)
                                    await asyncio.sleep(.2);continue
                                message='\n'.join(c.text for c in reply.content if c.type=='text')
                                if not any(k in message for k in ['NATIVE_WORK_PENDING','STATE_NOT_IDLE']):raise RuntimeError(message)
                                if time.monotonic()>deadline:raise TimeoutError('native work did not become reviewable: '+message)
                                await asyncio.sleep(.2)
                            assert ack['acknowledged'] and not ack['replayed'],ack
                            if pinned:
                                with Path(pinned).open('r+b'):pass
                            if unpublished:assert not Path(unpublished).exists(),'cancelled export was published'
                            passed(label+'_terminal_review_releases_without_replay')
                            return dispatched
                        finally:
                            if not task.done():task.cancel()
                            with suppress(BaseException):await task

                    await interrupt('menu_import','open_from_menu','open_from_menu',dict(expected_menu=menu['menu_token'],filename=str(original_file),confirm_attached=True),pinned=original_file)
                    status=await call('get_status');token=status['model_token']
                    assert status['pid']==pid and status['attached_state']['file_path']==str(original_file),status
                    face=await call('list_face_params');assert abs(next(p['value'] for p in face['parameters'] if p['id']=='face/FaceSet/006')-.37)<1e-5
                    passed('cancelled_import_actual_file_and_face_state_inspected')
                    saved=await call('save_custom_items',{'expected_model':token,'types':['Iris']})
                    item=saved['saved'][0];custom_path=Path(item['path']);custom_hash=sha(custom_path)
                    await interrupt('custom_validation','custom_item_validate_begin','apply_custom_item',dict(expected_model=token,filename=str(custom_path)),pinned=custom_path)
                    await interrupt('custom_selection','apply_registered_custom_item','apply_custom_item',dict(expected_model=token,filename=str(custom_path)),pinned=custom_path)
                    assert sha(custom_path)==custom_hash
                    inventory=await call('list_groups',{'expected_model':token})
                    assert any(g['active'] and g['id']==item['id'] for g in inventory['groups']),inventory
                    passed('cancelled_custom_selection_actual_membership_and_source_bytes_inspected')
                    destination=lab/'saves'/'cancelled.vrm'
                    export=await interrupt('vrm_export','start_vrm_export','export_vrm',dict(expected_model=token,filename=destination.name,version=1,title='Native cancellation fixture',author='VRoid Character MCP'),unpublished=destination)
                    staged=Path(export['args']['path'])
                    assert staged.is_file() and staged.stat().st_size>100,staged
                    await call('get_vrm_export_options',{'expected_model':token,'leave':True})
                    await call('set_face_params',{'expected_model':token,'changes':[{'id':'face/FaceSet/006','value':.42}]})
                    final=await call('save_character_as',{'expected_model':token,'path':str(lab/'saves'/'recovered.vroid')})
                    report['recovered_file']=final['path']
                    passed('cancelled_export_remains_unpublished_and_edit_save_resume',dict(staged=str(staged),bytes=staged.stat().st_size))
                    if force_host_exit:
                        await call('return_to_main_menu',{'expected_model':token,'discard_unsaved':True})
                        menu=await call('get_status')
                        marker=lab/'community-interrupt.dispatched.json'
                        if marker.exists():marker.unlink()
                        (lab/'community-interrupt.arm.json').write_text(json.dumps(dict(operation='open_from_menu',ms=hold_ms,force_host_exit=True)))
                        forced=True
                        await call('open_from_menu',{'expected_menu':menu['menu_token'],'filename':report['recovered_file'],'confirm_attached':True})
                        raise AssertionError('forced host unexpectedly returned success')
                    await call('exit_vroid',{'expected_model':token,'discard_unsaved':True},'CLOSE_ATTACHED_REQUIRED')
                    result=await call('exit_vroid',{'expected_model':token,'discard_unsaved':True,'close_attached':True})
                    assert result['graceful'] and not alive(),result
                    assert (await call('get_status'))['stopped'] and not alive()
                    passed('explicit_attached_graceful_exit_has_no_implicit_relaunch')
        except Exception as failure:
            marker=lab/'community-interrupt.dispatched.json'
            if not forced or not marker.is_file() or not alive():raise
            report['forced_host_dispatch']=json.loads(marker.read_text())
            dispatched=report['forced_host_dispatch']
            if dispatched.get('operation')!='open_from_menu' or dispatched.get('force_host_exit') is not True:raise
            def leaves(error):
                for nested in getattr(error,'exceptions',()):yield from leaves(nested)
                if not getattr(error,'exceptions',()):yield error
            # Only transport closure is the expected result of os._exit(73).
            # Do not turn an assertion or ordinary tool error into a pass.
            if not all(isinstance(e,McpError) and 'Connection closed' in str(e) for e in leaves(failure)):raise
            report['forced_host_transport_error']=repr(failure)
            # A new host cannot certify owners retained by an unloaded agent.
            # Native import is still genuine and must survive the lost client.
            await asyncio.sleep(3)
            with (out/'replacement-server.log').open('w',encoding='utf8') as log:
                async with stdio_client(params,errlog=log) as (read,write):
                    async with ClientSession(read,write) as replacement:
                        await replacement.initialize()
                        attached=await replacement.call_tool('attach_open_vroid',{'pid':pid})
                        if not attached.isError:
                            review=await replacement.call_tool('get_attached_state',{})
                            message='\n'.join(c.text for c in review.content if c.type=='text')
                            assert review.isError and 'NATIVE_WORK_OWNER_LOST' in message,message
                        else:
                            message='\n'.join(c.text for c in attached.content if c.type=='text')
                            assert any(k in message for k in ['NATIVE_WORK','OWNER_LOST']),message
                        report['replacement_refusal']=message
            assert alive()
            passed('forced_host_exit_keeps_target_alive_and_refuses_unproven_owner_handoff')
        assert sha(original_file)==original_hash and sha(custom_path)==custom_hash
        report['passed']=True
    except BaseException as error:
        report.update(passed=False,error=repr(error));raise
    finally:
        if controller is not None:await asyncio.to_thread(controller.close)
        if process is not None:process.stop();process.close()
        if guard_session:
            with suppress(frida.InvalidOperationError):guard_session.detach()
        save()
    cold=Runtime(target)
    try:
        await asyncio.to_thread(cold.start);status=await cold.initialize(model_file=Path(report['recovered_file']))
        face=await cold.list_face_params()
        assert abs(next(p['value'] for p in face['parameters'] if p['id']=='face/FaceSet/006')-.42)<1e-5
        inventory=await cold.list_groups(status['model_token'])
        assert any(g['active'] and g['id']==item['id'] for g in inventory['groups'])
        passed('recovered_face_and_custom_item_survive_cold_process')
    except BaseException as error:report.update(passed=False,cold_error=repr(error));raise
    finally:await asyncio.to_thread(cold.close);save()
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--variant',choices=['F00','M00'],default='F00')
    parser.add_argument('--hold-ms',type=int,default=30000,choices=range(5000,30001))
    parser.add_argument('--force-host-exit',action='store_true',help='lose the host during a final menu import and verify conservative handoff refusal')
    args=parser.parse_args()
    asyncio.run(check(args.source,args.out,args.variant,args.hold_ms,args.force_host_exit))
