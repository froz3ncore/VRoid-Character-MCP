// Native accessor identity adapted from brainrom/vroid-studio-mcp Colors.cs.
// MIT attribution: vroid_mcp/data/color_state/NOTICE.
function createColorState({text,seq,readBinding}) {
    const identity=b=>JSON.stringify([b.group,b.key]);
    function keys(accessor,name){
        if(!accessor||accessor.handle.isNull()||!accessor.tryField(name))return null;
        return seq(accessor.field(name).value).map(k=>({group:text(k.method('get_TransferableGroupType').invoke()),key:text(k.method('get_Key').invoke())}));
    }
    function inspect(sm){
        const empty={status:'unavailable',bindings:[],modified:[],reason:null};
        try{
            if(!sm||!sm.tryMethod('get_Accessor'))return empty;
            const a=sm.method('get_Accessor').invoke(),bs=keys(a,'_keysToSet'),modified=keys(a,'_keysToModify');
            if(!bs||!bs.length)return {...empty,reason:'Native accessor exposes no writable key set'};
            const complete=bs.every(b=>typeof b.group==='string'&&b.group.length&&typeof b.key==='string'&&b.key.length);
            const bindings=[...new Map(bs.filter(b=>b.group&&b.key).map(b=>[identity(b),b])).values()].sort((a,b)=>identity(a).localeCompare(identity(b)));
            return {status:complete?'complete':'partial',bindings,modified:modified||[],reason:complete?null:'Incomplete native binding keys'};
        }catch(e){return {...empty,reason:String(e)};}
    }
    function decorate(entries){
        const colors=entries.filter(e=>e.data.type==='color'),values=new Map();
        for(const e of colors){
            const info=e.colorInfo||{status:'unavailable',bindings:[],modified:[],reason:'No native editable-element accessor'},d=e.data;
            const bindings=info.bindings.map(b=>{
                const k=identity(b);
                if(!values.has(k)){
                    try{
                        const value=readBinding(b);
                        if(!Array.isArray(value)||value.length!==4||!value.every(Number.isFinite))throw Error('Invalid native RGBA binding value');
                        values.set(k,{value,value_status:'read',error:null});
                    }catch(error){values.set(k,{value:null,value_status:'unavailable',error:String(error)});}
                }
                return {...b,...values.get(k)};
            });
            const groups=[...new Set(bindings.map(b=>b.group))].sort();
            const complete=info.status==='complete',known=complete&&bindings.length>0&&bindings.every(b=>b.value_status==='read');
            const mixed=known?bindings.some(b=>b.value.some((v,i)=>v!==bindings[0].value[i])):null;
            Object.assign(d,{native_value:d.value,color_binding_status:info.status,color_binding_error:info.reason,
                color_bindings:bindings,color_signature:complete?JSON.stringify(bindings.map(b=>[b.group,b.key])):null,
                modified_bindings:info.modified,is_shared:complete?groups.length>1:null,shared_groups:groups,
                is_aggregate:complete?bindings.length>1:null,mixed,
                value_status:known?(mixed?'mixed':'uniform'):'native_representative',
                alias_of:null,alias_ids:[],affected_parameter_ids:[]});
            if(known)d.value=mixed?null:bindings[0].value;
            else if(complete&&bindings.length>1){d.value=null;d.value_status='unavailable';}
            e.colorWriteKeys=complete?bindings.map(identity):null;
        }
        for(const e of colors){
            const d=e.data;if(!d.color_signature)continue;
            const aliases=colors.filter(o=>o.data.color_signature===d.color_signature).sort((a,b)=>Number(b.data.editable)-Number(a.data.editable)||a.data.id.localeCompare(b.data.id));
            d.alias_of=aliases[0]===e?null:aliases[0].data.id;
            d.alias_ids=aliases.filter(o=>o!==e).map(o=>o.data.id);
            const own=new Set(e.colorWriteKeys);
            d.affected_parameter_ids=colors.filter(o=>o.colorWriteKeys&&o.colorWriteKeys.some(k=>own.has(k))).map(o=>o.data.id).sort();
        }
        return entries;
    }
    function validateBatch(changes){
        const seen=new Map();
        for(const {e} of changes)for(const k of e.colorWriteKeys||[]){
            if(seen.has(k))throw Error('OVERLAPPING_COLOR_TARGETS: '+seen.get(k)+' / '+e.data.id+'; write one alias, or separate left/right controls');
            seen.set(k,e.data.id);
        }
    }
    return {inspect,decorate,validateBatch};
}
