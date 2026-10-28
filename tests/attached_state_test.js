const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
vm.runInThisContext(fs.readFileSync('agent/attached_state.js','utf8'));
let environment=null, enabledDialog=false, busy=false, currentModel='model-1', activeScreen='EditRoot';
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
    if(name==='SetEnvironmentVariableW')return (key,value)=>{environment=value;return 1;};
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
const create=()=>createAttachedState({main,text:x=>x,state});
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
const ack=api.operations.attached_acknowledge({recovery_token:fresh.recovery_token});
assert.equal(ack.interrupted_edit.tool,'import_texture_layer');assert.equal(ack.replayed,false);
assert.equal(environment,null);
assert.throws(()=>api.operations.attached_acknowledge({recovery_token:fresh.recovery_token}),/STALE_ATTACHED_REVIEW/);
// Rejection before any mutation clears the new receipt without claiming work.
const rejected=api.operations.attached_edit_begin({tool:'save_custom_items'});
assert.equal(api.operations.attached_edit_finish({id:rejected.id,success:false,uncertain:false}).needs_review,false);
activeScreen='VRoid.Studio.TextureEditorScreen.ViewModel';
for(const name of ['rename_texture_layer','delete_texture_layer','reorder_texture_layers','set_texture_layer_blend']) {
    const edit=api.operations.attached_edit_begin({tool:name});
    api.guard(name);
    assert.equal(api.operations.attached_edit_finish({id:edit.id,success:true,uncertain:false}).needs_review,false);
}
assert.throws(()=>api.guard('set_body_params'),/CLOSE_TEXTURE_EDITOR_FIRST/);
console.log('attached state guards, cross-host receipt and stale review checks passed');
