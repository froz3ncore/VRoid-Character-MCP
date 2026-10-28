"""Attached editing acceptance on a NEW, test-owned external VRoid fixture.

The startup fixture guard isolates its profile. The attached MCP has no guard.
No existing user window is selected. Keeps native and MCP logs and checks.json.
"""
from __future__ import annotations
import argparse
import asyncio
import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
from datetime import timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import frida
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import prepare_lab
from vroid_mcp import bridge, attached_ui
from vroid_mcp.runtime import Runtime
from vroid_mcp.texture_mapping import png_rgba
from vroid_mcp.bounded_paint import decode_rgba_png
from check_texture_layers import exercise as exercise_layers

FIXTURE_RPC = r'''
rpc.exports.fixture = (name,args={}) => schedule(() => {
 const type=cls('VRoid.Studio','VRoid.Studio.MainViewModel');
 const main=Il2Cpp.gc.choose(type).filter(o=>o.class.handle.equals(type.handle))[0];
 rememberSingleton('VRoid.Studio.MainViewModel',main);
 if(name==='new_model')cls('UnityEngine.CoreModule','UnityEngine.Application').method('set_runInBackground').invoke(true);
 const progress=main.method('get_ProgressProviderViewModel').invoke();
 if(name==='progress_start') {globalThis.progressNode=progress.method('Start').invoke(Il2Cpp.string('Attachment test'),false);globalThis.progressHold=retain(progressNode);return true;}
 if(name==='progress_finish') {progress.method('Finish').invoke(progressNode);progressHold.free();return true;}
 if(name==='dialog_show') {main.method('<WantsToQuitHandler>g__ShowUnSavedDialog|61_1').invoke();return true;}
 if(name==='dialog_dismiss'){main.method('get_DialogProviderViewModel').invoke().method('Dismiss').invoke();return true;}
 if(name==='png_callbacks') {
  const texture=cls('UnityEngine.CoreModule','UnityEngine.Texture2D'),error=Il2Cpp.corlib.class('System.Exception');
  const list=Il2Cpp.corlib.class('System.Collections.Generic.List`1');
  const ok=list.inflate(texture).new(),fail=list.inflate(error).new();
  const make=(t,o)=>Il2Cpp.corlib.class('System.Delegate').method('CreateDelegate').overload('System.Type','System.Object','System.Reflection.MethodInfo').invoke(t.type.object,o,o.class.type.object.method('GetMethod').overload('System.String').invoke(Il2Cpp.string('Add')));
  const success=make(Il2Cpp.corlib.class('System.Action`1').inflate(texture),ok),failure=make(Il2Cpp.corlib.class('System.Action`1').inflate(error),fail);
  globalThis.pngResults={ok,fail,holds:[ok,fail,success,failure].map(retain)};
  return {ok:success.handle.toString(),fail:failure.handle.toString()};
 }
 if(name==='png_results') {
  const p=pngResults,count=p.ok.method('get_Count').invoke(),items=[];
  for(let i=0;i<count;i++){const t=p.ok.method('get_Item').invoke(i),readable=t.method('get_isReadable').invoke();let pixel=null;
   if(readable){const c=t.method('GetPixel',2).invoke(0,0);pixel=['r','g','b','a'].map(k=>c.field(k).value);}
   items.push({readable,pixel,width:t.method('get_width').invoke(),height:t.method('get_height').invoke()});}
  return {count,failed:p.fail.method('get_Count').invoke(),items};
 }
 if(name==='png_submit') {
  const bytes=Il2Cpp.corlib.class('System.Convert').method('FromBase64String').invoke(Il2Cpp.string(args.png));
  const ok=new Il2Cpp.Object(ptr(args.ok)),fail=new Il2Cpp.Object(ptr(args.fail));
  const method=cls('VRoidCore','VRoidCore.Common.PNGUtil').method('LoadPNGToRGBATexture2DAsync');
  const call=new NativeFunction(method.virtualAddress,'void',['pointer','bool','bool','bool','pointer','pointer','pointer'],{exceptions:'propagate'});
  call(bytes.handle,0,0,0,ok.handle,fail.handle,method.handle);
  call(bytes.handle,1,1,1,ok.handle,fail.handle,method.handle);
  send({event:'fixture-png-submitted'});
  new NativeFunction(Process.getModuleByName('kernel32.dll').getExportByName('Sleep'),'void',['uint32'])(3000);
  return true;
 }
 if(name==='manual_save') {
  const h=main.method('get_ActionHandler').invoke();
  const p=Memory.alloc(1);p.writeU8(0);
  const inv=new NativeFunction(Il2Cpp.module.getExportByName('il2cpp_runtime_invoke'),'pointer',['pointer','pointer','pointer','pointer'],{exceptions:'propagate'});
  const a=Memory.alloc(2*Process.pointerSize),e=Memory.alloc(Process.pointerSize);e.writePointer(NULL);
  a.writePointer(Il2Cpp.string(args.path).handle);a.add(Process.pointerSize).writePointer(p);
  inv(h.method('SaveSync').handle,h.handle,a,e);if(!e.readPointer().isNull())throw Error('FIXTURE_SAVE_FAILED');
  const file=main.field('_mainModel').value.field('currentFile').value,path=Il2Cpp.string(args.path);
  new NativeFunction(Il2Cpp.module.getExportByName('il2cpp_field_set_value_object'),'void',['pointer','pointer','pointer'])(file.handle,file.field('path').handle,path.handle);
  globalThis.fixtureSourcePath=retain(path);
  h.method('set_IsUnSaved').invoke(false);return true;
 }
 return vroid.dispatch(name,args);
},true);
'''

# Controlled interruption AFTER the native layer write, BEFORE the public tool
# responds. Only this fixture bootstrap applies the delay; product code has none.
BOOTSTRAP = '''import asyncio
from vroid_mcp.runtime import Runtime
from vroid_mcp.server import main
original=Runtime.parameter_call
async def delayed(self,operation,args=None,mutating=False):
 result=await original(self,operation,args,mutating)
 if operation=='import_texture_layer' and (self.lab/'interrupt.arm').exists():
  (self.lab/'interrupt.imported').write_text('native layer imported')
  await asyncio.sleep(60)
 return result
Runtime.parameter_call=delayed
main()
'''

FILE_DIALOG = r'''
import ctypes,sys
from ctypes import wintypes as w
class OPENFILENAMEW(ctypes.Structure):
 _fields_=[('lStructSize',w.DWORD),('hwndOwner',w.HWND),('hInstance',w.HINSTANCE),
  ('lpstrFilter',w.LPCWSTR),('lpstrCustomFilter',w.LPWSTR),('nMaxCustFilter',w.DWORD),
  ('nFilterIndex',w.DWORD),('lpstrFile',w.LPWSTR),('nMaxFile',w.DWORD),
  ('lpstrFileTitle',w.LPWSTR),('nMaxFileTitle',w.DWORD),('lpstrInitialDir',w.LPCWSTR),
  ('lpstrTitle',w.LPCWSTR),('Flags',w.DWORD),('nFileOffset',w.WORD),('nFileExtension',w.WORD),
  ('lpstrDefExt',w.LPCWSTR),('lCustData',w.LPARAM),('lpfnHook',ctypes.c_void_p),
  ('lpTemplateName',w.LPCWSTR),('pvReserved',ctypes.c_void_p),('dwReserved',w.DWORD),('FlagsEx',w.DWORD)]
filename=ctypes.create_unicode_buffer(4096)
ofn=OPENFILENAMEW();ofn.lStructSize=ctypes.sizeof(ofn);ofn.hwndOwner=int(sys.argv[1])
ofn.lpstrFile=ctypes.cast(filename,w.LPWSTR);ofn.nMaxFile=len(filename)
ofn.lpstrFilter='VRoid models\0*.vroid\0\0';ofn.lpstrInitialDir=sys.argv[2]
ofn.lpstrTitle='VRoid MCP isolated file dialog check';ofn.Flags=0x80000|0x1000|0x800|8
dialog=ctypes.WinDLL('comdlg32');dialog.GetOpenFileNameW.argtypes=[ctypes.POINTER(OPENFILENAMEW)]
result=dialog.GetOpenFileNameW(ctypes.byref(ofn))
print('selected' if result else 'cancelled',flush=True)
'''


async def check(source: Path, out: Path, variant: str, xwear: Path | None = None):
    if out.exists():
        raise FileExistsError('Use a NEW output directory')
    prepare_lab.check_directories(source.resolve(), out.resolve())
    prepare_lab.check_install(source)
    out.mkdir(parents=True)
    (out / 'temp').mkdir()
    os.environ['TEMP'] = os.environ['TMP'] = str(out / 'temp')
    target = out / 'target'
    await asyncio.to_thread(prepare_lab.main, ['--source', str(source), '--lab', str(target)])
    fixture = Runtime(target)
    fixture.run_dir.mkdir(parents=True)
    # The fixture startup guard only permits model IO beneath target. Both
    # independent clients stay there; the attached agent still has no guard.
    lab = target / 'clients' / 'client'
    (lab / 'saves').mkdir(parents=True)
    bootstrap = out / 'server_boot.py'
    bootstrap.write_text('import sys\nsys.path.insert(0,' + repr(str(ROOT)) + ')\n' + BOOTSTRAP)
    params = StdioServerParameters(command=sys.executable,
        args=[str(bootstrap), '--lab', str(lab)], cwd=str(ROOT), env=dict(os.environ))
    dev = frida.get_local_device()
    pid = None
    guard_session = None
    controller = None
    crashed_server = None
    dialog_process = None
    report = {'scope': 'test-owned external process; separate startup profile guard',
              'variant': variant, 'checks': {}}
    def passed(name, evidence=True):
        report['checks'][name] = evidence
        print('PASS ' + name, flush=True)
    async def fixture_call(name, args=None):
        return await asyncio.to_thread(controller.script.exports_sync.fixture, name, args or {})
    def alive(): return any(p.pid == pid for p in dev.enumerate_processes())
    try:
        pid = dev.spawn([str(fixture.exe), '-logFile', str(fixture.run_dir/'Player.log'),
                         '-screen-fullscreen', '0', '-screen-width', '960', '-screen-height', '720'],
                        cwd=str(fixture.exe.parent), env=bridge._environment(fixture), stdio='pipe')
        guard_session = dev.attach(pid)
        guard = guard_session.create_script('const PROBE=' + json.dumps(bridge._probe_config(fixture)) + ';\n' +
            (ROOT/'agent/native_traps.js').read_text() + '\n' + (ROOT/'agent/profile_guard.js').read_text())
        guard.load()
        dev.resume(pid)
        await asyncio.sleep(10)
        controller = Runtime(out/'controller')
        original = bridge.script_text
        bridge.script_text = lambda *a, **kw: original(*a, **kw) + FIXTURE_RPC
        try: await asyncio.to_thread(controller.attach, pid)
        finally: bridge.script_text = original
        controller.script.on('message',lambda message,data:
            (out/'png.submitted').write_text(json.dumps(message))
            if message.get('payload',{}).get('event')=='fixture-png-submitted' else None)
        deadline = asyncio.get_running_loop().time()+30
        while not (await asyncio.to_thread(controller.script.exports_sync.health))['ready']:
            if asyncio.get_running_loop().time() > deadline: raise TimeoutError('fixture not ready')
            await asyncio.sleep(.1)
        await fixture_call('new_model', {'variant': variant})
        # A busy first frame can reject a queued read without executing it.
        # Retry only that read, never the model creation request.
        deadline = asyncio.get_running_loop().time() + 90
        while True:
            try:
                state = await controller._settle()
                break
            except Exception as error:
                if 'MAIN_THREAD_TIMEOUT: not executed' not in str(error) or asyncio.get_running_loop().time() >= deadline:
                    raise
                await asyncio.sleep(.5)
        original_file = lab/'saves'/'manual-source.vroid'
        original_file.parent.mkdir(exist_ok=True)
        await fixture_call('manual_save', {'path': str(original_file)})
        token = state['model_token']
        await controller.set_params('body', token, [{'id':'body/WholeBody/002','value':.15}])
        await controller.set_face_params(token, [{'id':'face/FaceSet/006','value':.4}])
        source_hash = hashlib.sha256(original_file.read_bytes()).hexdigest()
        passed('preexisting_manual_file_and_unsaved_body_face_edits')
        with (out/'server.log').open('w',encoding='utf8') as log:
            async with stdio_client(params, errlog=log) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=100)) as client:
                    await client.initialize()
                    async def call(name, args=None, error=None):
                        reply = await client.call_tool(name,args or {})
                        if error:
                            assert reply.isError and error in str(reply.content), reply
                            return
                        if reply.isError: raise RuntimeError(name+': '+str(reply.content))
                        return reply.structuredContent or json.loads(reply.content[0].text)
                    attached = await call('attach_open_vroid', {'pid':pid})
                    assert attached['attached_state']['unsaved'] and attached['attached_state']['file_path']==str(original_file)
                    token = attached['model_token']
                    assert attached['png_decoder']['mode']=='unity_owned_callbacks'
                    passed('adopt_unsaved_manual_state_and_managed_png_decoder')
                    await call('new_character', {'expected_model':token}, 'EXPLICIT_DISCARD_REQUIRED')
                    for next_variant in ('M00','F00',variant):
                        changed=await call('new_character',{'expected_model':token,'variant':next_variant,'discard_unsaved':True})
                        assert changed['model_token']!=token and alive()
                        token=changed['model_token']
                    passed('repeated_native_new_character_transition_same_pid')
                    external=target/'external-files';external.mkdir(exist_ok=True)
                    associated=await call('save_character_as',{'expected_model':token,'path':str(external/'new-character.vroid')})
                    assert associated['associated'] and Path(associated['path']).is_file()
                    assert (await call('get_status'))['attached_state']['file_path']==associated['path']
                    absolute_opened=await call('open_character',{'expected_model':token,'filename':associated['path'],'discard_unsaved':True})
                    token=absolute_opened['model_token']
                    assert absolute_opened['attached_state']['file_path']==associated['path']
                    passed('untitled_save_as_absolute_path_and_association',associated)
                    await call('open_character',{'expected_model':token,'filename':'manual-source.vroid'},'EXPLICIT_DISCARD_REQUIRED')
                    opened=await call('open_character',{'expected_model':token,'filename':'manual-source.vroid','discard_unsaved':True})
                    assert opened['model_token']!=token and opened['attached_state']['file_path']==str(original_file),opened
                    token=opened['model_token']
                    face=await call('list_face_params')
                    assert abs(next(p['value'] for p in face['parameters'] if p['id']=='face/FaceSet/006')-.4)>1e-4
                    await call('set_body_params',{'expected_model':token,'changes':[{'id':'body/WholeBody/002','value':.15}]})
                    await call('set_face_params',{'expected_model':token,'changes':[{'id':'face/FaceSet/006','value':.4}]})
                    passed('open_character_explicit_discard_and_fresh_identity')
                    saved_copy=await call('save_as',{'expected_model':token,'filename':'attached-copy.vroid'})
                    preserved=(await call('get_status'))['attached_state']
                    assert saved_copy['attached_copy'] and Path(saved_copy['path']).is_file()
                    assert preserved['file_path']==str(original_file) and preserved['unsaved'],preserved
                    assert hashlib.sha256(original_file.read_bytes()).hexdigest()==source_hash
                    passed('attached_save_copy_preserves_source_association_and_dirty',saved_copy)
                    old_hash=source_hash
                    overwritten=await call('save_character',{'expected_model':token})
                    assert overwritten['path']==str(original_file)
                    assert hashlib.sha256(Path(overwritten['backup_path']).read_bytes()).hexdigest()==old_hash
                    source_hash=hashlib.sha256(original_file.read_bytes()).hexdigest()
                    assert source_hash!=old_hash
                    clean=(await call('get_status'))['attached_state']
                    assert not clean['unsaved'] and clean['file_path']==str(original_file)
                    reopened=await call('open_character',{'expected_model':token,'filename':'manual-source.vroid','discard_unsaved':True})
                    token=reopened['model_token']
                    face=await call('list_face_params')
                    assert abs(next(p['value'] for p in face['parameters'] if p['id']=='face/FaceSet/006')-.4)<1e-6
                    await call('set_face_params',{'expected_model':token,'changes':[{'id':'face/FaceSet/006','value':.3}]})
                    passed('in_place_save_backup_clean_flag_and_reload',overwritten)
                    await fixture_call('progress_start')
                    await call('set_face_params', {'expected_model':token,'changes':[{'id':'face/FaceSet/006','value':.9}]}, 'ATTACHED_UI_BLOCKED')
                    await fixture_call('progress_finish')
                    assert not (await call('get_status'))['attached_state']['pending_edit']
                    passed('native_progress_lock_refuses_before_edit_receipt')
                    await fixture_call('dialog_show')
                    dialog=(await call('get_status'))['attached_state']['dialog']
                    assert dialog
                    await call('undo', {'expected_model':token}, 'ATTACHED_UI_BLOCKED')
                    await fixture_call('dialog_dismiss')
                    passed('native_modal_dialog_refuses_mutation', dialog)
                    # A disabled owner is the OS-level condition common-file
                    # dialogs impose. Windows state is restored in finally.
                    windows = attached_ui.window_state(pid)['windows']
                    assert windows
                    user=ctypes.WinDLL('user32');user.EnableWindow.argtypes=[ctypes.c_void_p,ctypes.c_int]
                    hwnd=windows[0]['window']
                    user.EnableWindow(hwnd,False)
                    try:
                        blocked=await call('get_status')
                        assert blocked['current_state_unavailable']
                        await call('undo',{'expected_model':token},'ATTACHED_OS_MODAL_BLOCKED')
                    finally: user.EnableWindow(hwnd,True)
                    passed('disabled_windows_owner_reports_unavailable_and_refuses_rpc')
                    helper=out/'file_dialog.py';helper.write_text(FILE_DIALOG)
                    dialog_process=await asyncio.create_subprocess_exec(sys.executable,str(helper),str(hwnd),str(target/'saves'),
                        stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
                    deadline=asyncio.get_running_loop().time()+15
                    while not attached_ui.window_state(pid)['blocked']:
                        if dialog_process.returncode is not None:raise RuntimeError('File dialog exited before showing')
                        if asyncio.get_running_loop().time()>deadline:raise TimeoutError('Real file dialog did not disable owner')
                        await asyncio.sleep(.05)
                    try:
                        blocked=await call('get_status');assert blocked['current_state_unavailable']
                        await call('undo',{'expected_model':token},'ATTACHED_OS_MODAL_BLOCKED')
                    finally:
                        user.FindWindowW.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p];user.FindWindowW.restype=ctypes.c_void_p
                        user.PostMessageW.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t]
                        deadline=asyncio.get_running_loop().time()+10
                        popup=None
                        while not popup and asyncio.get_running_loop().time()<deadline:
                            popup=user.FindWindowW('#32770','VRoid MCP isolated file dialog check')
                            if not popup:await asyncio.sleep(.05)
                        assert popup,'Test-owned file dialog not found'
                        user.PostMessageW(popup,0x111,2,0)  # IDCANCEL, only this test's dialog
                    stdout,stderr=await asyncio.wait_for(dialog_process.communicate(),10)
                    assert dialog_process.returncode==0 and stdout.strip()==b'cancelled',(stdout,stderr)
                    assert not attached_ui.window_state(pid)['blocked']
                    passed('real_windows_file_picker_blocks_rpc_then_cancel_restores_owner')
                    regions=(await call('list_texture_regions',{'expected_model':token}))['regions']
                    choices=[r for r in regions if r['part'] in ('BodySkin','Iris','Eyelid','FaceSkin')]
                    for region in choices[:4]:
                        await call('open_texture_editor',{'expected_model':token,'region_id':region['region_id']})
                        await call('close_texture_editor',{'expected_model':token})
                    passed('body_edits_then_repeated_texture_entries_same_pid',len(choices[:4]))
                    region=next(r for r in regions if r['part']==('Cheek' if any(r['part']=='Cheek' for r in regions) else 'FaceSkin'))
                    await call('open_texture_editor',{'expected_model':token,'region_id':region['region_id'],'bake_colors':True})
                    layers=(await call('list_texture_layers',{'expected_model':token,'region_id':region['region_id']}))['layers']
                    sample=await call('export_texture_layer',{'expected_model':token,'region_id':region['region_id'],'layer_id':layers[0]['layer_id']})
                    width,height,_=decode_rgba_png(Path(sample['path']).read_bytes())
                    rgba=bytearray(width*height*4)
                    for y in range(height//3,height//3+16):
                        for x in range(width//3,width//3+16):rgba[4*(y*width+x):4*(y*width+x)+4]=bytes([170,40,110,160])
                    png=png_rgba(width,height,rgba)
                    (lab/'saves'/'marker.png').write_bytes(png)
                    paint_args={'expected_model':token,'region_id':region['region_id'],
                        'image_id':json.dumps(layers[0]['image'],separators=(',',':')),'filename':'marker.png',
                        'layer_name':'Attached diagnostic','expected_png_sha256':hashlib.sha256(png).hexdigest()}
                    await call('import_texture_layer',paint_args)
                    await call('undo',{'expected_model':token});await call('redo',{'expected_model':token})
                    layers=(await call('list_texture_layers',{'expected_model':token,'region_id':region['region_id']}))['layers']
                    marker=next(l for l in layers if l.get('Name',l.get('name'))=='Attached diagnostic')
                    exported=await call('export_texture_layer',{'expected_model':token,'region_id':region['region_id'],'layer_id':marker['layer_id']})
                    assert decode_rgba_png(Path(exported['path']).read_bytes())[2]==bytes(rgba)
                    passed('texture_layer_exact_pixels_and_native_undo_redo')
                    management=await exercise_layers(call,lab,token,region['region_id'],'attached-layer-check',render=True)
                    passed('native_layer_management_rename_delete_order_26_blends_and_pixel_preservation',management['checks'])
                    # Refusal after dispatch is intentionally reviewable, not
                    # guessed to have left a complex canvas unchanged.
                    await call('set_body_params',{'expected_model':token,'changes':[{'id':'body/WholeBody/002','value':.2}]},'CLOSE_TEXTURE_EDITOR_FIRST')
                    assert not (await call('get_status'))['attached_state']['pending_edit']
                    passed('active_canvas_refuses_geometry_before_dispatch')
                    await call('close_texture_editor',{'expected_model':token})
                    saved=await call('save_custom_items',{'expected_model':token,'types':['Iris']})
                    assert saved['profile_scope']=='attached VRoid profile'
                    custom=saved['saved'][0]
                    assert Path(custom['path']).is_relative_to(target/'profile') and not Path(custom['path']).is_relative_to(lab)
                    report['custom_item']=custom
                    preserved=(await call('get_status'))['attached_state']
                    report['preserved_after_custom_save']=preserved
                    assert preserved['file_path']==str(original_file) and preserved['unsaved'],preserved
                    assert hashlib.sha256(original_file.read_bytes()).hexdigest()==source_hash
                    passed('new_custom_item_uses_target_profile_preserves_source_file_and_dirty_state')
                    review=await call('get_attached_state')
                    # Independent controller simulates a manual native edit;
                    # changing the model must invalidate the reviewed state.
                    native_token=(await controller._call('status'))['model_token']
                    await controller.set_face_params(native_token,[{'id':'face/FaceSet/006','value':.5}])
                    await call('acknowledge_attached_state',{'recovery_token':review['recovery_token']},'STALE_ATTACHED_REVIEW')
                    passed('manual_or_mcp_history_change_invalidates_review_token')
                    await call('detach_open_vroid')
                    reattached=await call('attach_open_vroid',{'pid':pid});token=reattached['model_token']
                    assert any(i['id']==custom['id'] for i in (await call('list_parts',{'expected_model':token}))['custom_items'])
                    passed('reattach_retains_registered_custom_item_and_unsaved_texture')
                    await call('detach_open_vroid')
        # Interrupt a real public layer import between native success and reply.
        callbacks=await fixture_call('png_callbacks')
        callbacks['png']=base64.b64encode(png_rgba(16,16,bytes([170,40,110,160])*256)).decode()
        (lab/'png-callbacks.json').write_text(json.dumps(callbacks))
        (lab/'interrupt.arm').write_text('test fixture only')
        with (out/'interrupted-server.log').open('w',encoding='utf8') as log:
            crashed_server=await asyncio.create_subprocess_exec(sys.executable,str(bootstrap),'--lab',str(lab),
                cwd=str(ROOT),env=dict(os.environ),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=log)
            seq=0
            async def rpc(method,args,wait=True):
                nonlocal seq
                seq+=1;req=seq
                crashed_server.stdin.write((json.dumps({'jsonrpc':'2.0','id':req,'method':method,'params':args})+'\n').encode())
                await crashed_server.stdin.drain()
                if not wait:return
                while True:
                    line=await asyncio.wait_for(crashed_server.stdout.readline(),100)
                    if not line:raise RuntimeError('host exited')
                    reply=json.loads(line)
                    if reply.get('id')==req:
                        if 'error' in reply or reply.get('result',{}).get('isError'):raise RuntimeError(str(reply))
                        r=reply['result'];return r.get('structuredContent') or (json.loads(r['content'][0]['text']) if r.get('content') else r)
            await rpc('initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'attached-interruption','version':'1'}})
            crashed_server.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n');await crashed_server.stdin.drain()
            a=await rpc('tools/call',{'name':'attach_open_vroid','arguments':{'pid':pid}})
            token=a['model_token'];host=a['adopted']['owner_pid']
            await rpc('tools/call',{'name':'open_texture_editor','arguments':{'expected_model':token,'region_id':region['region_id']}})
            layers=await rpc('tools/call',{'name':'list_texture_layers','arguments':{'expected_model':token,'region_id':region['region_id']}})
            paint_args.update(expected_model=token,image_id=json.dumps(layers['layers'][0]['image'],separators=(',',':')),layer_name='Interrupted diagnostic')
            await rpc('tools/call',{'name':'import_texture_layer','arguments':paint_args},False)
            async def watch_interrupted_reply():
                while True:
                    line=await crashed_server.stdout.readline()
                    if not line:return None
                    reply=json.loads(line)
                    if reply.get('id')==seq:return reply
            interrupted_reply=asyncio.create_task(watch_interrupted_reply())
            deadline=asyncio.get_running_loop().time()+60
            while not (lab/'interrupt.imported').exists():
                if interrupted_reply.done():raise RuntimeError('Import returned before interruption: '+str(interrupted_reply.result()))
                if asyncio.get_running_loop().time()>deadline:raise TimeoutError('interruption marker missing')
                await asyncio.sleep(.05)
            png_submission=asyncio.create_task(fixture_call('png_submit',callbacks))
            while not (out/'png.submitted').exists():
                if png_submission.done():raise RuntimeError('PNG submit did not enter hold: '+str(png_submission.result()))
                if asyncio.get_running_loop().time()>deadline:raise TimeoutError('PNG submission marker missing')
                await asyncio.sleep(.02)
            os.kill(host,signal.SIGTERM);await asyncio.wait_for(crashed_server.wait(),15)
            await interrupted_reply
            await png_submission
            assert alive();passed('forced_host_exit_mid_public_texture_import_keeps_target_alive')
            await asyncio.sleep(3.5)
            results=await fixture_call('png_results')
            assert results['count']==2 and not results['failed'],results
            assert results['items'][0]['readable'] and not results['items'][1]['readable'],results
            assert max(abs(a-b/255) for a,b in zip(results['items'][0]['pixel'],[170,40,110,160]))<1e-6
            passed('unity_owned_png_callbacks_finish_after_agent_unload_with_exact_pixels_and_readability',results)
        (lab/'interrupt.arm').unlink()
        # Recover with a different lab: the receipt belongs to the target process,
        # rather than being lost with the old server's filesystem or PID reuse.
        recovered_lab=target/'clients'/'recovery-client'
        recovery_params=StdioServerParameters(command=sys.executable,args=['-m','vroid_mcp.server','--lab',str(recovered_lab)],cwd=str(ROOT),env=dict(os.environ))
        with (out/'recovery-server.log').open('w',encoding='utf8') as log:
            async with stdio_client(recovery_params,errlog=log) as (read,write):
                async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=100)) as client:
                    await client.initialize()
                    # call() intentionally closes over the current client.
                    a=await call('attach_open_vroid',{'pid':pid});token=a['model_token']
                    assert a['writes_blocked'] and a['attached_state']['pending_edit']['tool']=='import_texture_layer'
                    await call('undo',{'expected_model':token},'ATTACHED_EDIT_NEEDS_REVIEW')
                    layers=(await call('list_texture_layers',{'expected_model':token,'region_id':region['region_id']}))['layers']
                    assert sum(l.get('Name',l.get('name'))=='Interrupted diagnostic' for l in layers)==1
                    interrupted=next(l for l in layers if l.get('Name',l.get('name'))=='Interrupted diagnostic')
                    exported=await call('export_texture_layer',{'expected_model':token,'region_id':region['region_id'],'layer_id':interrupted['layer_id']})
                    assert decode_rgba_png(Path(exported['path']).read_bytes())[2]==bytes(rgba)
                    passed('cross_client_recovery_preserves_receipt_blocks_writes_allows_exact_pixel_inspection')
                    review=await call('get_attached_state')
                    ack=await call('acknowledge_attached_state',{'recovery_token':review['recovery_token']})
                    assert ack['acknowledged'] and not ack['replayed']
                    await call('close_texture_editor',{'expected_model':token})
                    passed('review_acknowledgment_resumes_without_replay')
                    # Explicitly load the saved fixture into Dress-up. This is a
                    # file switch with discard_unsaved=true, not a hidden save.
                    (recovered_lab/'saves').mkdir(exist_ok=True)
                    import shutil
                    shutil.copyfile(original_file,recovered_lab/'saves'/'wear-source.vroid')
                    wear=await call('get_wear_status')
                    await call('open_wear_project',{'filename':'wear-source.vroid','expected_wear':wear['wear_token'],'discard_unsaved':False},'EXPLICIT_DISCARD_REQUIRED')
                    review=await call('get_attached_state');await call('acknowledge_attached_state',{'recovery_token':review['recovery_token']})
                    wear=await call('get_wear_status')
                    model=(await call('get_status'))['model_token']
                    switched=await call('open_current_in_wear',{'expected_model':model,'expected_wear':wear['wear_token'],'filename':'current-to-wear.vroid','switch_to_wear':True})
                    assert Path(switched['saved_character']['path']).is_file()
                    opened=switched['wear']
                    assert opened['active'] and alive()
                    passed('unsaved_current_saved_then_opened_in_dress_up',switched['saved_character'])
                    if xwear is not None:
                        shutil.copyfile(xwear, external/'attached-input.xwear')
                        imported=await call('import_xwear',{'filename':str(external/'attached-input.xwear'),'expected_wear':opened['wear_token']})
                        assert len(imported['added_item_ids']) and alive()
                        reread=await call('get_wear_status')
                        assert all(any(item['id']==item_id for item in reread['items']) for item_id in imported['added_item_ids'])
                        passed('attached_xwear_import_readback', {'added_item_ids': imported['added_item_ids'], 'items':reread['items']})
                        saved=await call('save_wear_project',{'filename':str(external/'attached-assembly.xroid'),'expected_wear':reread['wear_token']})
                        assert Path(saved['path']).is_file() and alive()
                        associated=await call('get_wear_status')
                        assert associated['save_path']==saved['path'],associated
                        opened=await call('open_wear_project',{'filename':saved['path'],'expected_wear':reread['wear_token'],'discard_unsaved':True})
                        assert opened['active'] and len(opened['items'])==len(reread['items']),opened
                        passed('attached_xroid_save_reopen_retains_wearables',saved)
                    await call('detach_open_vroid')
        assert hashlib.sha256(original_file.read_bytes()).hexdigest()==source_hash
        report['passed']=True
    except BaseException as e:
        report.update(passed=False,error=repr(e));raise
    finally:
        if dialog_process is not None and dialog_process.returncode is None:
            dialog_process.kill();await dialog_process.wait()
        if crashed_server is not None and crashed_server.returncode is None:
            crashed_server.kill();await crashed_server.wait()
        if controller is not None:await asyncio.to_thread(controller.close)
        if pid is not None:
            try:dev.kill(pid)
            except frida.ProcessNotFoundError:pass
        if guard_session:
            try:guard_session.detach()
            except frida.InvalidOperationError:pass
        (out/'checks.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    if report.get('passed'):
        cold=Runtime(target)
        try:
            await asyncio.to_thread(cold.start)
            await cold.initialize(model_file=original_file)
            face=await cold.list_face_params()
            body=await cold.list_params('body')
            assert abs(next(p['value'] for p in face['parameters'] if p['id']=='face/FaceSet/006')-.4)<1e-6
            assert abs(next(p['value'] for p in body['parameters'] if p['id']=='body/WholeBody/002')-.15)<1e-6
            passed('in_place_save_cold_process_face_body_persistence')
        except BaseException as error:
            report.update(passed=False,cold_error=repr(error));raise
        finally:
            await asyncio.to_thread(cold.close)
            (out/'checks.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--variant',choices=['F00','M00'],default='F00')
    parser.add_argument('--xwear', type=Path)
    args=parser.parse_args()
    asyncio.run(check(args.source,args.out,args.variant,args.xwear))
