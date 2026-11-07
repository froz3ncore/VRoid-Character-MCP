const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
vm.runInThisContext(fs.readFileSync(path.join(__dirname,'../agent/hair_groups.js'),'utf8'));
let configured={length:.2,hair_count:8},writes=[];
const state=()=>({scope:'t/g',category:'HairFront',type:'procedural',strands:[],configured:{...configured}});
const adapter={begin:()=>({token:'fresh',frame:10}),end(){},identity(){},snapshot:state,
    procedural:()=>({configured:{...configured},controls:[
        {key:'length',type:'float',min:.01,max:2,value:configured.length,write:v=>{writes.push(['length',v]);configured.length=Math.fround(v);}},
        {key:'hair_count',type:'int',min:1,max:100,value:configured.hair_count,write:v=>{writes.push(['hair_count',v]);configured.hair_count=v;}}]})};
const api=createHairGroupApi({adapter}),args={expected_model:'fresh',category:'HairFront',scope:'t/g'};
assert.equal(typeof api.operations.set_procedural_hair,'function','procedural hair API missing');
for(const changes of [{},{length:true},{length:NaN},{hair_count:1.5},{hair_count:true},{hair_count:0},{length:.5,hair_count:101}]){
    assert.throws(()=>api.operations.set_procedural_hair({...args,...changes}));assert.equal(writes.length,0);
}
const r=api.operations.set_procedural_hair({...args,length:.5,hair_count:16});
assert.equal(r.ok,true);assert.equal(r.setter_count,2);assert.equal(r.command_count,null);
assert.equal(r.history_entry_count,null);assert.deepEqual(writes,[['length',.5],['hair_count',16]]);
assert.deepEqual(r.configured,{length:.5,hair_count:16});assert.equal(r.readback.control_point_polyline_length,0);
assert.equal(r.procedural_length_units,'native_procedural_parameter');
assert.equal(r.controls.find(c=>c.key==='hair_count').max,100);
const noop=api.operations.set_procedural_hair({...args,length:.5});assert.equal(noop.setter_count,0);
console.log('Procedural typed/range preflight, native writer routing, scalar readback and geometry separation passed');
