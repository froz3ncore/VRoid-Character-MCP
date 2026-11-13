const assert=require('assert'),fs=require('fs'),vm=require('vm');
const ctx=vm.createContext({console});
for(const file of ['agent/catalog.js','agent/groups.js'])vm.runInContext(fs.readFileSync(file,'utf8'),ctx);
const obj=(fields={},methods={})=>({tryField:k=>k in fields?{value:fields[k]}:null,
    tryMethod:k=>k in methods?{invoke:methods[k]}:null,method(k){return this.tryMethod(k);}});
const option=(area,id,resource)=>({id:area+'/Tops/'+id,transferable_id:id,category:'Tops',owned:true,
    label:'Option',resource_name:resource,p:obj({}, {get_TransferableGroupId:()=>id})});
function scan(options,entries){
    const catalog=entries.map(([id,resource])=>obj({Key:id,Value:obj({transferableGroupId:id,resourceName:resource,
        priceInCoin:0,isOwned:true,isSetItem:false})}));
    const m={token:'M',main:obj({_mainModel:obj({playFabUser:obj({}, {GetTransferableGroupIdToPresetModel:()=>catalog})})})};
    const groups=ctx.createGroupApi({text:x=>x});
    const snapshot=ctx.createPresetCatalogSnapshot({presetEntries:(m,area)=>options.filter(o=>o.id.startsWith(area+'/')),
        catalogRows:groups.helpers.catalogRows,customSnapshot:()=>({rows:[],complete:true,errors:[]}),build:'a'.repeat(64)});
    return snapshot(m,true);
}
const resource='Clothing/Tops/N00/R';
assert.throws(()=>scan([option('clothing','foreign',resource)],[['canon',resource]]),/CONFLICT/);
assert.throws(()=>scan([option('clothing','canon','Clothing/Tops/N00/other')],[['canon',resource]]),/CONFLICT/);
const result=scan([option('clothing','canon',resource),option('body','canon',resource),
                   option('hair','option-only','Hair/AllHair/N00/option')],
                  [['canon',resource],['catalog-only','Hair/AllHair/N00/catalog']]);
assert.equal(result.builtin_complete,true);assert.equal(result.rows.length,3);
const matched=result.rows.find(r=>r.id==='canon');
assert.equal(matched.selectable_preset_ids.length,2);assert.equal(matched.selectable,true);
assert.equal(result.rows.find(r=>r.id==='catalog-only').catalog_only,true);
assert.equal(result.rows.find(r=>r.resource==='Hair/AllHair/N00/option').id,'option-only');
console.log('actual catalog adapters reject identity contradictions and retain matched multi-area/independent rows');

// The actual retained native-preview route returns the same native identity.
ctx.retain=()=>({free(){}});
vm.runInContext(fs.readFileSync('agent/preset_previews.js','utf8'),ctx);
const task=obj({}, {get_IsCompleted:()=>true,get_IsCanceled:()=>true});
const nativeOption=option('clothing','canon',resource);
nativeOption.p=obj({}, {PrepareResources:()=>{},get_Preview:()=>obj({}, {Create:()=>task})});
const preview=ctx.createPresetPreviewApi({model:()=>({token:'M'}),presetEntries:()=>[nativeOption],text:x=>x});
const receipt=preview.operations.preset_preview_begin({expected_model:'M',area:'clothing',preset_id:nativeOption.id});
assert.equal(receipt.transferable_id,'canon');assert.equal(receipt.resource_name,resource);
