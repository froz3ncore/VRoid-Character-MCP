const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
vm.runInThisContext(fs.readFileSync('agent/groups.js','utf8'));
assert.equal(typeof certifySituationMembers,'function','sets need a bounded owned native entry graph certificate');
const root={id:'set',type:'ClothingSet',resource_name:'set/resource',revision:'r1',updated_since_last_revision:false},
    child={id:'top',type:'Tops',resource_name:'top/resource',revision:'r2',updated_since_last_revision:false};
const graph={set:{...root,entries:[{type:'TransferableGroup',id:'top'}]},
    top:{...child,entries:[{type:'Transferable',id:'mesh'}]}};
const result=certifySituationMembers(root,[root,child],id=>graph[id]);
assert.equal(result.verified,true);assert.deepEqual(result.members,[root,child]);
for(const type of ['RecommendedTransferableGroup','Clear','ClearByResourceName','Unknown']){
    graph.set.entries=[{type,id:'top'}];assert.throws(()=>certifySituationMembers(root,[root,child],id=>graph[id]));
}
graph.set.entries=[{type:'TransferableGroup',id:'top'}];
assert.throws(()=>certifySituationMembers({...root,resource_name:'alien'},[root,child],id=>graph[id]));
graph.top.entries=[{type:'TransferableGroup',id:'set'}];assert.throws(()=>certifySituationMembers(root,[root,child],id=>graph[id]));
graph.top.entries=[];graph.top.resource_name='rebound';assert.throws(()=>certifySituationMembers(root,[root,child],id=>graph[id]));
console.log('root-bound direct set graph passes; recommendations, clears, cycles and rebound resources refuse');
// Real native adapter shape: independent active Info versus stored group Header,
// named native enum values (deliberately non-ordinal constants).
class N{
    constructor(fields={},methods={}){this.fields=fields;this.methods=methods;this.handle={isNull:()=>false};this.class={methods:[]};}
    tryField(k){return Object.hasOwn(this.fields,k)?{value:this.fields[k]}:null;}
    tryMethod(k){return this.methods[k]?{invoke:(...a)=>this.methods[k](...a)}:null;}
    method(k){const m=this.tryMethod(k);if(!m)throw Error(k);return m;}
}
const pair=(key,value)=>new N({Key:key,Value:value});
const infos=[new N({Id:'set',Type:'ClothingSet',ResourceName:'set/resource',Revision:'r1'}),
    new N({Id:'top',Type:'Tops',ResourceName:'top/resource',Revision:'r2'})];
const edge=new N({Type:41,TransferableGroupId:'top'});
const stored=[new N({Header:new N({Id:'set',ResourceName:'set/resource',Custom:new N({Revision:'r1',UpdatedSinceLastRevision:false})}),TypeId:'ClothingSet',Entries:[edge]}),
    new N({Header:new N({Id:'top',ResourceName:'top/resource',Custom:new N({Revision:'r2',UpdatedSinceLastRevision:false})}),TypeId:'Tops',Entries:[new N({Type:72})]})];
const active=new N({TransferableGroups:stored.map((g,i)=>pair(i?'top':'set',g))},
    {GetActiveTransferableGroups:()=>infos.map((g,i)=>pair(i?'top':'set',g))});
const context=new N({}, {get_ActiveModel:()=>active,GetActiveLeafTransferableGroups:()=>[pair('top',infos[1])],
    GetActiveTransferableGroupInfo:id=>infos[id==='set'?0:1]});
global.Il2Cpp={string:x=>x};
const api=createGroupApi({model:()=>({token:'token',context}),cls:()=>({field:name=>({value:{TransferableGroup:41,Transferable:72,
    Clear:83,ClearByResourceName:94,RecommendedTransferableGroup:105}[name]})}),text:x=>x,presetEntries:()=>[]});
const certified=api.operations.list_groups({expected_model:'token',situation_root:root});
assert.equal(certified.membership_complete,true);assert.equal(certified.situation_membership.verified,true);
assert.equal(certified.situation_membership.members.length,2);
edge.fields.Type=105;
assert.equal(api.operations.list_groups({expected_model:'token',situation_root:root}).situation_membership.verified,false);
console.log('native set adapter distinguishes Info/Header and resolves actual named entry enums');
edge.fields.Type=41;
stored[1].fields.Header.fields.Custom.fields.Revision='old';
assert.equal(api.operations.list_groups({expected_model:'token',situation_root:root}).situation_membership.verified,false);
stored[1].fields.Header.fields.Custom.fields.Revision='r2';
stored[1].fields.Header.fields.Custom.fields.UpdatedSinceLastRevision=true;
assert.equal(api.operations.list_groups({expected_model:'token',situation_root:root}).situation_membership.verified,false);
stored[1].fields.Header.fields.Custom.fields.UpdatedSinceLastRevision=false;
context.methods.GetActiveLeafTransferableGroups=()=>[pair('top',new N({Id:'top',Type:'Tops',ResourceName:'top/resource',Revision:'alien'}))];
assert.equal(api.operations.list_groups({expected_model:'token',situation_root:root}).membership_complete,false);
context.methods.GetActiveLeafTransferableGroups=()=>[pair('top',infos[1])];
const catalogEntry=new N({id:'set',resourceName:'set/resource',transferableGroupType:'ClothingSet'});
const catalog=new N({}, {GetTransferableGroupByName:name=>catalogEntry});
context.methods.get_RestorationInfo=()=>new N({AssetStorage:new N({AssetCatalog:catalog})});
const candidate={id:'set',resource_name:'set/resource'};
assert.equal(api.operations.list_groups({expected_model:'token',situation_candidate:candidate}).situation_definition.revision_verified,true);
catalogEntry.fields.id='other';
assert.equal(api.operations.list_groups({expected_model:'token',situation_candidate:candidate}).situation_definition.verified,false);
catalogEntry.fields.id='set';active.fields.TransferableGroups=[];
const unloaded=api.operations.list_groups({expected_model:'token',situation_candidate:candidate}).situation_definition;
assert.equal(unloaded.verified,true);assert.equal(unloaded.revision_verified,false);assert.equal(unloaded.root.type,'ClothingSet');
console.log('stored revisions/dirty flags/incoherent views refuse; exact asset catalog prebinding also works without loaded revisions');
