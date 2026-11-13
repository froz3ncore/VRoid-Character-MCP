// Exercise the actual queued entry point. Attachment bootstrap runs on a free
// thread, so verify Application.version on the Unity thread before job.work.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('agent/main_thread.js','utf8');
function queued(expected, observed, digest) {
    const calls=[];
    const getter=observed===undefined?null:{invoke(){calls.push('version');return {content:observed};}};
    const context=vm.createContext({VROID_PRODUCT_VERSION:expected,VROID_ASSEMBLY_SHA256:digest,ATTACHED:true,Map,
        clearTimeout(){},rpc:{},Il2Cpp:{perform:()=>Promise.resolve(),currentThread:{id:5},
            domain:{assembly:()=>({image:{class:()=>({tryMethod:()=>getter})}})}}});
    vm.runInContext(source,context);
    const bridge=vm.runInContext('bridge',context);
    bridge.mainThread=5;
    let error;
    bridge.backlog.push({expiresAt:Date.now()+60000,work(){calls.push('dispatch');},
        resolve(){},reject(e){error=e.message;}});
    context.drainJob();
    return {calls,error,version:bridge.productVersion,source:bridge.productVersionSource};
}
for(const version of ['2.14.0','2.16.0']) {
    const ok=queued(version,version);
    assert.deepEqual(ok.calls,['version','dispatch']);
    assert.equal(ok.version,version);
    assert.equal(ok.source,'UnityEngine.Application.version');
}
const mismatch=queued('2.16.0','2.14.0');
assert.deepEqual(mismatch.calls,['version']);
assert.match(mismatch.error,/VERSION_MISMATCH/);
const fallback=queued('2.14.0',undefined,'793eb5fcff3093f344ee930fbfa0c0796ed7780ac91c45bdb7ce6bd34d62fd3c');
assert.deepEqual(fallback.calls,['dispatch']);
assert.equal(fallback.version,'2.14.0');assert.equal(fallback.source,'recognized package');
const unknown=queued(null,undefined);
assert.deepEqual(unknown.calls,[]);assert.match(unknown.error,/UNVERIFIED/);
assert.deepEqual(queued('2.16.0',undefined).calls,[]);
console.log('Runtime version checked on Unity thread before queued dispatch');

// Copy bootstrap runs before the first Unity frame. Application.version is
// unsafe then; both copy and attached jobs must still verify before dispatch.
{
    let bootstrap;
    const calls=[];
    const context=vm.createContext({VROID_PRODUCT_VERSION:'2.16.0',VROID_ASSEMBLY_SHA256:'signed',ATTACHED:false,Map,
        clearTimeout(){},rpc:{},send(){},Process:{id:1,getCurrentThreadId:()=>5},
        Interceptor:{attach:()=>({})},nativeBuildProfile:()=>({session:false}),
        installNativePngDecoder:()=>({}),
        Il2Cpp:{unityVersion:'6000.0.62f1',perform:fn=>{bootstrap=fn;return Promise.resolve();},currentThread:{id:5}}});
    vm.runInContext(source,context);
    context.createHandleKeeper=()=>()=>({free(){}});
    context.retainEditorSingletons=()=>{};
    context.holdRunInBackground=()=>{};
    context.countModelUpdates=()=>{};
    context.nativeClass=()=>({method:()=>({virtualAddress:1}),tryMethod:()=>({invoke(){
        calls.push('early-version');throw Error('ENGINE_APPLICATION_NOT_INITIALIZED');}})});
    assert.doesNotThrow(()=>bootstrap());
    assert.deepEqual(calls,[]);
    const bridge=vm.runInContext('bridge',context);
    assert.equal(bridge.ready,true);
    context.nativeClass=()=>({tryMethod:()=>({invoke(){calls.push('version');return {content:'2.16.0'};}})});
    bridge.backlog.push({expiresAt:Date.now()+60000,work(){calls.push('dispatch');},resolve(){},reject(e){throw e;}});
    context.drainJob();
    assert.deepEqual(calls,['version','dispatch']);
}
console.log('Copy bootstrap defers product getter until the first dispatched frame');
