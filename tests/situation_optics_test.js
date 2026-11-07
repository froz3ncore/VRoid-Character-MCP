const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
vm.runInThisContext(fs.readFileSync('agent/capture_framing.js','utf8'));
const profile={top:0,bottom:1,half:null,distance:.1,yaw:0,fit:'full-body'};
const plan=situationCameraPlan({min:[2,1,-8],max:[4,3,-4]},profile,.5),f=1/Math.tan(Math.PI/12),n=plan.near_clip,a=plan.far_clip;
const matrix=[f/.5,0,0,0,0,f,0,0,0,0,-(a+n)/(a-n),-2*a*n/(a-n),0,0,-1,0];
const val=values=>({field:k=>({value:values[k]})});
function camera(shift=0,near=n){return {method:name=>({invoke(){
    if(name==='get_transform')return {method:key=>({invoke:()=>key==='get_position'?val(Object.fromEntries(['x','y','z'].map((k,i)=>[k,plan.position[i]]))):val({x:0,y:1,z:0,w:0})})};
    if(name==='get_fieldOfView')return 30;if(name==='get_orthographic')return false;
    if(name==='get_nearClipPlane')return near;if(name==='get_farClipPlane')return a;
    if(name==='get_projectionMatrix')return val(Object.fromEntries(matrix.map((v,i)=>['m'+Math.floor(i/4)+i%4,i===2?v+shift:v])));
    throw Error(name);
}})};}
const api=createCaptureFraming({core:()=>{},text:x=>x});
assert.equal(api.readback(camera(),plan).projection_verified,true);
assert.throws(()=>api.readback(camera(2),plan));
assert.throws(()=>api.readback(camera(0,NaN),plan));
assert.throws(()=>api.readback(camera(0,.1),plan));
console.log('actual camera matrix/pose/clip readback and independent corner projection passed');
const ownership=captureModelOwnership({engine:{handle:{toString:()=> 'exact-engine'}},
    file:{field:name=>{assert.equal(name,'path');return {value:'E:/lab/saves/snapshot.vroid'};}}},x=>x);
assert.deepEqual(ownership,{engine_id:'exact-engine',file_path:'E:/lab/saves/snapshot.vroid'});
