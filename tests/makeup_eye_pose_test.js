const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const context={};vm.runInNewContext(fs.readFileSync('agent/textures.js','utf8'),context);const pose=context.createMakeupEyePose;
function fixture(shapes){const weights=new Map(shapes.map(s=>[s.index,s.weight||0]));return {shapes,weights,getWeight:i=>weights.get(i),setWeight:(i,v)=>weights.set(i,v)};}
const shapes=[{index:6,name:'Fcl_EYE_Close',last_frame_weight:100,weight:7},{index:7,name:'Fcl_EYE_Close_L',last_frame_weight:100,weight:12},{index:8,name:'Fcl_EYE_Close_R',last_frame_weight:100,weight:3}];
let api=fixture(shapes),p=pose(api,1);assert.equal(api.getWeight(6),100);assert.equal(api.getWeight(7),0);assert.equal(api.getWeight(8),0);p.restore();assert.equal(api.getWeight(6),7);assert.equal(api.getWeight(7),12);assert.equal(api.getWeight(8),3);assert(p.metadata.restored);
api=fixture(shapes.slice(1));p=pose(api,.5);assert.equal(api.getWeight(7),50);assert.equal(api.getWeight(8),50);p.restore();
for(const bad of [-1,2,NaN,Infinity,true]){api=fixture(shapes);assert.throws(()=>pose(api,bad));assert.equal(api.getWeight(6),7);}
for(const unsupported of [[],shapes.slice(1,2),[...shapes,shapes[0]],shapes.map(s=>({...s,last_frame_weight:0}))]){api=fixture(unsupported);assert.throws(()=>pose(api,1));}
api=fixture(shapes);const set=api.setWeight;let fail=true;api.setWeight=(i,v)=>{if(fail&&i===7){fail=false;throw Error('native write failed');}set(i,v);};assert.throws(()=>pose(api,1));assert.equal(api.getWeight(6),7);assert.equal(api.getWeight(7),12);assert.equal(api.getWeight(8),3);
api=fixture(shapes);assert.equal(pose(api,null),null);assert.equal(api.getWeight(6),7);
console.log('Temporary makeup eye pose selection, units, ambiguity, failure recovery and restoration passed');
