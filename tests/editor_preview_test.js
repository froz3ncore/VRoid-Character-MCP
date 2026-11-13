const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
vm.runInThisContext(fs.readFileSync('agent/editor_preview.js','utf8'));
function rejected(fn,pattern){const result=fn();assert.equal(result.ok,false);assert.equal(result.native_invocation_attempted,false);if(pattern)assert.match(result.error,pattern);}
function fixture(count=3){
    let owner='face:mesh',angles=[10,20],running=false,projection=false,calls=[],weights=[10,20,30];
    const names=count===3?['Smile','prefix.Smile','EyeBlink']:Array.from({length:count},(_,i)=>'shape'+i);
    if(count!==3)weights=names.map(()=>10);
    let identities=0,failWrite=false,reads=0,lateInvalid=false,guardCalls=0,guardOverride=null;
    const adapter={open:()=>({token:'token',identity:owner}),identity:c=>{identities++;if(c.identity!==owner)throw Error('STALE_PREVIEW');return owner;},
        cameraState:()=>({angles:[...angles],rotating:running,projection:projection?'orthographic':'perspective',camera_id:'camera'}),
        cameraAction:(c,a,args)=>{calls.push(a);if(a==='angles')angles=[...args.angles];if(a==='projection')projection=!projection;if(a==='mode')running=true;},
        face:()=>{reads++;return names.map((name,index)=>({name,index,weight:lateInvalid&&reads===3&&index===0?NaN:weights[index]}));},setWeight:(c,i,v)=>{calls.push(i);weights[i]=failWrite?NaN:v;}};
    return {api:createEditorPreview({adapter,beforeMutation:()=>{guardCalls++;if(guardOverride)guardOverride();}}),calls,weights,setOwner:v=>owner=v,setRunning:v=>running=v,
        setGuard:fn=>guardOverride=fn,
        failWrite:()=>failWrite=true,lateInvalid(){reads=0;lateInvalid=true;},get identities(){return identities;},get guardCalls(){return guardCalls;}};
}
{
 const f=fixture();rejected(()=>f.api.operations.face_preview({expected_model:'token',restore:true}),/SNAPSHOT/);
 rejected(()=>f.api.operations.face_preview({expected_model:'token',name:'Smile',weight:Infinity}));
 rejected(()=>f.api.operations.face_preview({expected_model:'token',name:'Smile',reset:true}));
 assert.equal(f.calls.length,0);
 f.api.operations.face_preview({expected_model:'token',name:'prefix.Smile',weight:55});assert.deepEqual(f.weights,[10,55,30]);
 f.weights[1]=1;assert.throws(()=>f.api.verify('token'),/WEIGHT_CHANGED/);
 f.setOwner('changed');rejected(()=>f.api.operations.face_preview({expected_model:'token',reset:true}),/STALE/);
 assert.equal(f.calls.length,1);
}
{
 const f=fixture();f.api.operations.editor_camera({expected_model:'token',action:'rotate',angles:[5,-3]});
 assert.deepEqual(f.api.operations.editor_camera({expected_model:'token',action:'get'}).angles,[15,17]);
 assert.equal(f.api.operations.editor_camera({expected_model:'token',action:'projection'}).projection,'orthographic');
 rejected(()=>f.api.operations.editor_camera({expected_model:'token',action:'pan',pan:[0,Infinity]}));
 rejected(()=>f.api.operations.editor_camera({expected_model:'token',action:'get',delta:1}));
 assert.deepEqual(f.calls,['angles','projection']);
}
{
 const f=fixture();assert.equal(f.api.operations.face_preview({expected_model:'token',filter:'smile'}).shapes.length,2);
 f.api.operations.face_preview({expected_model:'token',name:'Smile',weight:90});assert.deepEqual(f.weights,[90,20,30]);
 rejected(()=>f.api.operations.face_preview({expected_model:'token',name:'ile',weight:80}),/AMBIGUOUS/);
 f.api.operations.face_preview({expected_model:'token',reset:true});assert.deepEqual(f.weights,[0,0,0]);
 f.api.operations.face_preview({expected_model:'token',restore:true});assert.deepEqual(f.weights,[10,20,30]);
 f.weights[0]=23;f.setOwner('rebuilt');assert.doesNotThrow(()=>f.api.verify('token'));
 f.api.operations.face_preview({expected_model:'token',name:'Smile',weight:60});
 f.api.operations.face_preview({expected_model:'token',restore:true});assert.equal(f.weights[0],23);
}
{
 const f=fixture();f.weights[0]=NaN;const r=f.api.operations.face_preview({expected_model:'token',name:'Smile',weight:60});
 assert.equal(r.ok,false);assert.equal(r.native_invocation_attempted,false);assert.equal(f.calls.length,0);
}
{
 const f=fixture();f.failWrite();const r=f.api.operations.face_preview({expected_model:'token',name:'Smile',weight:60});
 assert.equal(r.ok,false);assert.equal(r.uncertain,true);assert.throws(()=>f.api.verify('token'),/UNCONFIRMED/);
}
{
 const f=fixture(4096);f.api.operations.face_preview({expected_model:'token',reset:true});
 assert(f.identities<20,'full ownership discovery must not scale with shape count');
}
{
 const f=fixture();f.api.operations.face_preview({expected_model:'token',name:'Smile',weight:60});f.lateInvalid();
 const r=f.api.operations.face_preview({expected_model:'token',restore:true});assert.equal(r.uncertain,true);assert.equal(r.restoration_verified,undefined);
 assert.throws(()=>f.api.verify('token'),/UNCONFIRMED/);
}
{
 const f=fixture();rejected(()=>f.api.operations.face_preview({expected_model:'token',name:'ile'}),/AMBIGUOUS/);
 f.api.operations.get_editor_camera({expected_model:'token'});f.api.operations.list_face_preview({expected_model:'token'});assert.equal(f.guardCalls,0);
 assert(f.api.operations.face_preview({expected_model:'token',name:'Smile',weight:70}).ok);assert.equal(f.guardCalls,1);
 f.weights[0]=Infinity;assert.throws(()=>f.api.verify('token'),/NONFINITE/);
}
console.log('editor actions and scoped raw preview behavior passed');
{
 const f=fixture();assert(f.api.operations.face_preview({expected_model:'token',name:'Smile',weight:60}).ok);
 f.setGuard(()=>{const error=Error('ATTACHED_UI_BLOCKED');error.attached_guard_prewrite=true;error.attached_guard_bookkeeping_attempted=false;throw error;});
 const blocked=f.api.operations.face_preview({expected_model:'token',name:'Smile',weight:40});
 assert.equal(blocked.uncertain,false);assert.equal(blocked.native_invocation_attempted,false);assert.equal(blocked.dispatch_state,'prewrite_rejected');
 assert.deepEqual(f.calls,[0]);assert.equal(f.weights[0],60);assert.doesNotThrow(()=>f.api.verify('token'));
 f.setGuard(null);assert(f.api.operations.face_preview({expected_model:'token',name:'Smile',weight:40}).ok);assert.equal(f.weights[0],40);
}
for(const kind of ['receipt_write','unknown_guard','unattested_ui_error']){
 const f=fixture();f.api.operations.face_preview({expected_model:'token',name:'Smile',weight:60});
 f.setGuard(()=>{const error=Error(kind==='unattested_ui_error'?'ATTACHED_UI_BLOCKED':kind);if(kind==='receipt_write'){error.attached_guard_bookkeeping_attempted=true;error.native_uncertain=true;}throw error;});
 const result=f.api.operations.face_preview({expected_model:'token',name:'Smile',weight:40});
 assert.equal(result.uncertain,true);assert.equal(result.native_invocation_attempted,false);assert.equal(f.weights[0],60);
 assert.deepEqual(f.calls,[0]);assert.doesNotThrow(()=>f.api.verify('token'),'a guard error did not enter a weight setter');
}
console.log('definite guard rejection preserves preview; uncertain guard bookkeeping stays separate from native entry');
