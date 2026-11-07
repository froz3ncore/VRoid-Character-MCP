const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
vm.runInThisContext(fs.readFileSync('agent/app_frame.js','utf8'));
let callback=null,reads=0,removed=0,identity='a',now=0;
const api=createAppFrameCapture({now:()=>now,subscribe:cb=>{callback=cb;return ()=>{removed++;callback=null;};},
    identity:()=>identity,read:()=>{reads++;return {width:1280,height:720,base64:'png'};},ttl:100});
const job=api.start('token');assert.equal(reads,0);assert.equal(api.poll(job).completed,false);
callback();assert.equal(reads,1);assert.equal(removed,1);assert.equal(api.poll(job).result.provenance,'unity_application_frame');
assert.throws(()=>api.poll(job),/UNKNOWN/);
const stale=api.start('token');identity='b';callback();assert.match(api.poll(stale).error,/IDENTITY/);assert.equal(reads,1);
const expired=api.start('token');now=200;api.expire();assert.equal(callback,null);assert.match(api.poll(expired).error,/TIMEOUT/);
const pending=api.start('token');api.dispose();assert.equal(callback,null);assert.throws(()=>api.poll(pending),/UNKNOWN/);
const abandoned=api.start('token');callback();now+=101;api.expire();assert.throws(()=>api.poll(abandoned),/UNKNOWN/);
console.log('one-shot end-frame timing, stale identity, timeout, teardown passed');
