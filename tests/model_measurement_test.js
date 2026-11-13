const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
vm.runInThisContext(fs.readFileSync('agent/capture_framing.js','utf8'));
global.state={frame:42};
const vector=values=>({field:k=>({value:values[['x','y','z'].indexOf(k)]})});
const nullObject={handle:{isNull:()=>true}};
let next=0;
const obj=methods=>({handle:{isNull:()=>false,toString:()=>String(++next)},method:name=>{
    const method={invoke:(...args)=>{if(!Object.hasOwn(methods,name))throw Error(name);return methods[name](...args);}};
    method.overload=()=>method;return method;}});
function node(id,box=null,enabled=true,active=true){
    const children=[];let parent=null,animator=nullObject;
    const renderer=box?obj({get_enabled:()=>enabled,get_bounds:()=>obj({get_center:()=>vector(box.center),get_extents:()=>vector(box.extents)})}):nullObject;
    const go=obj({get_activeInHierarchy:()=>active,GetComponent:type=>type==='Renderer'||type==='SkinnedMeshRenderer'?renderer:type==='Animator'?animator:nullObject});
    const transform=obj({get_gameObject:()=>go,get_childCount:()=>children.length,GetChild:i=>children[i],
        get_parent:()=>parent||nullObject,get_name:()=>id,get_position:()=>vector([3,2,-6])});
    transform.handle.toString=()=>id;
    return {transform,setAnimator:a=>{animator=a;},add:n=>{children.push(n.transform);n.parent(transform);},parent:p=>{parent=p;}};
}
const root=node('owned'),face=node('face',{center:[3,2,-6],extents:[1,1,2]});root.add(face);
root.add(node('disabled',{center:[100,100,100],extents:[20,20,20]},false));
root.add(node('inactive',{center:[100,100,100],extents:[20,20,20]},true,false));
// Unrelated scene geometry is deliberately not reachable from ModelOrigin.
node('unrelated',{center:[999,999,999],extents:[999,999,999]});
const bus=obj({get_ModelOrigin:()=>root.transform});bus.handle.toString=()=> 'bus';
const m={token:'token',main:obj({get_GlobalBus:()=>bus}),face:obj({GetFaceSMR:()=>obj({get_transform:()=>face.transform})})};
const api=createCaptureFraming({core:name=>({type:{object:name}}),text:x=>x,
    cls:()=>{throw Error('optional animator unavailable');}});
const result=api.reference(m);
assert.deepEqual(result.bounds,{min:[2,1,-8],max:[4,3,-4]});
assert.equal(result.renderer_count,1);assert.deepEqual(result.horizontal_center,[3,-6]);
assert.equal(result.vertical_span_m,2);assert.equal(result.renderer_extent_cm,200);
assert.equal(result.source_grounded_max_y_cm,300);assert.equal(result.landmarks.Head.available,false);
assert.equal(result.landmarks.LeftFoot.available,false);
const external=node('foreign-bone');
root.setAnimator(obj({get_isHuman:()=>true,GetBoneTransform:value=>value===10?face.transform:external.transform}));
const humanoid=createCaptureFraming({core:name=>({type:{object:name}}),text:x=>x,
    cls:(assembly,name)=>name.endsWith('Animator')?{type:{object:'Animator'}}:{field:name=>({value:name==='Head'?10:20})}});
const one=humanoid.reference(m);
assert.equal(one.landmarks.Head.available,true);assert.equal(one.landmarks.Head.world_y,2);
assert.equal(one.landmarks.LeftFoot.available,false);
face.setAnimator(obj({get_isHuman:()=>true}));
assert.equal(humanoid.reference(m).landmarks.Head.available,false);
console.log('scoped translated geometry ignores disabled/inactive/unrelated renderers and missing humanoid landmarks without requiring a camera');
