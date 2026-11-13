'use strict';
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const context = {ATTACHED:true, ATTACHED_OWNER_PID:41};
vm.runInNewContext(fs.readFileSync('agent/session_workflows.js','utf8'), context);
const edit = 'VRoid.Studio.EditRootScreen.ViewModel', home = 'VRoid.Studio.StartScreen.ViewModel';
const handle = id => ({equals:other => other.id === id, isNull:() => !id, id});
let active, file, dirty, blocked, window, calls, attached, pins, menuMode = 1, revision = 0;
function object(id, type, methods={}, fields={}) {
    return {handle:handle(id), class:{type:{name:type}},
        method:key => ({invoke:() => methods[key]()}), field:key => ({value:fields[key]()})};
}
const photo = object(12,'photo',{get_IsActive:() => false});
const root = object(1,edit,{}, {obsoleteLegacyPhotoBoothViewModel:() => photo});
const enumValue = n => ({field:() => ({value:n})});
const menuScreen = object(2,home,{get_StartScreenMode:() => ({...enumValue(menuMode),
    class:{field:() => ({value:enumValue(1)})}}), get_MainViewModel:() => main});
const navigation = object(3,'navigation',{get_ActiveScreen:() => active});
const bus = object(4,'bus',{get_ScreenNavigation:() => navigation});
const model = object(5,'model',{}, {currentFile:() => file});
const transform = object(7,'transform',{get_IsUpdatingModel:() => false});
const main = object(6,'main',{get_GlobalBus:() => bus},
    {_mainModel:() => model, _editModelTransform:() => transform});
const editor = {root, context:object(8,'ctx',{get_IsCommandExecutable:() => true})};
active = root; file = object(9,'file'); dirty = true; blocked = false; window = '0xf'; calls = []; pins = 0;
const session = context.createSessionWorkflows({main:() => main, model:token => {
    if (token && token !== 'm') throw Error('STALE_MODEL');
    return editor;
}, ui:() => ({unsaved:dirty, progress_locked:blocked, pending_edit:attached}),
retain:() => { pins++; return {free:() => pins--}; }, sessionTag:'test', invalidateModel:() => {},
nativeProfile:() => ({session:true}), invoke:(_,name) => calls.push(name),
newModel:args => calls.push(args.variant), openFile:args => calls.push(args.path),
windowIdentity:() => window, png:() => ({installed:true,pending:0}), guard:() => {}, navigationRevision:() => revision});

const args = {expected_model:'m', window:'0xf'};
const s = new Proxy(session.operations, {get:(ops,name) => args => {
    if (!attached) attached = {owner:41,tool:name,id:'r'};
    const result = ops[name]({...args,receipt_id:'r'});
    attached = null;
    return result;
}});
assert.match(s.return_to_main_menu(args).error,/DISCARD/);
dirty = null;
assert.match(s.exit_vroid({...args, discard_unsaved:true, close_attached:true}).error,/DIRTY/);
dirty = false;
assert.match(s.exit_vroid(args).error,/CLOSE_ATTACHED/);
blocked = true;
assert.match(s.exit_vroid({...args,close_attached:true}).error,/BLOCKED/);
blocked = false; active = object(20,edit);
assert.match(s.return_to_main_menu(args).error,/CHANGED/);
active = root; attached = {owner:99,tool:'exit_vroid'};
assert.match(s.exit_vroid({...args,close_attached:true}).error,/REVIEW/);
attached = null;
assert.deepEqual(calls,[]);
assert.equal(s.exit_vroid({...args,close_attached:true}).requested,true);
assert.equal(s.return_to_main_menu(args).requested,true);
assert.deepEqual(calls,['<WantsToQuitHandler>g__Quit|61_0','<BackToModelSelect>g__BackToStartScreen|103_0']);
active = menuScreen;
assert.equal(session.view().menu_token,null);  // currentFile still owns the previous model
file = object(0,'null');
menuMode = 2;
assert.equal(session.view().menu_token,null);
menuMode = 1;
const generation = session.view().menu_token;
revision++;
assert.notEqual(session.view().menu_token,generation);
for (const variant of ['F00','M00']) {
    const expected_menu = session.view().menu_token;
    assert.equal(pins,1);
    const request = {window, expected_menu, variant, confirm_attached:true};
    assert.match(s.create_from_menu({...request, confirm_attached:false}).error,/CONFIRM/);
    s.create_from_menu(request);
    assert.equal(pins,0);
    assert.equal(calls.at(-1),variant);
    assert.match(s.create_from_menu(request).error,/STALE_MENU/);
}
const token = session.view().menu_token;
window = '0xb';
assert.match(s.open_from_menu({window, expected_menu:token, confirm_attached:true, path:'archive'}).error,/STALE_MENU/);
const expected_menu = session.view().menu_token;
s.open_from_menu({window,expected_menu,confirm_attached:true,path:'archive'});
assert.equal(calls.at(-1),'archive');
function observedVariant(value) {
    let item = {string:value, handle:handle(11)};
    for (const getter of ['get_BlendShapeSynthesisType','get_BlendShapeSynthesisParameters',
                          'get_Global','get_BaseCollection','get_ActiveModel']) {
        const next = item;
        item = {handle:handle(10),tryMethod:name => name === getter ? {invoke:() => next} : null};
    }
    return context.sessionModelVariant(item, s => s.string);
}
assert.equal(observedVariant('M00'),'M00');
assert.equal(observedVariant('F00'),'F00');
console.log('session guard, dirty, exit and menu identities passed');
