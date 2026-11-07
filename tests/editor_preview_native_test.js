// Execute the supported-build ownership adapter without a running Unity process.
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
vm.runInThisContext(fs.readFileSync('agent/editor_preview.js','utf8'));
function fixture(multi=true){
 let sequence=0;const calls=[];
 function obj(name,methods={},fields={}){
   const key=++sequence;return {class:{type:{name}},handle:{isNull:()=>false,toString:()=>String(key),equals:h=>h?.toString()===String(key)},
     field:n=>{if(!(n in fields))throw Error('UNKNOWN_FIELD '+n);return {get value(){return fields[n];},set value(v){fields[n]=v;}};},
     method(n){if(!(n in methods))throw Error('UNEXPECTED_NATIVE_METHOD '+n+' ON '+name);return {invoke:methods[n]};},
     tryMethod(n){return n in methods;},methods,fields};
 }
 const nil={handle:{isNull:()=>true,toString:()=> '0'}};
 const v=a=>({field:k=>({value:a['xyzw'.indexOf(k)]})});
 const go=obj('GameObject',{get_activeInHierarchy:()=>true});
 const origin=obj('Transform',{get_parent:()=>nil});
 const tr=obj('Transform',{get_position:()=>v([1,2,3]),get_parent:()=>origin});
 const mesh=obj('UnityEngine.Mesh',{GetInstanceID:()=>10,get_blendShapeCount:()=>2,GetBlendShapeName:i=>({content:['Smile','prefix.Smile'][i],handle:{isNull:()=>false}})});
 const weights=[10,20];
 const renderer=obj('UnityEngine.SkinnedMeshRenderer',{get_transform:()=>tr,get_gameObject:()=>go,get_sharedMesh:()=>mesh,GetInstanceID:()=>9,
   GetBlendShapeWeight:i=>weights[i],SetBlendShapeWeight:(i,w)=>{calls.push('weight');weights[i]=w;}});
 const engine=obj('engine'),file=obj('file',{}, {engine}),main=obj('main'),face=obj('face',{}, {_engine:engine});
 const root=obj('root',{get_FaceEditor:()=>face},{_engineModel:engine});
 let active=root,groups=[],angles=[1,2],rotating=false;
 const transform=obj('Transform',{get_position:()=>v([1,2,3])});
 const controller=obj('VRoid.UI.Component.AvatarCameraPosition',{get_isActiveAndEnabled:()=>true,get_gameObject:()=>go,get_transform:()=>transform,GetAngles:()=>v(angles),
   ChangeAngles:a=>{calls.push('angles');angles=['x','y'].map(k=>a.field(k).value);},Zoom:d=>calls.push(['zoom',d]),Pan:p=>calls.push(['pan',...['x','y'].map(k=>p.field(k).value)]),
   ResetPosition:()=>calls.push('reset'),SwitchCameraProjection:()=>{calls.push('projection');camera.fields.ortho=!camera.fields.ortho;},
   RotateAxis:value=>{calls.push(['mode',value]);rotating=true;},SetCustomView:(p,c)=>calls.push(['custom',...['x','y','z'].map(k=>p.field(k).value),...['x','y','z'].map(k=>c.field(k).value)])}, {_rotationCenter:v([0,1,0])});
 Object.defineProperty(controller.fields,'_isRunningCameraRotateCoroutine',{get:()=>rotating});
 const camera=obj('UnityEngine.Camera',{get_transform:()=>transform,get_enabled:()=>true,get_gameObject:()=>go,get_orthographic:()=>camera.fields.ortho,
   get_fieldOfView:()=>42,get_orthographicSize:()=>2,get_aspect:()=>1.5},{ortho:false});
 const group=obj('VRoid.UI.Component.CameraGroup',{get_PrimaryCamera:()=>camera});groups.push(group);
 const enumerator=()=>{let i=-1;return obj('enum',{MoveNext:()=>++i<groups.length,get_Current:()=>groups[i],Dispose:()=>{}});};
 const rig=obj('VRoid.UI.Component.MultipleRenderTextureCamera',{get_transform:()=>transform,get_InstantiatedCameras:()=>obj('dictionary',{
   get_Keys:()=>obj('keys',{GetEnumerator:enumerator})})});
 controller.fields._multipleRenderTextureCamera=multi?rig:nil;controller.fields._unityCamera=multi?nil:camera;
 const wrapper=obj('wrapper',{}, {_body:rig});
 const bus=obj('bus',{get_ScreenNavigation:()=>obj('nav',{get_ActiveScreen:()=>active}),get_ModelOrigin:()=>origin,
   get_EditAvatarCameraPosition:()=>controller,get_PhotoBoothAvatarCameraPosition:()=>nil,
   get_Common3D:()=>obj('common',{get_AvatarCamera:()=>wrapper})});
 main.methods.get_GlobalBus=()=>bus;face.methods.get_GlobalBus=()=>bus;face.methods.GetFaceSMR=()=>renderer;
 const model=expected=>{if(expected!=='token')throw Error('STALE_MODEL');return {main,root,face,engine,file,token:'token'};};
 function core(name){return {alloc:()=>{let coordinates=[];return {unbox:()=>({field:k=>({get value(){return coordinates['xyzw'.indexOf(k)];}}),method:()=>({invoke(...args){coordinates=args;}})})};}};}
 const modes={nestedClasses:[{name:'CameraRotationMode',fields:[{name:'Right',isStatic:true,value:701}]}]};
 const adapter=createEditorPreviewNative({model,core,cls:()=>modes,text:s=>s.content});
 return {adapter,calls,controller,camera,rig,group,groups,renderer,root,face,wrapper,setActive:v=>active=v,setRotating:v=>rotating=v,
  orphan(){renderer.methods.get_transform=()=>obj('otherTransform',{get_parent:()=>nil});},go,weights};
}
for(const multi of [false,true]){
 const f=fixture(multi),c=f.adapter.open('token'),s=f.adapter.cameraState(c);
 assert.equal(s.camera_path,multi?'owned_instantiated_group':'owned_single_camera');assert.equal(s.projection,'perspective');
 f.adapter.cameraAction(c,'projection',{});assert.equal(f.adapter.cameraState(c).projection,'orthographic');
 f.adapter.cameraAction(c,'mode',{mode:'Right'});assert(f.adapter.cameraState(c).rotating);assert.deepEqual(f.calls[1],['mode',701]);
 f.adapter.setWeight(c,1,77);assert.equal(f.adapter.face(c)[1].weight,77);
 f.setActive(f.face);assert.throws(()=>f.adapter.identity(c),/ACTIVE_EDIT_ROOT/);
}
for(const multi of [false,true]){
 const f=fixture(multi),api=createEditorPreview({adapter:f.adapter}).operations;
 assert.deepEqual(api.editor_camera({expected_model:'token',action:'angles',angles:[30,-10]}).angles,[30,-10]);
 assert.deepEqual(api.editor_camera({expected_model:'token',action:'rotate',angles:[2,3]}).angles,[32,-7]);
 api.editor_camera({expected_model:'token',action:'zoom',delta:-.5});
 api.editor_camera({expected_model:'token',action:'pan',pan:[.25,-.75]});
 api.editor_camera({expected_model:'token',action:'reset'});
 api.editor_camera({expected_model:'token',action:'custom',position:[1,3,5],center:[2,4,6]});
 assert.deepEqual(f.calls,['angles','angles',['zoom',-.5],['pan',.25,-.75],'reset',['custom',1,3,5,2,4,6]]);
 const before=f.calls.length;
 for(const args of [{action:'angles',angles:[NaN,0]},{action:'custom',position:[0,0,0],center:[0,0,0]},
   {action:'get',mode:'Front'},{action:'mode',mode:'Guess'},{action:'zoom',delta:true},{action:'unknown'}])
   assert.throws(()=>api.editor_camera({expected_model:'token',...args}));
 assert.equal(f.calls.length,before);
}
for(const mutate of [f=>f.groups.push(f.group),f=>f.orphan(),f=>f.wrapper.fields._body=f.controller,
 f=>f.face.fields._engine=f.root,f=>f.go.methods.get_activeInHierarchy=()=>false]){
 const f=fixture();mutate(f);assert.throws(()=>f.adapter.open('token'));assert.equal(f.calls.length,0);
}
console.log('native single/multi ownership, active-screen, dictionary-key, scoped-face and enum identities passed');
