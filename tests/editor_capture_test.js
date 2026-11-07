const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
vm.runInThisContext(fs.readFileSync('agent/capture_quality.js','utf8'));
vm.runInThisContext(fs.readFileSync('agent/editor_capture.js','utf8'));
global.Il2Cpp={string:s=>s};
const value=a=>({field:k=>({value:a[k]} )});
function native(fail=''){
 const live=new Set(),events=[];let sequence=0;
 const projection=Object.fromEntries(Array.from({length:16},(_,i)=>['m'+Math.floor(i/4)+i%4,[1,0,.1,0,0,1.75,.2,0,0,0,-1,-1,0,0,-1,0][i]]));
 const source={position:{x:2,y:3,z:4},rotation:{x:0,y:.7,z:0,w:.7},projection,ortho:true,aspect:1.75};
 function camera(data){
  const tr={method:n=>({invoke(v){if(n.startsWith('get_'))return value(data[n.slice(4)]);data[n.slice(4)]=v?Object.fromEntries((n==='set_position'?['x','y','z']:['x','y','z','w']).map(k=>[k,v.field(k).value])):null;}})};
  return {method:n=>({invoke(...a){
   if(n==='CopyFrom'){Object.assign(data,source);return;}
   if(n==='get_transform')return tr;
   if(n==='set_projectionMatrix'){data.projection=Object.fromEntries(Object.keys(projection).map(k=>[k,a[0].field(k).value]));return;}
   if(n==='get_projectionMatrix')return value(data.projection);
   if(n==='get_orthographic')return data.ortho;
   if(n==='get_aspect')return data.aspect;
   if(n==='get_fieldOfView')return 40;
   if(n==='get_orthographicSize')return 2;
   if(n==='set_aspect')throw Error('STRIPPED_SETTER');
   if(n==='Render'){events.push('render');assert.deepEqual(data.position,source.position);assert.deepEqual(data.rotation,source.rotation);
     for(const key of Object.keys(expectedProjection))assert(Math.abs(data.projection[key]-expectedProjection[key])<1e-12);
     if(fail==='render')throw Error('RENDER_FAILED');}
  }})};
 }
 const expectedProjection={...projection,m10:projection.m10*.625/1.75,m11:projection.m11*.625/1.75,m12:projection.m12*.625/1.75,m13:projection.m13*.625/1.75};
 const src=camera(source),core=name=>({alloc(){
   if(name==='Matrix4x4'){const data={};return {unbox:()=>({field:k=>({get value(){return data[k];},set value(v){data[k]=v;}})})};}
   const o={id:++sequence,method:n=>({invoke(){if(n==='AddComponent')return camera({});}})};live.add(o);return o;},
  type:{object:name},method:n=>({invoke(o){if(n==='DestroyImmediate'){events.push('destroy');live.delete(o);}}})});
 const c={camera:src,token:'token',identity:'owned'};
 const preview={verify:()=>c,adapter:{cameraState:()=>({camera_id:'camera',preview_identity:'owned'})}};
 const quality={begin(){if(fail==='allocate')throw Error('ALLOCATE_FAILED');return {target:{},metadata:{output_width:640,output_height:1024,render_width:640,render_height:1024},encode(){if(fail==='encode')throw Error('ENCODE_FAILED');return 'png';},dispose(){events.push('dispose');}};}};
 return {render:createEditorCapture({core,preview,quality}),live,events,source};
}
{
 const n=native(),r=n.render({expected_model:'token',size:512,quality:'balanced',width:640,height:1024});
 assert.equal(r.provenance,'clean_current_editor_render');assert.equal(r.width,640);assert.equal(r.height,1024);
 assert.equal(r.projection,'orthographic');assert.deepEqual(r.framing.render_position,[2,3,4]);
 assert.equal(n.live.size,0);assert.deepEqual(n.events,['render','destroy','dispose']);
}
for(const fail of ['allocate','render','encode']){
 const n=native(fail);assert.throws(()=>n.render({expected_model:'token',size:512,quality:'balanced',width:640,height:1024}),/FAILED/);
 assert.equal(n.live.size,0);assert(n.events.includes('destroy'));if(fail!=='allocate')assert(n.events.includes('dispose'));
}
for(const aspect of [16/9,1,9/16])for(const perspective of [true,false])for(const [width,height] of [[640,1024],[1024,640],[2048,1536]]){
    const p=[1,0,.12,0,0,aspect,.2,0,0,0,-1,-1,0,0,perspective?-1:0,perspective?0:1],original=[...p];
    const plan=captureQualityPlan(512,'high',{width,height,ssaa:3});
    const fit=expandCaptureProjection(p,aspect,plan);
    const project=point=>{
        const v=[...point,1],clip=[0,1,2,3].map(r=>v.reduce((s,x,i)=>s+fit.matrix[r*4+i]*x,0));
        // Native renders to the full RT, then quality encode resamples each axis.
        return [clip[0]/clip[3]*plan.render_width*(width/plan.render_width),clip[1]/clip[3]*plan.render_height*(height/plan.render_height)];
    };
    const dx=project([1,0,-5])[0]-project([-1,0,-5])[0],dy=project([0,1,-5])[1]-project([0,-1,-5])[1];
    assert(Math.abs(dx-dy)<1e-10,'a projected square/round target keeps equal pixel diameters');
    const center=project([0,0,-5]);
    for(let i=0;i<32;i++){
        const angle=2*Math.PI*i/32,point=project([Math.cos(angle),Math.sin(angle),-5]);
        assert(Math.abs(Math.hypot(point[0]-center[0],point[1]-center[1])-dx/2)<1e-10,'the whole projected circle remains round');
    }
    assert.deepEqual(p,original,'live matrix was not changed');
    assert(fit.clip_scale.every(v=>v>0&&v<=1),'source frustum content is contained without crop');
    assert.deepEqual(fit.render_viewport,[0,0,plan.render_width,plan.render_height]);
}
console.log('live pose/projection, rectangular output, cleanup and no-fallback behavior passed');
