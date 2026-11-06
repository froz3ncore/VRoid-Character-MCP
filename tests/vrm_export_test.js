// Native doubles execute the production adapter; no installed VRoid is loaded.
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const context = {console, Memory: {alloc: () => ({writeU8(v){this.value=v;this.kind='System.Boolean';},
    writeS32(v){this.value=v;this.kind='System.Int32';},writeFloat(v){this.value=v;this.kind='System.Single';},
    writeDouble(v){this.value=v;this.kind='System.Double';}})},
    Il2Cpp: {string: value => ({handle: value})}};
vm.createContext(context);
// Missing module is an intentional RED until the native adapter exists.
const file = 'agent/vrm_export.js';
assert.equal(fs.existsSync(file), true, 'native export settings adapter required');
vm.runInContext(fs.readFileSync(file, 'utf8'), context);
const nil = {handle: {isNull: () => true}};
let calls=[], frees=0, completed=false, fault=false, cancel=false, result=true;
const pointer = {isNull: () => false};
function object(values={}, fields={}) {
    const o={handle:pointer, fields, values};
    o.field = key => { if (!(key in fields)) throw Error('unknown field '+key); return fields[key]; };
    o.method = (name, count) => ({parameters:[{type:{name:
        ['set_MeshErasure','set_HairCrossSection','set_IsEnableHairCombination'].includes(name)?'System.Boolean':
            name==='set_HairReductionStrength'?'System.Single':'System.Int32'}}],invoke(...args){
        if (name.startsWith('get_')) {const v=values[name.slice(4)]; if(v===undefined)throw Error('unknown getter '+name); return typeof v==='function'?v():v;}
        if (name.startsWith('set_')) {calls.push(name); if(name!=='set_TextureCompressionModeIndex')values[name.slice(4)]=args[0];return;}
        throw Error('unexpected '+name);
    }});
    return o;
}
const enumValue={method:name=>({invoke:()=>{assert.equal(name,'ToString');return 'None';}})};
const list = (name,value) => object({Count:2, Item:object({TranslatedDisplayName:name, [value]:value==='MaterialReductionMode'?enumValue:3})});
const mesh=object({MeshErasure:true,HairCrossSection:false,HairSmoothnessRate:0,HairReductionStrength:2,
    FaceReductionStrength:0,BodyReductionStrength:0,ClothingReductionStrength:0});
const bones=object({HairReductionStrength:7});
const settings=object({MeshReduction:mesh,IsEnableHairCombination:true,MaterialReductionModeIndex:0,
    VRM0MetaData:nil,VRM10MetaData:nil,
    AtlasResolutionIndex:0,TextureCompressionModeIndex:0,
    MaterialReductionModeItems:list('Default','MaterialReductionMode'),AtlasResolutionItems:list('4096','AtlasResolution'),
    TextureCompressionModeItems:list('Original','TextureCompressionMode')},
    {hairBoneReduction:{value:bones}, textureCompressionModeIndex:{value:0}});
Object.defineProperty(settings.fields.textureCompressionModeIndex,'value',{
    get:()=>settings.values.TextureCompressionModeIndex,set:v=>{settings.values.TextureCompressionModeIndex=v;}});
const task=object({IsCompleted:()=>completed,IsFaulted:()=>fault,IsCanceled:()=>cancel,Result:()=>result,
    Exception:object({})});
task.method = name => ({invoke:()=> name==='get_Exception'?{method:()=>({invoke:()=> 'native fault'})}:task.values[name.slice(4)]()});
const completion=object({Task:task});
const completionClass={alloc:()=>completion};
const booth=object({ExportSettings:settings,PreviewAvatar:object(),IsActive:true},
    {_isBlockingUpdateExportPreview:{value:false},waitForPointerUpAndUpdateExportPreview:{value:nil}});
const baseMethod=booth.method;
booth.method = name => name.startsWith('OnVRM')? {parameters:[{}, {}, {type:{name:'System.Threading.Tasks.TaskCompletionSource<System.Boolean>',class:completionClass}}]} : baseMethod(name);
const model={token:'live',main:object({}, {_editModelTransform:{value:object({IsUpdatingModel:false})}}),
    root:object({}, {obsoleteLegacyPhotoBoothViewModel:{value:booth}})};
let throws=false;
const api=context.createVrmExportApi({model: token=>{assert.equal(token,'live');return model;},text:String,
    invokeManaged(o,n,args=[]){
        if(n==='.ctor')return;
        if(n.startsWith('set_')) {assert.equal(args[0].kind,o.method(n).parameters[0].type.name,'setter marshals its actual native parameter type');return o.method(n).invoke(args[0].kind==='System.Boolean'?!!args[0].value:args[0].value);}
        if(n.startsWith('OnVRM')) {calls.push(n); if(throws)throw Error('after dispatch'); return;}
        throw Error(n);
    },retain:()=>({free(){frees++;}}),metadata:()=>object()});
const ops=api.operations, args={expected_model:'live'};
model.root.fields.obsoleteLegacyPhotoBoothViewModel.value=nil;
assert.equal(ops.vrm_export_preview(args).ready,false,'missing booth is preparation state');
model.root.fields.obsoleteLegacyPhotoBoothViewModel.value=booth;
const snap=ops.vrm_export_options(args);
assert.equal(snap.settings.hair,2); assert.equal(snap.settings.hair_bones,7);
assert.equal(snap.choices.material_mode[0].name,'Default');
assert.equal(snap.choices.material_mode[0].value,'None');
ops.apply_vrm_export_options({...args,stage:'mesh',options:{hair:100,delete_transparent:false}});
assert.equal(mesh.values.HairReductionStrength,100); assert.equal(mesh.values.MeshErasure,false);
assert.throws(()=>ops.apply_vrm_export_options({...args,stage:'mesh',options:{hair:true}}));
assert.throws(()=>ops.apply_vrm_export_options({...args,stage:'texture',options:{texture_mode:2}}));
ops.apply_vrm_export_options({...args,stage:'material',options:{hair_bones:100,combine_hair:false,material_mode:1}});
assert.equal(bones.values.HairReductionStrength,100);assert.equal(settings.values.IsEnableHairCombination,false);
assert.equal(settings.values.MaterialReductionModeIndex,1);
ops.apply_vrm_export_options({...args,stage:'texture',options:{atlas_resolution:1,texture_mode:1}});
assert.equal(settings.values.AtlasResolutionIndex,1);assert.equal(settings.values.TextureCompressionModeIndex,1);
assert.equal(ops.vrm_export_options(args).settings.texture_mode,1,'readback includes backing-field fallback');
assert(calls.indexOf('set_AtlasResolutionIndex')<calls.indexOf('set_TextureCompressionModeIndex'));
assert.equal(ops.vrm_export_preview(args).ready,true);
booth.fields.waitForPointerUpAndUpdateExportPreview.value=object();
assert.equal(ops.vrm_export_preview(args).ready,false);
booth.fields.waitForPointerUpAndUpdateExportPreview.value=nil;
model.main.fields._editModelTransform.value.values.IsUpdatingModel=true;
assert.equal(ops.vrm_export_preview(args).ready,false);
model.main.fields._editModelTransform.value.values.IsUpdatingModel=false;
booth.values.PreviewAvatar=nil;assert.equal(ops.vrm_export_preview(args).ready,false);booth.values.PreviewAvatar=object();
booth.fields._isBlockingUpdateExportPreview.value=true;assert.equal(ops.vrm_export_preview(args).ready,false);
booth.fields._isBlockingUpdateExportPreview.value=false;
for(const version of [0,1]){
    completed=false; fault=false; cancel=false; result=true;
    ops.start_vrm_export({...args,version,path:'stage.vrm'});
    assert.equal(ops.vrm_export_status(args).running,true);
    assert.throws(()=>ops.finish_vrm_export(args));
    completed=true; result=false;
    assert.equal(ops.vrm_export_status(args).result,false);
    assert.equal(frees,version*4);
    fault=true;assert.equal(ops.vrm_export_status(args).faulted,true);
    fault=false;cancel=true;assert.equal(ops.vrm_export_status(args).canceled,true);
    cancel=false;result=true;
    assert.equal(ops.vrm_export_status(args).done,true);
    ops.finish_vrm_export({...args,output_stable:true});
}
assert(calls.includes('OnVRMSettingChanged')&&calls.includes('OnVRM1SettingChanged'));
assert.equal(frees,8);
throws=true;completed=false;
assert.throws(()=>ops.start_vrm_export({...args,version:1,path:'stage.vrm'}),/after dispatch/);
assert.throws(()=>ops.start_vrm_export({...args,version:1,path:'stage.vrm'}),/BUSY/);
assert.equal(frees,8);
console.log('vrm_export native doubles: settings, readiness, signatures, completion, retention passed');

// Exercise the existing metadata builder too: settings migration must not
// replace stored permissions with source defaults while adding model_version.
let buildMetadata;
const sourceValues={Title:'Stored title',Name:'Stored name',Version:'stored-version',Author:'Stored author',
    Authors:'Stored author',References:'Reference',AvatarPermission:2,ViolentUsage:1,SexualUsage:1,
    CommercialUsage:2,PoliticalOrReligiousUsage:1,AntisocialOrHateUsage:1,CreditNotation:1,
    Redistribution:1,Modification:2,AllowedUserName:2,ViolentUssageName:1,SexualUssageName:1,
    CommercialUssageName:2,LicenseName:3};
const source={field:name=>({value:sourceValues[name.replace(/^<|>k__BackingField$/g,'')]??'stored'})};
const metaObject=()=>{const fields={};return {handle:pointer,field:key=>(fields[key]??={value:null}),fields};};
const makeList=()=>{const items=[];return {items,method:n=>({invoke:v=>{if(n==='Add')items.push(v);else throw Error(n);}})};};
const metadataContext={console,createVrmExportApi:({metadata})=>{buildMetadata=metadata;return {operations:{}};},
    Il2Cpp:{string:s=>s,domain:{assemblies:[{image:{tryClass:()=>({new:metaObject})}}]},
        corlib:{class:()=>({inflate:()=>({new:makeList})})}}};
vm.createContext(metadataContext);
vm.runInContext(fs.readFileSync('agent/ordinary_extensions.js','utf8'),metadataContext);
metadataContext.createOrdinaryExtensions({model:()=>{},text:String,invokeManaged:()=>{},retain:()=>{},state:{}});
const storedModel={context:object({ActiveModel:object({AppState:object({Vrm0Export:source,Vrm1Export:source})})})};
const zero=buildMetadata(storedModel,0,nil,{model_version:'2'});
assert.equal(zero.fields.title.value,'Stored title');assert.equal(zero.fields.author.value,'Stored author');
assert.equal(zero.fields.version.value,'2');assert.equal(zero.fields.allowedUserName.value,'2');
assert.equal(zero.fields.licenseName.value,'3');assert.equal(zero.fields.texture.value,-1);
const one=buildMetadata(storedModel,1,nil,{title:'New title',author:'New author',model_version:'3'});
assert.equal(one.fields.Name.value,'New title');assert.equal(one.fields.Version.value,'3');
assert.deepEqual(one.fields.Authors.value.items,['New author']);
assert.equal(one.fields.AvatarPermission.value,2);assert.equal(one.fields.CommercialUsage.value,2);
assert.equal(one.fields.Modification.value,2);assert.equal(sourceValues.Version,'stored-version');
console.log('ordinary metadata native doubles: VRM0/1 stored permissions and optional overrides passed');
