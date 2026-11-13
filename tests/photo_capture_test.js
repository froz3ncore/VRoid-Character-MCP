const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
vm.runInThisContext(fs.readFileSync('agent/capture_quality.js','utf8'));
vm.runInThisContext(fs.readFileSync('agent/editor_capture.js','utf8'));
vm.runInThisContext(fs.readFileSync('agent/photo_capture.js','utf8'));
global.Il2Cpp={string:s=>s};
function fixture(fail){
 let touched=0,disposed=0,destroyed=0,owned=true,active='old',lateWrites=0,rendered=false;
 const original={enabled:true,target:{handle:'oldTarget'},mask:99,msaa:false,projection:Array.from({length:16},(_,i)=>i===0?1:i===5?16/9:0)};
 const live={...original,projection:[...original.projection]},source={handle:'source'},backup={handle:'backup'},photo={handle:'photo'};
 const obj=(data,isSource)=>({handle:isSource?'source':'backup',method:name=>({invoke(...args){
  if(isSource&&!owned&&(name.startsWith('set_')||name==='CopyFrom'))lateWrites++;
  if(name==='CopyFrom'){if(!isSource&&fail==='backup'){data.mask=123;data.target={handle:'partial'};throw Error('PARTIAL_BACKUP');}if(isSource){touched++;Object.assign(data,args[0].data);}else Object.assign(data,args[0].data);return;}
  if(name==='get_targetTexture')return data.target;
  if(name==='get_pixelWidth')return 1600;if(name==='get_pixelHeight')return 900;
  if(name==='get_aspect')return 1;
  if(name==='get_projectionMatrix')return {field:k=>({value:data.projection[Number(k[1])*4+Number(k[2])]})};
  if(name==='set_projectionMatrix'){touched++;data.projection=Array.from({length:16},(_,i)=>args[0].field('m'+Math.floor(i/4)+i%4).value);return;}
  if(name==='get_enabled')return data.enabled;
  if(name==='get_orthographic')return false;
  if(name==='get_cullingMask')return data.mask;
  if(name==='set_cullingMask'){if(isSource)touched++;data.mask=args[0];if(fail==='mask')throw Error('MASK_FAILED');return;}
  if(name==='set_enabled'){if(isSource)touched++;data.enabled=args[0];return;}
  if(name==='set_allowMSAA'){touched++;data.msaa=args[0];return;}
  if(name==='set_targetTexture'){if(isSource)touched++;data.target=args[0];return;}
  if(name==='Render'){rendered=true;if(fail==='owner')owned=false;if(fail==='render')throw Error('RENDER_FAILED');return;}
 }}),data});
 const cam=obj(live,true),backupCam=obj({},false);Object.assign(source,cam);Object.assign(backup,backupCam);
 original.target={handle:{isNull:()=>true}};live.target=original.target;
 const core=name=>({type:{object:name},alloc(){if(name==='Matrix4x4'){const m={};return {unbox:()=>({field:k=>({get value(){return m[k];},set value(v){m[k]=v;}})})};}
  return {method:n=>({invoke(){if(n==='AddComponent')return backup;}})};},method:n=>({invoke(v){if(n==='get_active')return active;if(n==='set_active')active=v;if(n==='DestroyImmediate')destroyed++;}})});
 photo.method=n=>({invoke(){if(n==='get_IsActive')return true;if(n==='get_PhotoBoothCamera')return source;}});
 const m={token:'token',engine:{handle:'engine'},root:{handle:'root',field:()=>({value:photo})}};
 const quality={begin(){if(fail==='allocate')throw Error('ALLOCATE_FAILED');return {target:{handle:'newTarget'},metadata:{output_width:640,output_height:1024},encode(){if(fail==='encode')throw Error('ENCODE_FAILED');return 'png';},dispose(){disposed++;}};}};
 const scope={culling_mask:7},cleanScope={inspect:()=>scope,apply(camera){camera.method('set_cullingMask').invoke(7);},verify(){if(!owned)throw Error('OWNER_CHANGED');if(rendered&&fail==='presentation')throw Error('CAPTURE_PRESENTATION_CHANGED');}};
 const render=createPhotoCapture({core,quality,invokeManaged:(o,n,a=[])=>o.method(n).invoke(...(n==='set_targetTexture'&&a[0]===original.target.handle?[original.target]:a)),model:()=>owned?m:{...m,root:{...m.root,handle:'replacement'}},cleanScope});
 return {run:()=>render(m,512,'balanced',{width:640,height:1024}),live,original,get touched(){return touched;},get disposed(){return disposed;},get destroyed(){return destroyed;},get lateWrites(){return lateWrites;}};
}
{
 const f=fixture('presentation');assert.throws(f.run,/CAPTURE_PRESENTATION_CHANGED/);assert.deepEqual(f.live,f.original);assert.equal(f.disposed,1);
}
{
 const f=fixture('allocate');assert.throws(f.run,/ALLOCATE_FAILED/);assert.equal(f.touched,0);assert.deepEqual(f.live,f.original);assert.equal(f.destroyed,1);
}
{
 const f=fixture('owner');assert.throws(f.run,/OWNER_CHANGED/);assert.equal(f.lateWrites,0);assert.equal(f.disposed,1);assert.equal(f.destroyed,1);
}
{
 const f=fixture('backup');assert.throws(f.run,/PARTIAL_BACKUP/);assert.equal(f.touched,0);assert.deepEqual(f.live,f.original);assert.equal(f.destroyed,1);
}
for(const fail of ['mask','render','encode']){const f=fixture(fail);assert.throws(f.run,/FAILED/);assert.deepEqual(f.live,f.original);assert.equal(f.disposed,1);}
{
 const f=fixture();const r=f.run();assert.deepEqual(f.live,f.original);assert.equal(r.framing.source_optical_aspect,1);assert.equal(r.framing.source_pixel_width,1600);assert.equal(r.framing.source_pixel_height,900);
 assert(Math.abs(r.framing.projection_matrix[0]*640-r.framing.projection_matrix[5]*1024)<1e-10);
}
console.log('photo snapshot readiness, rollback, raster/optical disagreement and failure cleanup passed');
