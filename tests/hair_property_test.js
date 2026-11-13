// Reuse the existing native UI-owned property; no constructor/subscription/UI writes.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
vm.runInThisContext(fs.readFileSync('agent/parameters.js','utf8'));
global.createColorState=()=>({});
global.retain=()=>{throw Error('property lookup must not retain/create an owner');};
function object(methods={},fields={},nativeType='Fixture'){
    const id={},o={class:{type:{name:nativeType}},handle:{isNull:()=>false,equals:p=>p===o.handle},
        method:n=>({invoke:(...a)=>{assert(methods[n],n);return methods[n](...a);}}),
        tryMethod:n=>methods[n]?o.method(n):null,field:n=>({value:fields[n]})};return o;
}
let allocations=0,selected=0;
const api=createParameterApi({cls:()=>{allocations++;throw Error('no allocation');},text:x=>x});
assert.equal(typeof api.hairGroupHelpers.existingHairGroupProperty,'function','existing property route missing');
const engine=object(),foreign=object(),file=object(),action=object(),resources=object();
const engineVM=object({}, {_model:engine}),hairModel=object({}, {_engine:engine});
const path=(tid,gid)=>object({get_TransferableId:()=>tid,get_HairGroupId:()=>gid});
let bound=path('sibling','hidden');
const property=object({}, {_engine:engine,get _proceduralHairGroupPath(){return bound;}},
    'VRoid.Studio.HairEditor.DesignEditor.HairGroup.ViewModel.ProceduralHairGroupPropertyViewModel');
let actualProperty=property;
const design=object({get_Property:()=>actualProperty,get_Resources:()=>resources,set_SelectedItem:()=>selected++},
    {_engine:engine,_model:hairModel,_engineViewModel:engineVM,_currentFileViewModel:file,_mainActionHandler:action},
    'VRoid.Studio.HairEditor.DesignEditor.ViewModel');
const hair=object({get_DesignEditor:()=>design,get_Model:()=>hairModel});
const m={engine,root:object({get_HairEditor:()=>hair,get_Resources:()=>resources}),
    main:object({get_CurrentFile:()=>file,get_ActionHandler:()=>action})};
assert.equal(api.hairGroupHelpers.existingHairGroupProperty(m,path('sibling','hidden')),property);
assert.equal(allocations,0);assert.equal(selected,0);
assert.throws(()=>api.hairGroupHelpers.existingHairGroupProperty(m,path('t','g')),/EXISTING_PROPERTY_REQUIRED/);
actualProperty={handle:{isNull:()=>true}};
assert.throws(()=>api.hairGroupHelpers.existingHairGroupProperty(m,path('t','g')),/EXISTING_PROPERTY_REQUIRED/);
assert.equal(allocations,0);assert.equal(selected,0);
console.log('Exact existing UI-owned property reuse, hidden selected path and definite prewrite fallback passed');
