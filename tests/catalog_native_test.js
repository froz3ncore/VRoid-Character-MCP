const assert=require('assert'),fs=require('fs'),vm=require('vm');
class Native{
    constructor(name,fields={},methods={}){this.class={name,type:{name:'VRoid.Studio.ModelPresetsSelector.'+name}};
        this.fields=fields;this.calls=methods;this.handle=this;}
    isNull(){return false;}equals(other){return this===other;}
    field(name){if(!(name in this.fields))throw Error('missing field '+name);return {value:this.fields[name]};}
    method(name,count){const fn=this.calls[name];if(!fn)throw Error('missing method '+name);
        const scope='VRoid.Studio.ModelPresetsSelector.',collection='System.Collections.Generic.IReadOnlyCollection<';
        const types=name==='OnUpdate'?[collection+scope+'ObservedCustomItem>',collection+scope+'CustomItemObservationFailureItem>']:
            name==='NotifyUpdateFiles'?['System.Collections.Generic.List<'+scope+'CustomItemObservationFailureItem>']:[];
        if(['OnUpdate','NotifyUpdateFiles','QueueUpdate'].includes(name)&&count!==types.length)
            throw Error('wrong parameter count for '+name);
        if(this.badNotify&&name==='NotifyUpdateFiles')types[0]='System.Collections.Generic.List<Other.CustomItemObservationFailureItem>';
        return {
        invoke:(...args)=>fn(...args),isStatic:false,
        parameters:types.map(name=>({type:{name}})),returnType:{name:'System.Void'},
        virtualAddress:{name,isNull:()=>false}};}
}
function dictionary(items,count=items.length){return new Native('Dictionary',{}, {
    get_Count:()=>count,get_Values:()=>new Native('Values',{}, {GetEnumerator:()=>{
        let i=-1;return new Native('Enumerator',{}, {MoveNext:()=>++i<items.length,get_Current:()=>items[i],Dispose:()=>{}});
    }})});}
let hooks=new Map(),frees=0,queues=0;
const ctx=vm.createContext({console,Date,Map,Set,JSON,Number,Error,setTimeout,clearTimeout,
    Process:{getCurrentThreadId:()=>1},Interceptor:{attach:(address,callbacks)=>{
        hooks.set(address.name,callbacks);return {detach:()=>hooks.delete(address.name)};}}});
if(fs.existsSync('agent/build_profiles.js'))vm.runInContext(fs.readFileSync('agent/build_profiles.js','utf8'),ctx);
vm.runInContext(fs.readFileSync('agent/catalog.js','utf8'),ctx);
const custom=new Native('CustomItemId',{ResourceName:'user/resource',Revision:'c1'});
const file=new Native('FileCustomItemModel',{CustomItemId:custom,FilePath:'E:/registered/a.vroidcustomitem',
    TransferableGroupId:'group',TransferableGroupTypeId:'TransferableGroupType.N00.Level2.Tops',
    TransferableGroupResourceName:'group/resource',TransferableGroupRevision:'r1',DisplayName:'Top'});
const failure=new Native('CustomItemObservationFailureItem',{CustomItemPath:'E:/registered/bad.vroidcustomitem'});
let observed=true;
const registry=new Native('CustomItemRegistry',{
    _pathToFileCustomItemModels:dictionary([file]),_pathToObservationFailureItems:dictionary([])}, {
        OnUpdate:()=>{},NotifyUpdateFiles:()=>{},QueueUpdate:()=>{queues++;
            if(!observed)return;
            const update=hooks.get('OnUpdate'),notify=hooks.get('NotifyUpdateFiles'),frame={};
            // Wrong registry and Notify without an active matching OnUpdate cannot complete.
            notify.onEnter([{}]);
            update.onEnter.call(frame,[registry]);notify.onEnter([registry]);update.onLeave.call(frame);
        },CheckIfIsRegisteredInAssetStorage:()=>true});
const engine=new Native('Engine'),root=new Native('Root',{_customItemRegistry:registry});
const H={model:token=>{assert.equal(token,'token');return {token,engine,root};},
    presetEntries:()=>[],helpers:{prop:(o,key)=>o.fields[key],catalogRows:()=>[]},text:o=>o,
    build:'ed65ebbc1e806db635566347a9022b9577f6b3d373db128ea23f0e862e005296',retain:()=>({free:()=>frees++})};
let api=ctx.createNativePresetCatalog(H),ops=api.operations;
let receipt=ops.preset_catalog_begin({expected_model:'token'});
let result=ops.preset_catalog_poll({expected_model:'token',...receipt});
assert.equal(result.completed,true);assert.equal(result.custom_complete,true);assert.equal(result.rows[0].resource,'user/resource');
assert.equal(hooks.size,0);assert.equal(frees,1);assert.equal(queues,1);
ops.preset_catalog_release({expected_model:'token',...receipt});
// Actual signed failure dictionary: one good row and one failed observation.
registry.fields._pathToObservationFailureItems=dictionary([failure]);
receipt=ops.preset_catalog_begin({expected_model:'token'});
result=ops.preset_catalog_poll({expected_model:'token',...receipt});
assert.equal(result.custom_complete,false);assert.equal(result.rows.length,1);
assert.match(result.errors.join(' '),/bad.vroidcustomitem/);
ops.preset_catalog_release({expected_model:'token',...receipt});
// Silent/truncated enumerator is not evidence of an empty registry.
registry.fields._pathToFileCustomItemModels=dictionary([],1);
receipt=ops.preset_catalog_begin({expected_model:'token'});
result=ops.preset_catalog_poll({expected_model:'token',...receipt});
assert.equal(result.custom_complete,false);assert.equal(result.rows.length,0);
assert.match(result.errors.join(' '),/ENUMERATION_INCOMPLETE/);
ops.preset_catalog_release({expected_model:'token',...receipt});
observed=false;
receipt=ops.preset_catalog_begin({expected_model:'token'});
assert.equal(hooks.size,2);assert.equal(ops.preset_catalog_poll({expected_model:'token',...receipt}).completed,false);
api.dispose();assert.equal(hooks.size,0);assert.equal(frees,4);
// A replacement registry in the same root/token invalidates the observation.
api=ctx.createNativePresetCatalog(H);ops=api.operations;
receipt=ops.preset_catalog_begin({expected_model:'token'});
root.fields._customItemRegistry=new Native('CustomItemRegistry',registry.fields,registry.calls);
assert.throws(()=>ops.preset_catalog_poll({expected_model:'token',...receipt}),/OWNER_CHANGED/);
assert.equal(hooks.size,0);root.fields._customItemRegistry=registry;api.dispose();
// Final receipt release repeats ownership checks after a completed snapshot.
observed=true;registry.fields._pathToFileCustomItemModels=dictionary([]);
registry.fields._pathToObservationFailureItems=dictionary([]);
api=ctx.createNativePresetCatalog(H);ops=api.operations;
receipt=ops.preset_catalog_begin({expected_model:'token'});
assert.equal(ops.preset_catalog_poll({expected_model:'token',...receipt}).completed,true);
root.fields._customItemRegistry=new Native('CustomItemRegistry',registry.fields,registry.calls);
assert.throws(()=>ops.preset_catalog_release({expected_model:'token',...receipt}),/OWNER_CHANGED/);
assert.equal(hooks.size,0);root.fields._customItemRegistry=registry;api.dispose();
// Unproven builds still enumerate builtins, but cannot authorize custom removals.
const wrongRegistry=new Native('OtherRegistry',registry.fields,registry.calls),beforeWrong=queues;
root.fields._customItemRegistry=wrongRegistry;
api=ctx.createNativePresetCatalog(H);ops=api.operations;
receipt=ops.preset_catalog_begin({expected_model:'token'});
result=ops.preset_catalog_poll({expected_model:'token',...receipt});
assert.equal(result.custom_complete,false);assert.equal(queues,beforeWrong);
ops.preset_catalog_release({expected_model:'token',...receipt});api.dispose();
root.fields._customItemRegistry=registry;
api=ctx.createNativePresetCatalog({...H,build:'other'});ops=api.operations;
receipt=ops.preset_catalog_begin({expected_model:'token'});
result=ops.preset_catalog_poll({expected_model:'token',...receipt});
assert.equal(result.custom_complete,false);assert.match(result.errors.join(' '),/BUILD_UNSUPPORTED/);
ops.preset_catalog_release({expected_model:'token',...receipt});api.dispose();
for(const build of ['3334b166e298682eeda1ca1c5ca568b12f7085b76cc629668fe8b192af816bd8',
    'c8daa116938b40896e3a09208bbde71604a92d5ca6d86f9ff8b89fea3c1a5ad2']){
    for(const bad of [false,true]){
        registry.badNotify=bad;
        const count=queues;
        api=ctx.createNativePresetCatalog({...H,build});ops=api.operations;
        receipt=ops.preset_catalog_begin({expected_model:'token'});
        result=ops.preset_catalog_poll({expected_model:'token',...receipt});
        assert.equal(result.custom_complete,!bad);
        assert.equal(queues,count+(bad?0:1));
        ops.preset_catalog_release({expected_model:'token',...receipt});api.dispose();
    }
}
// A second observer generation may have cleared the same dictionary in place.
// Equal reads of those interim empty tables must never certify removals.
registry.badNotify=false;
function updateFrame(){
    const update=hooks.get('OnUpdate'),notify=hooks.get('NotifyUpdateFiles'),frame={};
    update?.onEnter.call(frame,[registry]);
    return {notify:()=>notify?.onEnter([registry]),leave:()=>update?.onLeave.call(frame)};
}
for(const race of ['paused','left_without_notify','during_enumeration','settled_again']){
    const before=frees;api=ctx.createNativePresetCatalog(H);ops=api.operations;
    const items=dictionary([]);registry.fields._pathToFileCustomItemModels=items;
    receipt=ops.preset_catalog_begin({expected_model:'token'});
    if(race==='during_enumeration'){
        const count=items.calls.get_Count;let reads=0;
        items.calls.get_Count=()=>{
            if(++reads===3){const next=updateFrame();next.notify();next.leave();}
            return count();
        };
    }else{
        const next=updateFrame();
        if(race==='settled_again')next.notify();
        if(race!=='paused')next.leave();
    }
    result=ops.preset_catalog_poll({expected_model:'token',...receipt});
    assert.equal(result.completed,true,race);
    assert.equal(result.custom_complete,race==='settled_again',race);
    assert.equal(hooks.size,0,race);assert.equal(frees,before+1,race);
    ops.preset_catalog_release({expected_model:'token',...receipt});api.dispose();
}
console.log('exact registry descriptors, stable generation, failure table and cleanup passed');
