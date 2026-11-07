const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
vm.runInThisContext(fs.readFileSync(path.join(__dirname,'../agent/hair_groups.js'),'utf8'));
let configured={length:.2,hair_count:8},writes=[];
const state=()=>({scope:'t/g',category:'HairFront',type:'procedural',strands:[],configured:{...configured}});
const adapter={begin:()=>({token:'fresh',frame:10}),end(){},identity(){},snapshot:state,
    procedural:()=>({configured:{...configured},controls:[
        {key:'length',type:'float',min:.01,max:2,value:configured.length,write:(v,onInvoke)=>{onInvoke();writes.push(['length',v]);configured.length=Math.fround(v);}},
        {key:'hair_count',type:'int',min:1,max:100,value:configured.hair_count,write:(v,onInvoke)=>{onInvoke();writes.push(['hair_count',v]);configured.hair_count=v;}}]})};
const api=createHairGroupApi({adapter}),args={expected_model:'fresh',category:'HairFront',scope:'t/g'};
assert.equal(typeof api.operations.set_procedural_hair,'function','procedural hair API missing');
for(const changes of [{},{length:true},{length:NaN},{hair_count:1.5},{hair_count:true},{hair_count:0},{length:.5,hair_count:101}]){
    const rejected=api.operations.set_procedural_hair({...args,...changes});assert.equal(rejected.ok,false);
    assert.equal(rejected.dispatch_state,'prewrite_rejected');assert.equal(rejected.uncertain,false);assert.equal(writes.length,0);
}
const r=api.operations.set_procedural_hair({...args,length:.5});
assert.equal(r.ok,true);assert.equal(r.setter_count,1);assert.equal(r.command_count,null);
assert.equal(r.history_entry_count,null);assert.deepEqual(writes,[['length',.5]]);
assert.deepEqual(r.requested_configured,{length:.5,hair_count:8});assert.equal(r.verification_pending,true);
assert.equal(r.procedural_length_units,'native_procedural_parameter');
assert.equal(r.controls.find(c=>c.key==='hair_count').max,100);
const noop=api.operations.set_procedural_hair({...args,length:.5});assert.equal(noop.setter_count,0);
console.log('Procedural typed/range preflight, native writer routing, scalar readback and geometry separation passed');
{
    let calls=0;
    const nativeAdapter={...adapter,procedural:()=>({configured:{length:.2,hair_count:8},controls:[
        {key:'length',type:'float',min:Math.fround(.1),max:1,native_route:'command',
            write(v,onInvoke){onInvoke();calls++;}}]})};
    const nativeApi=createHairGroupApi({adapter:nativeAdapter});
    const accepted=nativeApi.operations.set_procedural_hair({...args,length:.1});
    assert.equal(accepted.ok,true);assert.equal(accepted.requested_configured.length,Math.fround(.1));
    assert.equal(accepted.command_count,1);assert.equal(accepted.setter_count,0);assert.equal(calls,1);
    assert.equal(accepted.verification_pending,true,'delayed publication is checked after host settling');
    const rejected=nativeApi.operations.set_procedural_hair({...args,length:.099});
    assert.equal(rejected.dispatch_state,'prewrite_rejected');assert.equal(rejected.uncertain,false);assert.equal(calls,1);
}
