const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
vm.runInThisContext(fs.readFileSync('agent/capture_quality.js','utf8'));
vm.runInThisContext(fs.readFileSync('agent/app_frame.js','utf8'));
global.NULL={null:true};
global.Il2Cpp={corlib:{class:()=>({method:()=>({overload:()=>({invoke:()=>({content:'png'})})})})}};
function native(fail=''){
 let hooks=[],reads=0,destroyed=0,wired=0,active={old:true},frame=1,owner='model',dims=[1234,734];const previous=active;
 global.Process={getCurrentThreadId:()=>7};
 global.Interceptor={attach(address,callbacks){assert.equal(address,'end-frame');const h={callbacks,detach(){hooks=hooks.filter(x=>x!==h);}};hooks.push(h);return h;}};
 function core(name){
   return {
     alloc(){return {
       unbox(){return this;},
       method(n){return {invoke(...args){
         if(n==='ReadPixels'){reads++;assert.equal(active,NULL);if(fail==='read')throw Error('READ_FAILED');}
       }};},
     };},
     method(n){return {
       virtualAddress:n==='OnEndOfFrame'?{isNull:()=>false,toString:()=> 'end-frame'}:null,
       invoke(...a){
         if(n==='EnsureDelayedCallWiredUp'){wired++;return;}
         if(n==='get_width')return dims[0];if(n==='get_height')return dims[1];
         if(n==='get_active')return active;if(n==='set_active'){active=a[0];return;}
         if(n==='DestroyImmediate'){destroyed++;return;}
         if(n==='get_antiAliasing')return 2;
         if(n==='get_frameCount')return frame;
       },
     };},
   };
 }
 // Treat the exact method-address object as an opaque native address.
 global.Interceptor.attach=(address,callbacks)=>{assert.equal(address.toString(),'end-frame');const h={callbacks,detach(){hooks=hooks.filter(x=>x!==h);}};hooks.push(h);return h;};
 const preview={verify:()=>({identity:owner}),open:()=>({identity:owner}),adapter:{identity:c=>c.identity,cameraState:()=>({camera_id:'owned'})}};
 const cls=()=>({method:()=>({invoke(){if(fail==='encode')throw Error('ENCODE_FAILED');return {};}})});
 const api=createNativeAppFrame({core,cls,preview,mainThread:()=>7,frame:()=>frame});
 return {api,get reads(){return reads;},get hooks(){return hooks;},get destroyed(){return destroyed;},get active(){return active;},previous,
  tick(){frame++;for(const h of [...hooks])h.callbacks.onLeave();},setOwner:v=>owner=v,setDimensions:v=>dims=v,get wired(){return wired;}};
}
for(const fail of ['', 'read', 'encode']){
 const n=native(fail),job=n.api.start('token');assert.equal(n.reads,0);assert.equal(n.wired,1);n.tick();
 const response=n.api.poll(job);assert.equal(response.completed,true);assert.equal(n.hooks.length,0);assert.equal(n.destroyed,1);assert.equal(n.active,n.previous);
 if(fail)assert.match(response.error,/FAILED/);else{assert.equal(response.result.width,1234);assert.equal(response.result.height,734);assert.equal(response.result.frame,2);assert.equal(response.result.requested_unity_frame,1);assert.equal(response.result.quality.msaa_samples,2);}
}
{
 const n=native(),job=n.api.start('token');n.setOwner('changed');n.tick();assert.match(n.api.poll(job).error,/IDENTITY/);assert.equal(n.reads,0);
}
{
 const n=native(),job=n.api.start('token');n.setDimensions([4000,3000]);n.tick();assert.match(n.api.poll(job).error,/BUDGET/);assert.equal(n.reads,0);assert.equal(n.destroyed,0);
}
console.log('actual end-frame binding, screen dimensions/quality, backbuffer and error cleanup passed');
