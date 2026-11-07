// Use production owner aggregation with substitute managed tasks and cleanup.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('agent/operations.js','utf8');
const cx=vm.createContext({});
vm.runInContext(source.slice(0,source.indexOf('globalThis.vroid =')),cx);
const events=[];
let completed=false,exporting=true,selecting=true;
const tasks=new Map([['import',{task:{method:()=>({invoke:()=>completed})},handle:{free:()=>events.push('import')}}]]);
const vrm={pendingWork:()=>exporting?[{kind:'vrm_export'}]:[],releaseWork:()=>events.push('vrm')};
const groups={pendingWork:()=>selecting?[{kind:'custom'}]:[],releaseWork:()=>events.push('custom')};
const work=cx.createPendingNativeWork(tasks,vrm,groups);
for(const remaining of [3,2,1]){
    const observed=work.observe();assert.equal(observed.safe,false);assert.equal(observed.pending_work.length,remaining);
    assert.equal(work.release().safe,false);assert.deepEqual(events,[]);
    if(remaining===3)completed=true;else if(remaining===2)exporting=false;else selecting=false;
}
assert.equal(work.observe().safe,true);assert.deepEqual(events,[]);
assert.equal(work.release().safe,true);assert.deepEqual(events.sort(),['custom','import','vrm']);
assert.equal(tasks.size,0);
