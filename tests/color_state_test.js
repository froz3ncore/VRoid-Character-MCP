const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
vm.runInThisContext(fs.readFileSync('agent/color_state.js','utf8'));
const left={group:'Iris',key:'NativeRightKey'},right={group:'Iris',key:'NativeLeftKey'};
const id=b=>JSON.stringify([b.group,b.key]);
const blue=[.1,.3,.9,1],gold=[.95,.5,.05,1];
function entry(name,bindings,value=blue){return {data:{id:name,label:'任意本地化名称',type:'color',value,editable:true},colorInfo:{status:'complete',bindings,modified:bindings,reason:null}};}
function setup(mixed=true){
    const state=new Map([[id(left),gold],[id(right),mixed?blue:gold]]),reads=new Map();
    const api=createColorState({text:v=>v,seq:v=>v,readBinding(b){const k=id(b);reads.set(k,(reads.get(k)||0)+1);if(!state.has(k))throw Error('No readback');return state.get(k);}});
    const rows=[entry('both',[left,right],gold),entry('left',[left],gold),entry('right',[right],blue)];
    api.decorate(rows);return {api,rows,state,reads};
}
{
    const {rows,reads}=setup();assert.equal(rows[0].data.mixed,true);assert.equal(rows[0].data.value,null);
    assert.deepEqual(rows[0].data.native_value,gold);assert.deepEqual(rows[1].data.value,gold);
    assert.deepEqual(rows[1].data.affected_parameter_ids,['both','left']);assert.deepEqual(rows[2].data.affected_parameter_ids,['both','right']);
    assert.equal(reads.size,2);assert([...reads.values()].every(n=>n===1));
}
{
    const {rows}=setup(false);assert.equal(rows[0].data.mixed,false);assert.deepEqual(rows[0].data.value,gold);
}
{
    const {api,rows}=setup();api.validateBatch([{e:rows[1]},{e:rows[2]}]);
    assert.throws(()=>api.validateBatch([{e:rows[0]},{e:rows[1]}]),/OVERLAPPING_COLOR_TARGETS/);
}
{
    const skin=[{group:'FaceSkin',key:'Base'},{group:'BodySkin',key:'Base'}];
    const rows=[entry('face',skin),entry('body',[...skin].reverse())];
    const api=createColorState({text:v=>v,seq:v=>v,readBinding:()=>gold});api.decorate(rows);
    // inspect() sorts native keys; sort here because these rows bypass native extraction.
    assert(rows.every(e=>e.data.is_shared));
    const sorted=skin.sort((a,b)=>id(a).localeCompare(id(b)));
    const same=[entry('face',sorted),entry('body',sorted)];api.decorate(same);
    assert.equal(same[0].data.alias_of,'body');assert.equal(same[1].data.alias_of,null);
    assert.deepEqual(same[0].data.alias_ids,['body']);
    assert.throws(()=>api.validateBatch(same.map(e=>({e}))),/OVERLAPPING_COLOR_TARGETS/);
}
{
    const api=createColorState({text:v=>v,seq:v=>v,readBinding:b=>b.group==='FaceSkin'?gold:blue});
    const rows=[entry('skin',[{group:'FaceSkin',key:'Base'},{group:'BodySkin',key:'Base'}])];api.decorate(rows);
    assert(rows[0].data.is_shared&&rows[0].data.mixed);assert.equal(rows[0].data.value,null);
}
{
    const api=createColorState({text:v=>v,seq:v=>v,readBinding(){throw Error('Read unavailable');}});
    const rows=[entry('both',[left,right])];api.decorate(rows);
    assert.equal(rows[0].data.mixed,null);assert.equal(rows[0].data.value,null);assert.equal(rows[0].data.value_status,'unavailable');
    assert.equal(rows[0].data.color_bindings[0].value_status,'unavailable');
}
{
    const api=createColorState({text:v=>v,seq:v=>v,readBinding(){throw Error('Should not read');}});
    const rows=[{data:{id:'hair/all',type:'color',value:gold,editable:true}}];api.decorate(rows);
    assert.equal(rows[0].data.color_binding_status,'unavailable');assert.equal(rows[0].data.mixed,null);
    assert.deepEqual(rows[0].data.value,gold);assert.equal(rows[0].data.is_shared,null);
}
{
    const {api}=setup();const rows=[entry('a',[{group:'A',key:'same'}]),entry('b',[{group:'B',key:'same'}])];
    api.decorate(rows);api.validateBatch(rows.map(e=>({e})));assert.equal(rows[0].data.alias_of,null);
}
{
    const api=createColorState({text:v=>v,seq:v=>v,readBinding:b=>b.key==='NativeRightKey'?blue:[.1,.3,.9000001,1]});
    const rows=[entry('both',[left,right])];api.decorate(rows);assert.equal(rows[0].data.mixed,true);
}
console.log('Color state regression passed (9 scenarios)');
