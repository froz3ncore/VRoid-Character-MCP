const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
vm.runInThisContext(fs.readFileSync('agent/attachment_lease.js','utf8'));
function fixture(initial=false) {
    const state={raw:null,background:initial,owner:'dead',closed:[],writes:[]};
    const api={target:10,owner:20,read:()=>state.raw,
        write:value=>{state.raw=value;state.writes.push(value);},
        getBackground:()=>state.background,setBackground:value=>{state.background=value;},
        openOwner:()=> '0x123',ownerState:()=>state.owner,
        closeOwner:handle=>state.closed.push(handle)};
    return {state,api,lease:createAttachmentLease(api)};
}
for(const initial of [false,true]) {
    const {state,lease}=fixture(initial);
    assert.equal(lease.acquire().original_background,initial);
    assert.equal(state.background,true);
    lease.release();lease.release();
    assert.equal(state.background,initial);assert.equal(state.raw,null);
    assert.deepEqual(state.closed,['0x123']);
}
{
    const {state,api,lease}=fixture();lease.acquire();
    // Simulate a destroyed host: its process handle remains signaled in the target.
    const next=createAttachmentLease({...api,owner:21,openOwner:()=> '0x456'});
    assert.equal(next.acquire().recovered_previous_host,true);
    assert.equal(state.background,true);
    assert.equal(JSON.parse(state.raw).background,false);
    next.release();assert.equal(state.background,false);
    assert.deepEqual(state.closed,['0x123','0x456']);
}
for(const owner of ['alive','invalid']) {
    const {state,api,lease}=fixture();lease.acquire();state.owner=owner;
    const raw=state.raw;
    assert.throws(()=>createAttachmentLease(api).acquire(),/ATTACHMENT_(ALREADY_OWNED|LEASE_OWNER_UNVERIFIED)/);
    assert.equal(state.raw,raw);assert.deepEqual(state.closed,[]);
}
{
    const {state,api}=fixture();state.raw=JSON.stringify({version:1,target:99});
    assert.throws(()=>createAttachmentLease(api).acquire(),/LEASE_INVALID/);
    assert.equal(state.background,false);assert.deepEqual(state.closed,[]);
}
{
    const {state,api}=fixture();api.write=()=>{throw Error('write failed');};
    assert.throws(()=>createAttachmentLease(api).acquire(),/write failed/);
    assert.equal(state.background,false);assert.deepEqual(state.closed,['0x123']);
}
{
    const {state,api}=fixture();let failed=true;
    api.setBackground=value=>{if(failed)throw Error('setter failed');state.background=value;};
    const lease=createAttachmentLease(api);
    assert.throws(()=>lease.acquire(),/setter failed/);
    assert(state.raw);failed=false;lease.release();
    assert.equal(state.raw,null);assert.equal(state.background,false);
}
{
    const {state,lease}=fixture();lease.acquire();
    const other=JSON.parse(state.raw);other.owner=99;state.raw=JSON.stringify(other);
    assert.throws(()=>lease.release(),/LEASE_CHANGED/);
    assert.equal(state.background,true);assert.deepEqual(state.closed,[]);
}
console.log('Attachment lease: normal release, crash recovery, ownership and failure boundaries passed');
