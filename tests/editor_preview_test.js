const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
vm.runInThisContext(fs.readFileSync('agent/editor_preview.js','utf8'));
function fixture(){
    let owner='face:mesh',angles=[10,20],running=false,projection=false,calls=[],weights=[10,20,30];
    const names=['Smile','prefix.Smile','EyeBlink'];
    const adapter={open:()=>({token:'token',identity:owner}),identity:c=>{if(c.identity!==owner)throw Error('STALE_PREVIEW');return owner;},
        cameraState:()=>({angles:[...angles],rotating:running,projection:projection?'orthographic':'perspective',camera_id:'camera'}),
        cameraAction:(c,a,args)=>{calls.push(a);if(a==='angles')angles=[...args.angles];if(a==='projection')projection=!projection;if(a==='mode')running=true;},
        face:()=>names.map((name,index)=>({name,index,weight:weights[index]})),setWeight:(c,i,v)=>{calls.push(i);weights[i]=v;}};
    return {api:createEditorPreview({adapter}),calls,weights,setOwner:v=>owner=v,setRunning:v=>running=v};
}
{
 const f=fixture();assert.throws(()=>f.api.operations.face_preview({expected_model:'token',restore:true}),/SNAPSHOT/);
 assert.throws(()=>f.api.operations.face_preview({expected_model:'token',name:'Smile',weight:Infinity}));
 assert.throws(()=>f.api.operations.face_preview({expected_model:'token',name:'Smile',reset:true}));
 assert.equal(f.calls.length,0);
 f.api.operations.face_preview({expected_model:'token',name:'prefix.Smile',weight:55});assert.deepEqual(f.weights,[10,55,30]);
 f.weights[1]=1;assert.throws(()=>f.api.verify('token'),/WEIGHT_CHANGED/);
 f.setOwner('changed');assert.throws(()=>f.api.operations.face_preview({expected_model:'token',reset:true}),/STALE/);
 assert.equal(f.calls.length,1);
}
{
 const f=fixture();f.api.operations.editor_camera({expected_model:'token',action:'rotate',angles:[5,-3]});
 assert.deepEqual(f.api.operations.editor_camera({expected_model:'token',action:'get'}).angles,[15,17]);
 assert.equal(f.api.operations.editor_camera({expected_model:'token',action:'projection'}).projection,'orthographic');
 assert.throws(()=>f.api.operations.editor_camera({expected_model:'token',action:'pan',pan:[0,Infinity]}));
 assert.throws(()=>f.api.operations.editor_camera({expected_model:'token',action:'get',delta:1}));
 assert.deepEqual(f.calls,['angles','projection']);
}
{
 const f=fixture();assert.equal(f.api.operations.face_preview({expected_model:'token',filter:'smile'}).shapes.length,2);
 f.api.operations.face_preview({expected_model:'token',name:'Smile',weight:90});assert.deepEqual(f.weights,[90,20,30]);
 assert.throws(()=>f.api.operations.face_preview({expected_model:'token',name:'ile',weight:80}),/AMBIGUOUS/);
 f.api.operations.face_preview({expected_model:'token',reset:true});assert.deepEqual(f.weights,[0,0,0]);
 f.api.operations.face_preview({expected_model:'token',restore:true});assert.deepEqual(f.weights,[10,20,30]);
 f.setOwner('changed');assert.throws(()=>f.api.verify('token'),/STALE/);
}
console.log('editor actions and scoped raw preview behavior passed');
