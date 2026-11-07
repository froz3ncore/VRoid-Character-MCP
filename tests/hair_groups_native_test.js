// Execute the native adapter through query/command doubles; no live app is used.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
vm.runInThisContext(fs.readFileSync(path.join(__dirname,'../agent/hair_groups.js'),'utf8'));
assert.equal(typeof globalThis.createHairGroupNative,'function','native hair group adapter missing');
let pins=0,commands=[],type='BrushHairGroupPath',complete=true,active=true,screen='VRoid.Studio.EditRootScreen.ViewModel';
global.Il2Cpp={string:value=>({handle:value})};
const obj=(methods={},fields={},name='Fixture')=>{
    const o={class:{type:{name:'VRoidCore.Common.SpecificTypes.'+name}},
        method:n=>({invoke:(...a)=>{if(!methods[n])throw Error('Missing '+n);return methods[n](...a);}}),
        tryMethod:n=>methods[n]?o.method(n):null,
        field:n=>({get value(){return fields[n];},set value(v){fields[n]=v;}}),
        tryField:n=>n in fields?o.field(n):null};
    o.handle={isNull:()=>false,owner:o};return o;
};
const pth=(kind,id)=>obj({get_TransferableId:()=> 't',get_HairGroupId:()=> 'g',
    ...(kind==='BrushHairStrandPath'?{get_HairStrandId:()=>id}:{})},{},kind);
const group=()=>pth(type),strand=pth('BrushHairStrandPath','s');
const vector=a=>obj({},Object.fromEntries(['x','y','z'].slice(0,a.length).map((k,i)=>[k,a[i]])));
const point=()=>obj({}, {'<Point>k__BackingField':vector([2,3,4]),'<Normal>k__BackingField':vector([.1,.2,.3]),
    '<Uv>k__BackingField':vector([.4,.5]),unknown:987});
let cp=point();
const box=v=>{const b=obj();b.unbox=()=>v;return b;};
const material=obj({get_SharedHairMaterialId:()=> 'mat',get_TransferableMaterialId:()=>null});
const guide=obj({}, {Position:vector([1,2,3]),Rotation:obj({}, {x:0,y:0,z:0,w:1}),Scale:vector([1,1,1])});
const context=obj({get_ActiveModel:()=>obj(),GetActiveLeafTransferables:()=>[['t',obj({get_GroupId:()=> 'owner'})]],
    ExecuteSyncCommand:c=>{commands.push(c.owner);if(c.owner.name==='MoveBrushHairStrandControlPointCommand')cp=c.owner.args[2].owner;}});
const currentScreen=()=>({class:{type:{name:screen}}});
const main=obj({get_GlobalBus:()=>obj({get_ScreenNavigation:()=>obj({get_ActiveScreen:currentScreen})})});
const m={token:'fresh',context,main};
const queries={GetHairGroupListQuery:()=>[group()],GetHairGroupChildrenQuery:()=>[strand],
    GetHairStrandControlPointCountQuery:()=>box(obj({}, {m_value:1})),
    GetHairStrandControlPointQuery:()=>box(cp),
    GetBrushHairGroupParameterSetQuery:()=>obj({get_HairMaterialReference:()=>material}),
    GetBrushHairStrandParameterSetQuery:()=>obj({get_HairMaterialReference:()=>material}),
    GetGuideOriginTransformQuery:()=>box(guide)};
const helpers={hairDesignEditor:()=>0,hairNodeList:()=>[{id:'t/g',parent:null,n:obj({get_HairGroupPath:group})}],
    seq:x=>x,boxArgument:(_,v)=>v,readPoint:b=>{
        const v=b.unbox();return {point:['x','y','z'].map(k=>v.field('<Point>k__BackingField').value.field(k).value),
            normal:['x','y','z'].map(k=>v.field('<Normal>k__BackingField').value.field(k).value),
            uv:['x','y'].map(k=>v.field('<Uv>k__BackingField').value.field(k).value)};
    }};
const adapter=createHairGroupNative({model:t=>{assert.equal(t,'fresh');return m;},text:x=>x,
    groupHelpers:{prop:(o,k)=>o.method('get_'+k).invoke(),sequence:x=>x},
    retain:()=>{pins++;return {free(){pins--;}};},helpers,
    inventory:()=>({membership_complete:complete,groups:[{id:'owner',active}]}),
    cls:(_,name)=>({alloc:()=>{const o=obj();o.name=name.split('.').pop();return o;}}),
    invokeManaged(o,name,args=[]){
        if(name==='.ctor'){o.args=args;return;}
        if(name==='Execute')return queries[o.name](o.args);
        return o.method(name).invoke(...args);
    },state:{frame:9}});
const a={expected_model:'fresh',category:'HairFront',scope:'t/g'},s=adapter.begin(a);
let snap=adapter.snapshot(s,'HairFront','t/g');
assert.equal(snap.type,'brush');assert.deepEqual(snap.material,{shared:'mat',transferable:null});
assert.deepEqual(snap.strands[0].material,{shared:'mat',transferable:null});
assert.deepEqual(snap.strands[0].points[0].normal,[.1,.2,.3]);assert(pins>0);
adapter.move(s,'t/g','t/g/s',0,{...snap.strands[0].points[0],point:[5,6,7]});
assert.equal(commands[0].name,'MoveBrushHairStrandControlPointCommand');
assert.equal(cp.field('unknown').value,987);assert.equal(cp.field('<Normal>k__BackingField').value.field('x').value,.1);
assert.deepEqual(adapter.snapshot(s,'HairFront','t/g').strands[0].points[0].point,[5,6,7]);
adapter.clone(s,'HairFront','t/g');assert.equal(commands[1].name,'CloneBrushHairGroupCommand');
active=false;
assert.throws(()=>adapter.move(s,'t/g','t/g/s',0,{point:[9,9,9]}),/OWNERSHIP/);
assert.equal(commands.length,2);active=true;
adapter.end(s);assert.equal(pins,0);
for(const unavailable of ['complete','active']){
    complete=unavailable!=='complete';active=unavailable!=='active';const t=adapter.begin(a);
    assert.throws(()=>adapter.snapshot(t,'HairFront','t/g'),/OWNERSHIP/);adapter.end(t);
}
complete=active=true;type='AlienHairGroupPath';const t=adapter.begin(a);
assert.equal(adapter.list(t,'HairFront')[0].type,'unknown');adapter.end(t);
assert.equal(pins,0);console.log('Native group queries, concrete paths, ownership, full boxed point and history commands passed');
screen='VRoid.Studio.TextureEditorScreen.ViewModel';
assert.throws(()=>adapter.begin(a),/ORDINARY_EDIT_SCREEN_REQUIRED/);
assert.equal(pins,0);
