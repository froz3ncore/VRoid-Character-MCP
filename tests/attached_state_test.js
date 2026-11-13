const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
vm.runInThisContext(fs.readFileSync('agent/attached_state.js','utf8'));
let environment=null, enabledDialog=false, busy=false, currentModel='model-1', activeScreen='EditRoot',receiptWriteMode='ok';
const nullHandle={isNull:()=>true,toString:()=> '0x0'};
const handle=s=>({isNull:()=>false,toString:()=>s});
const hooks=[];
global.ATTACHED=true;global.ATTACHED_OWNER_PID=101;
global.bridge={hooks:[],modelUpdates:0};
global.Interceptor={attach:(address,callbacks)=>{hooks.push(callbacks);return {detach(){}};}};
global.cls=()=>({method:()=>({virtualAddress:{isNull:()=>false}}),methods:[]});
global.Memory={allocUtf16String:s=>s,alloc:()=>({readUtf16String(){return this.text;}})};
global.NULL=null;
global.Process={getModuleByName:()=>({getExportByName:name=>name})};
global.NativeFunction=function(name){
    if(name==='GetEnvironmentVariableW')return (key,buffer)=>{buffer.text=environment;return environment?environment.length:0;};
    if(name==='SetEnvironmentVariableW')return (key,value)=>{environment=value;return receiptWriteMode==='write_then_fail'?0:1;};
    throw Error(name);
};
const object=(methods={},fields={},id='object')=>({handle:handle(id),class:{type:{name:id}},
    method:name=>({invoke:(...args)=>{assert(name in methods,name);return methods[name](...args);}}),
    field:name=>({value:fields[name]})});
const nil={handle:nullHandle};
const engine=object({get_Context:()=>object({get_IsCommandExecutable:()=>!busy,
    get_ActiveModel:()=>object({}, {}, currentModel)})},{},'engine');
const file=object({}, {engine,path:'source.vroid'},'file');
const main=()=>object({
    get_GlobalBus:()=>object({get_ScreenNavigation:()=>object({get_ActiveScreen:()=>object({}, {}, activeScreen)})}),
    get_DialogProviderViewModel:()=>object({get_Dialog:()=>enabledDialog?object({}, {}, 'UnsavedDialog'):nil,
        get_ActiveNotificationDialog:()=>nil}),
    get_ProgressProviderViewModel:()=>object({get_IsLocking:()=>busy}),
    get_PopupProviderViewModel:()=>object({get_IsActiveBlocker:()=>false}),
    get_ActionHandler:()=>object({get_IsUnSaved:()=>true}),
},{_mainModel:object({}, {currentFile:file}),_editModelTransform:object({get_IsUpdatingModel:()=>busy})});
const state={pngDecoder:{pending:0,fatal:null}};
let pending=[], releases=0, workOwner='original';
const create=()=>createAttachedState({main,text:x=>x,state,sessionTag:workOwner,
    observeWork:()=>({safe:!pending.length,pending_work:pending}),
    releaseWork:()=>{assert.equal(pending.length,0);releases++;return {safe:true};}});
let api=create();
enabledDialog=true;
assert.throws(()=>api.guard('attached_edit_begin'),/ATTACHED_UI_BLOCKED/);
assert.equal(environment,null);enabledDialog=false;
const receipt=api.operations.attached_edit_begin({tool:'import_texture_layer'});
api.guard('import_texture_layer');
assert.equal(JSON.parse(environment).dispatches,1);
assert(api.operations.attached_edit_finish({id:receipt.id,success:false}).needs_review);
// A new host has no prior JS state; the target's receipt still blocks it.
global.ATTACHED_OWNER_PID=202;api=create();
assert.throws(()=>api.guard('undo'),/ATTACHED_EDIT_NEEDS_REVIEW/);
api.guard('list_texture_layers');
assert.throws(()=>api.operations.attached_edit_begin({tool:'undo'}),/ATTACHED_EDIT_NEEDS_REVIEW/);
busy=true;assert.throws(()=>api.operations.attached_review(),/ATTACHED_STATE_NOT_IDLE/);busy=false;
const review=api.operations.attached_review();
currentModel='model-2';
assert.throws(()=>api.operations.attached_acknowledge({recovery_token:review.recovery_token}),/STALE_ATTACHED_REVIEW/);
const fresh=api.operations.attached_review();
pending=['custom selection'];
assert.throws(()=>api.operations.attached_acknowledge({recovery_token:fresh.recovery_token}),/NATIVE_WORK_PENDING/);
assert.throws(()=>api.operations.attached_review(),/NATIVE_WORK_PENDING/);
assert.equal(JSON.parse(environment).id,receipt.id);assert.equal(releases,0);
pending=[];
const recovered=api.operations.attached_review();
const ack=api.operations.attached_acknowledge({recovery_token:recovered.recovery_token});
assert.equal(ack.interrupted_edit.tool,'import_texture_layer');assert.equal(ack.replayed,false);
assert.equal(environment,null);
for (const native of ['start_vrm_export','open_from_menu','custom_item_validate_begin']) {
    const edit=api.operations.attached_edit_begin({tool:native});
    api.guard(native);
    api.operations.attached_edit_finish({id:edit.id,success:false,uncertain:true});
    workOwner='new';const orphan=create();
    assert.throws(()=>orphan.operations.attached_review(),/NATIVE_WORK_OWNER_LOST/);
    workOwner='original';api.confirmWorkReleased();
    const token=orphan.operations.attached_review().recovery_token;
    orphan.operations.attached_acknowledge({recovery_token:token});
}
api=create();
environment=JSON.stringify({id:'legacy',owner:101,dispatches:1,tool:'export_vrm'});
assert.throws(()=>api.operations.attached_review(),/NATIVE_WORK_OWNER_LOST/);
environment=null;
assert.throws(()=>api.operations.attached_acknowledge({recovery_token:fresh.recovery_token}),/STALE_ATTACHED_REVIEW/);
// Rejection before any mutation clears the new receipt without claiming work.
const rejected=api.operations.attached_edit_begin({tool:'save_custom_items'});
assert.equal(api.operations.attached_edit_finish({id:rejected.id,success:false,uncertain:false}).needs_review,false);
activeScreen='VRoid.Studio.TextureEditorScreen.ViewModel';
api.guard('enter_category'); // Group-bound read facade does not navigate or edit.
api.guard('custom_item_validate_poll');
api.guard('custom_item_application_state');
api.guard('preserving_preset_state');
for(const name of ['rename_texture_layer','delete_texture_layer','reorder_texture_layers','set_texture_layer_blend']) {
    const edit=api.operations.attached_edit_begin({tool:name});
    api.guard(name);
    assert.equal(api.operations.attached_edit_finish({id:edit.id,success:true,uncertain:false}).needs_review,false);
}
// Exercise the real guard between receipt acquisition and native preview entry.
vm.runInThisContext(fs.readFileSync('agent/editor_preview.js','utf8'));
environment=null;enabledDialog=false;activeScreen='EditRoot';
let previewWeight=10,setters=0,failSetter=false,cameraSetters=0;
const preview=createEditorPreview({beforeMutation:name=>api.guard(name),adapter:{
    open:()=>({token:'token',identity:'renderer:mesh'}),identity:()=> 'renderer:mesh',
    face:()=>[{index:0,name:'Smile',weight:previewWeight}],
    cameraState:()=>({angles:[0,0],rotating:false}),cameraAction:()=>cameraSetters++,
    setWeight(c,i,value){setters++;previewWeight=value;if(failSetter)throw Error('NATIVE_SETTER_RESPONSE_LOST');},
}});
let edit=api.operations.attached_edit_begin({tool:'face_preview'});
assert(preview.operations.face_preview({expected_model:'token',name:'Smile',weight:60}).ok);
api.operations.attached_edit_finish({id:edit.id,success:true,uncertain:false});
for(const blocker of ['dialog','canvas']){
    edit=api.operations.attached_edit_begin({tool:'face_preview'});
    enabledDialog=blocker==='dialog';activeScreen=blocker==='canvas'?'VRoid.Studio.TextureEditorScreen.ViewModel':'EditRoot';
    const blocked=preview.operations.face_preview({expected_model:'token',name:'Smile',weight:40});
    assert.equal(blocked.native_invocation_attempted,false);assert.equal(blocked.uncertain,false);
    assert.equal(blocked.dispatch_state,'prewrite_rejected');assert.equal(JSON.parse(environment).dispatches,0);
    const cameraBlocked=preview.operations.editor_camera({expected_model:'token',action:'angles',angles:[20,30]});
    assert.equal(cameraBlocked.uncertain,false);assert.equal(cameraBlocked.native_invocation_attempted,false);
    assert.equal(cameraSetters,0);assert.equal(JSON.parse(environment).dispatches,0);
    assert.equal(previewWeight,60);assert.equal(setters,1);assert.doesNotThrow(()=>preview.verify('token'));
    assert.equal(api.operations.attached_edit_finish({id:edit.id,success:false,uncertain:false}).needs_review,false);
    enabledDialog=false;activeScreen='EditRoot';
}
edit=api.operations.attached_edit_begin({tool:'face_preview'});
assert(preview.operations.face_preview({expected_model:'token',name:'Smile',weight:40}).ok);
assert.equal(setters,2);assert.equal(previewWeight,40);
api.operations.attached_edit_finish({id:edit.id,success:true,uncertain:false});
edit=api.operations.attached_edit_begin({tool:'face_preview'});receiptWriteMode='write_then_fail';
const uncertainGuard=preview.operations.face_preview({expected_model:'token',name:'Smile',weight:30});
receiptWriteMode='ok';assert.equal(uncertainGuard.uncertain,true);assert.equal(uncertainGuard.native_invocation_attempted,false);
assert.equal(uncertainGuard.dispatch_state,'guard_bookkeeping_unconfirmed');
assert.equal(JSON.parse(environment).dispatches,1);assert.equal(setters,2);assert.equal(previewWeight,40);
assert.doesNotThrow(()=>preview.verify('token'));
assert(api.operations.attached_edit_finish({id:edit.id,success:false,uncertain:true}).needs_review);
environment=null;edit=api.operations.attached_edit_begin({tool:'face_preview'});failSetter=true;
const uncertainSetter=preview.operations.face_preview({expected_model:'token',name:'Smile',weight:20});
assert.equal(uncertainSetter.native_invocation_attempted,true);assert.equal(uncertainSetter.uncertain,true);assert.equal(setters,3);
assert.equal(uncertainSetter.dispatch_state,'invocation_unconfirmed');
assert.throws(()=>preview.verify('token'),/UNCONFIRMED/);
assert(api.operations.attached_edit_finish({id:edit.id,success:false,uncertain:true}).needs_review);
console.log('real attached preview boundary: blocked UI/canvas, preserved weights, dismissal, receipt-write loss and partial setter passed');
// Restore the fixture baseline for the pre-existing texture/hair guard cases.
environment=null;activeScreen='VRoid.Studio.TextureEditorScreen.ViewModel';
assert.throws(()=>api.guard('set_body_params'),/CLOSE_TEXTURE_EDITOR_FIRST/);
console.log('attached state guards, cross-host receipt and stale review checks passed');
activeScreen='EditRoot';
assert.equal(typeof api.hairPrewriteCheckpoint,'function','native prewrite identity checkpoint missing');
{
    const receipt=api.operations.attached_edit_begin({tool:'scale_brush_hair'});
    const checkpoint=api.hairPrewriteCheckpoint('scale_brush_hair');api.guard('scale_brush_hair');
    const rejected={ok:false,dispatch_state:'prewrite_rejected',native_invocation_attempted:false,
        attempted_commands:0,command_count:0,uncertain:false};
    assert.equal(api.verifyHairPrewrite('scale_brush_hair',checkpoint,rejected),true);
    assert.equal(api.operations.attached_edit_finish({id:receipt.id,success:false,uncertain:false}).needs_review,false);
}
{
    const receipt=api.operations.attached_edit_begin({tool:'clone_brush_hair'});
    const checkpoint=api.hairPrewriteCheckpoint('clone_brush_hair');api.guard('clone_brush_hair');
    hooks.at(-1).onLeave(); // A native/manual history change invalidates the proof.
    assert.equal(api.verifyHairPrewrite('clone_brush_hair',checkpoint,{ok:false,dispatch_state:'prewrite_rejected',
        native_invocation_attempted:false,attempted_commands:0,command_count:0,uncertain:false}),false);
    assert.equal(api.operations.attached_edit_finish({id:receipt.id,success:false,uncertain:true}).needs_review,true);
}
