// Executes the actual screenshot function with a camera that begins shifted.
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
vm.runInThisContext(fs.readFileSync('agent/capture_framing.js','utf8'));
vm.runInThisContext(fs.readFileSync('agent/editor_capture.js','utf8'));
vm.runInThisContext(fs.readFileSync('agent/capture_quality.js','utf8'));
const source=fs.readFileSync('agent/operations.js','utf8'),start=source.indexOf('    function screenshot(args)'),end=source.indexOf('    // ------------------------------------------------------------- composition',start);
assert(start>0&&end>start);
const v=a=>({field:k=>({value:a[['x','y','z','w'].indexOf(k)]})});
const profile={top:0,bottom:1,half:null,distance:.1,yaw:0,fit:'full-body'};
const plan=situationCameraPlan({min:[2,1,-8],max:[4,3,-4]},profile,1);
function run(ignoreMatrix=false,clip=undefined){
    let renders=0,disposed=0;const backing={position:[0,0,0],rotation:[0,0,0,1],matrix:situationProjection(plan),near:.2,far:2000};backing.matrix[2]=2;
    const method=fn=>{const m={invoke:fn};m.overload=()=>m;return m;};
    const renderer={method:name=>method(()=>({method:k=>method(()=>k==='get_center'?v([3,2,-6]):v([1,1,2]))}))};
    const camera={method:name=>method((...a)=>{
        if(name==='CopyFrom')return;
        if(name==='get_transform')return {method:k=>method(value=>{
            if(k==='get_position')return v(backing.position);if(k==='get_rotation')return v(backing.rotation);
            if(k==='set_position')backing.position=['x','y','z'].map(x=>value.field(x).value);
            if(k==='LookAt')backing.rotation=[0,1,0,0];
        })};
        if(name==='get_aspect')return 1;
        if(name==='get_fieldOfView')return 30;
        if(name==='get_orthographic')return false;
        if(name==='get_nearClipPlane')return clip===undefined?backing.near:clip;
        if(name==='get_farClipPlane')return backing.far;
        if(name==='set_nearClipPlane'){backing.near=a[0];return;}
        if(name==='set_farClipPlane'){backing.far=a[0];return;}
        if(name==='get_projectionMatrix')return {field:k=>({value:backing.matrix[Number(k[1])*4+Number(k[2])]})};
        if(name==='set_projectionMatrix'){
            if(!ignoreMatrix)backing.matrix=Array.from({length:16},(_,i)=>a[0].field('m'+Math.floor(i/4)+i%4).value);return;
        }
        if(name==='Render'){renders++;assert.equal(backing.matrix[2],0);return;}
    })};
    const body={field:()=>({value:{method:()=>method(()=>camera)}})};
    const bus={method:()=>method(()=>({method:()=>method(()=>({field:()=>({value:body})}))}))};
    const m={token:'token',main:{method:()=>method(()=>bus)},face:{method:()=>method(()=>renderer)},
        root:{field:()=>({value:{method:()=>method(()=>false)}})}};
    const core=name=>({type:{object:name},alloc(){
        if(name==='Matrix4x4'){const data={};return {unbox:()=>({field:k=>({get value(){return data[k];},set value(x){data[k]=x;}})})};}
        return {method:key=>method(()=>key==='AddComponent'?camera:undefined)};
    },method:key=>method(()=>null)});
    const api=createCaptureFraming({core,text:x=>x});
    const scope={modelContext:()=>m,core,captureQualityPlan,parseCaptureView,captureProjectionValues,writeCaptureProjection,situationProjection,
        cleanCaptureScope:{inspect:()=>({}),apply(){},verify(){}},captureFraming:{situationPlan:()=>plan,readback:api.readback},
        captureQuality:{begin:()=>({target:{},metadata:{},encode:()=> 'png',dispose(){disposed++;}})},
        vector:(...a)=>v(a),Il2Cpp:{string:x=>x},editorPreview:{verifyIfTracked(){}},captureCleanup:steps=>steps.forEach(f=>f())};
    const context=vm.createContext(scope);vm.runInContext(source.slice(start,end)+';this.render=screenshot;',context);
    let result,error;try{result=context.render({expected_model:'token',view:'front',size:512,quality:'balanced',situation_framing:profile});}
    catch(e){error=e;}
    return {result,error,renders,disposed};
}
const good=run();assert.ifError(good.error);assert.equal(good.renders,1);assert.equal(good.result.framing.projection_verified,true);
const ignored=run(true);assert(ignored.error);assert.equal(ignored.renders,0);assert.equal(ignored.disposed,1);
for(const clip of [NaN,.2]){const bad=run(false,clip);assert(bad.error);assert.equal(bad.renders,0);}
console.log('actual situation screenshot overwrites a shifted clone projection; ignored writes/nonfinite or wrong clips refuse before Render');
