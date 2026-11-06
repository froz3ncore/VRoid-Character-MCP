const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
let freed = 0;
class Native {
    constructor(name, fields = {}, methods = {}) {
        this.class = {name, methods:[]}; this.fields = fields; this.calls = methods;
        this.handle = this;
    }
    isNull() { return false; }
    equals(other) { return this === other; }
    tryField(name) { return Object.hasOwn(this.fields,name) ? {value:this.fields[name]} : null; }
    field(name) { const f=this.tryField(name); if(!f) throw Error('missing field '+name); return f; }
    tryMethod(name) { return this.calls[name] ? {invoke:(...args)=>this.calls[name](...args)} : null; }
    method(name) { const m=this.tryMethod(name); if(!m)throw Error('missing method '+name); return m; }
}
const string = value => new Native('String',{},{});
function s(value) { const o=string(); o.content=value; return o; }
const pair = (key,value)=>new Native('Pair',{Key:s(key),Value:value});
const dict = entries => entries.map(([key,value])=>pair(key,value));
const rgba = a => new Native('Color',Object.fromEntries(['r','g','b','a'].map((c,i)=>[c,a[i]])));
const float = value => ({value, writeFloat(v){this.value=v;}, writeU8(v){this.value=v;},
    add(offset){ return {writeFloat:v=>{this.channels??=[];this.channels[offset/4]=v;}}; }});
const context = vm.createContext({console,Il2Cpp:{string:s,corlib:{class:()=>{}},gc:{choose:()=>[]}},
    Memory:{alloc:()=>float(0)},NULL:null,retain:()=>({free(){freed++;}}),bridge:{retained:new Map()}});
vm.runInContext(fs.readFileSync('agent/groups.js','utf8'),context);

function setup() {
    const type='TransferableGroupType.N00.Level1.WholeBody';
    const group=new Native('Group',{Id:s('g'),Type:s(type),ResourceName:s('resource'),Revision:s('r'),
        EditableElements:new Native('Elements',{Count:2})});
    const rawColor=new Native('Parameter',{Key:s('color'),color:new Native('ColorParameter',{Color:rgba([.1,.2,.3,1])})});
    const rawBone=new Native('Parameter',{Key:s('negative'),boneTransform:new Native('Bone',{Value:0.})});
    const path = key=>new Native('BoneTransformPath',{Key:s(key)});
    const p=new Native('CombinedBoneTransformParameterViewModel',{_pathNegative:path('negative'),_pathPositive:path('positive')},
        {set_CombinedValue:value=>{p.value=value.value;}}); p.value=0;
    const active=new Native('Model',{TransferableGroups:dict([['g',group]])},{GetActiveTransferableGroups:()=>dict([['g',group]])});
    const nativeContext=new Native('Context',{}, {get_ActiveModel:()=>active,
        GetActiveLeafTransferableGroups:()=>dict([['g',group]]),GetActiveTransferableGroupInfo:()=>group,
        GetParametersForTransferableGroup:()=>dict([['bone',rawBone],['color',rawColor]]),GetActiveLeafTransferables:()=>[],
        RemoveTransferableGroupAndChildren:()=>{calls.push('remove');},
        ExecuteSyncCommand:command=>{calls.push('history');rawColor.fields.color.fields.Color=rgba(command.dictionary.value.channels);},
        LoadAndReplaceTransferableGroup:(id,ok,fail,flag)=>{calls.push(['preserve',flag.value]);rawColor.fields.color.fields.Color=rgba([.9,.9,.9,1]);}});
    const root=new Native('Root');
    const m={token:'live',context:nativeContext,root};
    const calls=[];
    const clear=new Native('Clear',{_transferableGroupType:s(type)});
    const presets=[{id:'clothing/WholeBody/none',clear:true,p:clear}];
    const classes={};
    const classFor=(name)=> {
        if(classes[name])return classes[name];
        const c={name:name.split('.').pop(),type:{name},alloc:()=>new Native(c.name,{}, {'.ctor':()=>{}}),methods:[]};
        classes[name]=c;return c;
    };
    const single={name:'Single',type:{name:'System.Single'}};
    const colorClass={name:'Color',type:{name:'UnityEngine.Color'}};
    classes['UnityEngine.Color']=colorClass;
    classes['VRoidCore.Common.TransferableTypes.Path.ColorPath']={name:'ColorPath',type:{name:'ColorPath'},
        alloc:()=>new Native('ColorPath',{}, {'.ctor':()=>{}})};
    const colorInterface=classFor('VRoidCore.Common.TransferableTypes.Path.IColorPath');
    const commandClass=classFor('VRoidCore.Editing.History.Command.SetColorParameterCommand');
    commandClass.methods=[{name:'.ctor',parameters:[{type:{name:'System.String'}},
        {type:{name:'IEnumerable<KeyValuePair<'+colorInterface.type.name+',UnityEngine.Color>>'}},{type:{name:'System.Boolean'}}]}];
    commandClass.alloc=()=>{const c=new Native('Command');c.calls['.ctor']=(group,dictionary)=>{c.dictionary=dictionary;};return c;};
    context.Il2Cpp.corlib.class=name=>name==='System.Single'?single:{inflate:(key,value)=>({alloc:()=>{
        const dictionary=new Native('Dictionary',{}, {'.ctor':()=>{},Add:(path,value)=>{dictionary.value=value;}});
        const original=dictionary.method.bind(dictionary);
        dictionary.method=(name,...args)=>name==='Add'?{...original(name),parameters:[{type:key.type},{type:value.type}]}:original(name,...args);
        return dictionary;}})};
    const api=context.createGroupApi({model:expected=>{if(expected!=='live')throw Error('STALE_MODEL');return m;},
        cls:(_assembly,name)=>classFor(name),text:o=>o?.content??null,state:{frame:9},
        invokeManaged:(object,name,args=[])=>object.method(name).invoke(...args),
        entries:(_model,area)=>area==='body'?[{id:'body/WholeBody/000',p}]:[],
        details:entry=>({semantic_status:'complete',semantic_group:type,semantic_kind:'combined',
            semantic_bindings:[{key:'negative'},{key:'positive'}],min:-1,max:1,editable:true,value:entry.p.value}),
        presetEntries:(_model,area)=>area==='clothing'?presets:[],ordinary:{managedCallbacks:()=>({ok:{handle:1},fail:{handle:2}})}});
    return {api:api.operations,helpers:api.helpers,calls,m,group,p,rawColor,classes,classFor,presets,type,active};
}
const args={expected_model:'live',group_id:'g'};
{
    const f=setup();let index=0;
    const iterator=new Native('ExplicitIterator',{}, {'System.Collections.IEnumerator.MoveNext':()=>index++===0,
        'System.Collections.IEnumerator.get_Current':()=>42,'System.IDisposable.Dispose':()=>{}});
    iterator.class.methods=Object.keys(iterator.calls).map(name=>({name}));
    const collection=new Native('ExplicitCollection',{}, {'System.Collections.IEnumerable.GetEnumerator':()=>iterator});
    collection.class.methods=Object.keys(collection.calls).map(name=>({name}));
    assert.deepEqual(f.helpers.sequence(collection),[42]);
    const template=new Native('TemplateBlendShapeTransformPath',{
        templatePath:new Native('TemplatePath',{Key:s('template|with|pipes')}),
        editableElementPath:new Native('BlendShapeTransformPath',{Value:s('inner')})});
    const descriptor=f.helpers.pathDescriptor(template);
    assert.equal(descriptor.template_key,'template|with|pipes');assert.equal(descriptor.element_key,'inner');
}
{
    const f=setup(), listed=f.api.list_groups(args);
    assert.equal(listed.groups[0].active_leaf,true);assert.equal(listed.groups[0].stored,true);
    assert.equal(listed.groups[0].removable,true);
    const parameters=f.api.list_group_parameters(args).parameters;
    assert.equal(parameters.find(p=>p.source==='exact_native_vm').units,'native_vm');
    const raw=parameters.find(p=>p.native_dictionary_key==='bone');
    assert.equal(raw.editable,false);assert.equal(raw.target_binding_ids[0],'body/WholeBody/000');
    assert.equal(parameters.find(p=>p.kind==='color').units,'native_rgba');
    assert.throws(()=>f.api.list_group_parameters({...args,group_id:'missing'}),/UNKNOWN_OR_STALE_GROUP/);
    assert.throws(()=>f.api.list_groups({...args,expected_model:'old'}),/STALE_MODEL/);
    const typed=parameters.find(p=>p.source==='exact_native_vm');
    assert.throws(()=>f.api.set_group_parameters({...args,changes:[{id:typed.id,type:'float',units:'native_vm',value:.2},
        {id:'label',type:'float',units:'native_vm',value:.3}]}),/UNKNOWN_OR_STALE_BINDING/);
    assert.equal(f.p.value,0);
    const result=f.api.set_group_parameters({...args,changes:[{id:typed.id,type:'float',units:'native_vm',value:-.3}]});
    assert.equal(result.ok,true);assert.equal(f.p.value,-.3);
    f.group.fields.Revision=s('new');
    assert.throws(()=>f.api.set_group_parameters({...args,changes:[{id:typed.id,type:'float',units:'native_vm',value:0}]}),/UNKNOWN_OR_STALE_BINDING/);
}
{
    const f=setup();
    const template=new Native('TemplateBlendShapeTransformPath',{
        templatePath:new Native('TemplatePath',{Value:s('garment-template')}),
        editableElementPath:new Native('BlendShapeTransformPath',{Key:s('garment-slider')})});
    const sliders=new Native('SliderResult',{blendShapes:[new Native('BlendShape',{path:template})]});
    f.classFor('VRoidCore.Editing.Query.GetTransferableGroupBlendShapesQuery').alloc=()=>new Native('Query',{},
        {'.ctor':(group,transferable)=>{assert.equal(group.content,'g');assert.equal(transferable,null);},Execute:()=>sliders});
    f.active.calls.GetBlendShapeTransformParameter=(group,path)=>{assert.equal(group.content,'g');assert.equal(path,template);return 37.5;};
    const common=new Native('CommonColor',{transferableGroupId:s('g'),elementKey:new Native('ColorPath',{Key:s('color')})});
    const result=new Native('ClothingResult',{sections:[new Native('TopCategory',{childSections:[
        new Native('ClothingTemplate',{childSections:[new Native('ColorGroup',{colors:[common]})]})]})]});
    f.classFor('VRoidCore.Editing.Query.AdvancedEdit.GetClothingQuery').alloc=()=>new Native('ClothingQuery',{},
        {'.ctor':groupType=>{assert.equal(groupType.content,f.type);},Execute:()=>result});
    f.m.context.calls.GetColorParameter=()=>rgba([.1,.2,.3,1]);
    const listed=f.api.list_group_parameters(args);
    const item=listed.parameters.find(p=>p.item_slider);
    assert.equal(item.value,37.5);assert.equal(item.units,'native_float_unknown_range');assert.equal(item.editable,false);
    assert.equal(item.native_bindings[0].template_key,'garment-template');
    const worn=listed.parameters.find(p=>p.source==='worn_color_query');
    assert.equal(worn.group_id,'g');assert.equal(worn.material_identity,null);assert.equal(worn.alias_ids.length,1);
    const raw=listed.parameters.find(p=>p.native_dictionary_key==='color');
    assert.throws(()=>f.api.set_group_parameters({...args,changes:[
        {id:raw.id,type:'color',units:'native_rgba',value:[.2,.2,.2,1]},
        {id:worn.id,type:'color',units:'native_rgba',value:[.3,.3,.3,1]}]}),/OVERLAPPING_BINDINGS/);
    assert.deepEqual(f.calls,[]);
}
{
    const f=setup(), color=f.api.list_group_parameters(args).parameters.find(p=>p.kind==='color');
    for(const value of [[0,0,0,2],[0,true,0,1],1]) assert.throws(()=>f.api.set_group_parameters({...args,
        changes:[{id:color.id,type:'color',units:'native_rgba',value}]}),/INVALID_TYPED_NATIVE_VALUE/);
    f.api.set_group_parameters({...args,changes:[{id:color.id,type:'color',units:'native_rgba',value:[.4,.5,.6,1]}]});
    assert.deepEqual(f.calls,['history']);
    assert.deepEqual(f.api.list_group_parameters(args).parameters.find(p=>p.kind==='color').value,[.4,.5,.6,1]);
    const typed=f.api.list_group_parameters(args).parameters.find(p=>p.source==='exact_native_vm');
    const badCommand=f.classFor('VRoidCore.Editing.History.Command.SetColorParameterCommand');
    const metadata=badCommand.methods;badCommand.methods=[];
    assert.throws(()=>f.api.set_group_parameters({...args,changes:[
        {id:typed.id,type:'float',units:'native_vm',value:.5},
        {id:color.id,type:'color',units:'native_rgba',value:[.2,.2,.2,1]}]}),/RAW_HISTORY_CONSTRUCTOR_UNSUPPORTED/);
    assert.equal(f.p.value,0,'all native history contracts must validate before the first write');
    badCommand.methods=metadata;
    const row=f.api.list_groups(args).groups[0];
    assert.throws(()=>f.api.remove_group({...args,group_fingerprint:'old'}),/NONREMOVABLE_OR_STALE/);
    f.api.remove_group({...args,group_fingerprint:row.fingerprint});assert.equal(f.calls.at(-1),'remove');
    f.presets.length=0;
    assert.throws(()=>f.api.remove_group({...args,group_fingerprint:row.fingerprint}),/NONREMOVABLE_OR_STALE/);
}
{
    const f=setup();
    assert.equal(f.helpers.sectionFor('other.WholeBody'),null);
    assert.equal(f.helpers.sectionFor(f.type),'Body');
    assert.equal(f.api.list_categories({...args,section:'Body'}).categories[0].id,f.type);
    assert.equal(f.api.enter_category({...args,section:'Body',category:f.type}).ui_navigation,false);
    assert.throws(()=>f.api.enter_category({...args,section:'Body',category:'WholeBody'}),/UNKNOWN_CATEGORY/);
    const second=new Native('Group',{Id:s('other'),Type:s(f.type),ResourceName:s('resource2'),Revision:s('r2')});
    f.active.calls.GetActiveTransferableGroups=()=>dict([['g',f.group],['other',second]]);
    f.m.context.calls.GetActiveLeafTransferableGroups=()=>dict([['g',f.group],['other',second]]);
    f.m.context.calls.GetActiveTransferableGroupInfo=id=>id.content==='g'?f.group:second;
    assert.equal(f.api.enter_category({...args,section:'Body',category:f.type}).ambiguous,true);
    assert.equal(f.api.list_group_parameters(args).parameters.filter(p=>p.source==='exact_native_vm').length,0);
}
{
    const f=setup();
    const catalog = dict([['locked',new Native('PresetModel',{resourceName:s('pixiv/VRoid/Hair/Front/N00/locked'),isOwned:false,priceInCoin:100,isSetItem:false})],
        ['free',new Native('PresetModel',{resourceName:s('pixiv/VRoid/Hair/Front/N00/free'),isOwned:false,priceInCoin:0,isSetItem:true})]]);
    f.m.main=new Native('Main',{_mainModel:new Native('MainModel',{playFabUser:new Native('User',{},
        {GetTransferableGroupIdToPresetModel:()=>catalog})})});
    const defaults=f.helpers.catalogPage(f.m,{offset:0,limit:1},[]);
    assert.equal(defaults.total,1);assert.equal(defaults.presets[0].id,'free');
    assert.equal(defaults.presets[0].selectable,false);assert.equal(defaults.presets[0].catalog_only,true);
    assert.equal(defaults.complete,true);
    const all=f.helpers.catalogPage(f.m,{offset:0,limit:1,owned_only:false},[]);
    assert.equal(all.total,2);assert.equal(all.next_offset,1);assert.equal(all.complete,false);
    const locked=f.helpers.catalogPage(f.m,{offset:0,limit:10,owned_only:false,search:'LOCKED'},[]);
    assert.equal(locked.presets[0].locked,true);assert.equal(locked.presets[0].selectable,false);
}
{
    const f=setup();
    const item={id:'g',group_type:f.type,path:'registered.vroidcustomitem',resource_name:'resource',revision:'r',
        custom_resource_name:'user/custom',custom_revision:'c'};
    const nativeItem=new Native('FileCustomItemModel',{FilePath:s(item.path),TransferableGroupId:s('g'),
        TransferableGroupTypeId:s(f.type),TransferableGroupResourceName:s('resource'),TransferableGroupRevision:s('r'),
        CustomItemId:new Native('CustomItemId',{ResourceName:s(item.custom_resource_name),Revision:s('c')})});
    const deserialized=new Native('CustomObject',{customItemMetaData:new Native('Meta',{rootTransferableGroupId:s('g')}),
        transferableGroups:dict([['g',f.group]])},{IsNecessarilyMigrateBodySuitsCustomItemV2:()=>false});
    const task=new Native('Task',{}, {get_IsCompleted:()=>true,get_IsCanceled:()=>false,get_IsFaulted:()=>false,get_Result:()=>new Native('Contents')});
    nativeItem.calls.LoadCustomItemContents=()=>task;
    const values=new Native('Dictionary',{}, {get_Values:()=>[nativeItem]});
    f.m.root.fields._customItemRegistry=new Native('Registry',{_pathToFileCustomItemModels:values},
        {CheckIfIsRegisteredInAssetStorage:resource=>resource.content==='resource'});
    f.classFor('VRoid.Studio.ModelPresetsSelector.CustomItemSerializationUtil').method=()=>({invoke:()=>deserialized});
    const started=f.api.custom_item_validate_begin({...args,registered_item:item,
        metadata:{rootTransferableGroupId:'g',rootTransferableGroupTypeId:f.type}});
    assert.equal(started.completed,false);
    assert.equal(f.api.custom_item_validate_poll({...args,request_id:started.request_id}).compatible,true);
    nativeItem.fields.TransferableGroupRevision=s('changed');
    assert.throws(()=>f.api.apply_registered_custom_item({...args,request_id:started.request_id,registered_item:item}),/STALE/);
    const before=freed;
    f.api.custom_item_validate_release({...args,request_id:started.request_id});
    assert.equal(freed-before,4,'native task/item/contents/object handles must be released only after terminal validation');
    nativeItem.fields.TransferableGroupRevision=s('r');
    deserialized.calls.IsNecessarilyMigrateBodySuitsCustomItemV2=()=>true;
    const migration=f.api.custom_item_validate_begin({...args,registered_item:item,
        metadata:{rootTransferableGroupId:'g',rootTransferableGroupTypeId:f.type}});
    const rejected=f.api.custom_item_validate_poll({...args,request_id:migration.request_id});
    assert.equal(rejected.compatible,false);assert.match(rejected.error,/MIGRATION_REQUIRED/);
    assert.throws(()=>f.api.apply_registered_custom_item({...args,request_id:migration.request_id,registered_item:item}),/NOT_VALIDATED/);
    f.api.custom_item_validate_release({...args,request_id:migration.request_id});
}
{
    const f=setup();
    f.m.root.fields._customItemRegistry=new Native('Registry',{_assetCatalog:new Native('Catalog',{}, {ContainsId:()=>true})});
    f.presets.push({id:'clothing/WholeBody/preset',owned:true,is_set_item:false,resource_name:'builtin',
        p:new Native('Preset',{}, {get_TransferableGroupId:()=>s('g')})});
    const started=f.api.apply_preserving_preset({...args,area:'clothing',preset_id:'clothing/WholeBody/preset'});
    assert.deepEqual(f.calls[0],['preserve',1]);
    assert.equal(f.api.preserving_preset_state({...args,request_id:started.request_id}).completed,true);
    f.api.restore_preset_materials({...args,request_id:started.request_id});
    const verified=f.api.preserved_preset_readback({...args,request_id:started.request_id});
    assert.equal(verified.outcomes[0].status,'restored');
    assert.equal(verified.outcomes.at(-1).status,'unverified');
    const incompatible=f.api.apply_preserving_preset({...args,area:'clothing',preset_id:'clothing/WholeBody/preset'});
    const commands=f.calls.filter(c=>c==='history').length;
    f.group.fields.Revision=s('replacement');
    const outcomes=f.api.restore_preset_materials({...args,request_id:incompatible.request_id}).outcomes;
    assert.equal(outcomes[0].status,'incompatible');
    assert.equal(f.calls.filter(c=>c==='history').length,commands);
    f.api.preserved_preset_readback({...args,request_id:incompatible.request_id});
    f.presets.at(-1).owned=false;
    assert.throws(()=>f.api.apply_preserving_preset({...args,area:'clothing',preset_id:'clothing/WholeBody/preset'}),/LOCKED/);
}
console.log('groups native doubles: discovery, exact pairing, prevalidation, history ABI, removal, custom preflight and preservation passed');
