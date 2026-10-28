const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
vm.runInThisContext(fs.readFileSync('agent/native_png_decoder.js','utf8'));
function fixture() {
    const state={frame:0,decoded:[],delivered:[],requestHolds:0,valueHolds:0};
    const api={frame:()=>state.frame,
        holdRequest:r=>{state.requestHolds++;return ()=>state.requestHolds--;},
        holdValue:v=>{state.valueHolds++;return ()=>state.valueHolds--;},
        decode:r=>{state.decoded.push(r);return {failed:!!r.bad,value:r.bad?'native exception':'native texture'};},
        deliver:(r,result)=>state.delivered.push({r,result})};
    return {state,api,queue:createNativePngQueue(api)};
}
{
    const {state,queue}=fixture(),request={bytes:'PNG',mip:true,linear:false,unreadable:true};
    queue.request(request);queue.pump();assert.equal(state.decoded.length,0);
    assert.equal(state.requestHolds,1);state.frame++;queue.pump();
    assert.equal(state.decoded[0],request);assert.equal(state.delivered.length,1);
    assert.equal(state.requestHolds,0);assert.equal(state.valueHolds,0);assert.equal(queue.status().pending,0);
}
{
    const {state,api,queue}=fixture();
    api.deliver=(r,result)=>{state.delivered.push(result);if(!r.child)queue.request({child:true});queue.pump();};
    queue.request({});state.frame++;queue.pump();
    assert.equal(state.delivered.length,1);assert.equal(queue.status().pending,1);
    state.frame++;queue.pump();assert.equal(state.delivered.length,2);
}
{
    const {state,queue}=fixture();for(let i=0;i<9;i++)queue.request({i});
    state.frame++;queue.pump();assert.equal(state.delivered.length,4);assert.equal(queue.status().pending,5);
    state.frame++;queue.pump();state.frame++;queue.pump();assert.equal(state.delivered.length,9);
    assert.equal(state.requestHolds,0);
}
{
    const {state,queue}=fixture();queue.request({bad:true});state.frame++;queue.pump();
    assert.equal(state.delivered[0].result.value,'native exception');
    assert.equal(queue.status().failed,1);assert.equal(queue.status().fatal,null);
}
{
    const {state,api,queue}=fixture();api.deliver=()=>{throw Error('native callback failed');};
    queue.request({});queue.request({});state.frame++;queue.pump();queue.pump();
    assert.match(queue.status().fatal,/native callback failed/);
    assert.equal(state.decoded.length,1);assert.equal(queue.status().pending,1);
    assert.equal(state.valueHolds,0);assert.equal(state.requestHolds,1);
}
console.log('Native PNG decode: deferred delivery, rooted lifetimes, flags, budgets, reentrancy and error forwarding passed');
