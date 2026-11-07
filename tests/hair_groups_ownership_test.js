const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
vm.runInThisContext(fs.readFileSync('agent/hair_groups.js','utf8'));
global.Il2Cpp={string:v=>({handle:v})};
function fixture(){
    let owner='owner',ownerResource='original',pins=0,peak=0,inventory=0,lists=0,editor=0,commands=0,wrongChild=false,leafLookups=0,ownerLookups=0;
    const groups=[{t:'t',g:'g',strands:[{part:'a',id:'s',points:[[2,3,4],[4,5,6]]}]},
        {t:'sibling',g:'hidden',strands:[{part:'b',id:'s',points:[[0,0,0],[1,1,1]]}]}];
    const o=(methods={},fields={},name='Fixture')=>{const r={class:{type:{name:'VRoidCore.Common.SpecificTypes.'+name}},
        method:n=>({invoke:(...a)=>{assert(methods[n],n);return methods[n](...a);}}),tryMethod:n=>methods[n]?r.method(n):null,
        field:n=>({get value(){return fields[n];},set value(v){fields[n]=v;}})};r.handle={isNull:()=>false,owner:r};return r;};
    const v=a=>o({},Object.fromEntries(['x','y','z'].slice(0,a.length).map((k,i)=>[k,a[i]])));
    const cp=p=>o({}, {'<Point>k__BackingField':v(p),'<Normal>k__BackingField':v([.1,.2,.3]),'<Uv>k__BackingField':v([.4,.5]),unknown:987});
    const box=value=>{const r=o();r.unbox=()=>value;return r;};
    const read=b=>{const x=b.unbox();return Object.fromEntries([['point','Point',['x','y','z']],['normal','Normal',['x','y','z']],['uv','Uv',['x','y']]]
        .map(([key,f,channels])=>[key,channels.map(k=>x.field('<'+f+'>k__BackingField').value.field(k).value)]));};
    const path=(g,s)=>{const r=o({get_TransferableId:()=>g.t,get_HairGroupId:()=>g.g,
        ...(s?{get_HairGroupletId:()=>s.part,get_HairStrandId:()=>s.id,get_HairGroupPath:()=>path(g)}:{})},{},s?'BrushHairStrandPath':'BrushHairGroupPath');r.native={g,s};return r;};
    const mat=o({get_Type:()=>o({}, {value__:0}),get_SharedHairMaterialId:()=> 'mat',get_TransferableMaterialId:()=>{throw Error('wrong arm');}});
    const guide=o({}, {Position:v([0,0,0]),Rotation:o({}, {x:0,y:0,z:0,w:1}),Scale:v([1,1,1])});
    const dictionary=(rows,leaf)=>{
        rows.tryMethod=name=>({parameters:[{type:{name:'System.String'}}],invoke:arg=>{
            const id=arg.handle;const found=rows.find(([key])=>key===id);
            if(leaf)leafLookups++;else ownerLookups++;
            if(name==='ContainsKey')return !!found;
            assert(found,'exact key');return found[1];
        }});return rows;
    };
    const context=o({get_ActiveModel:()=>o(),GetActiveLeafTransferables:()=>dictionary(groups.map(g=>[g.t,o({get_GroupId:()=>g.t==='t'?owner:'sibling-owner',get_Type:()=> 'front-type'})]),true),
        GetActiveLeafTransferableGroups:()=>dictionary(['owner','sibling-owner','other-active'].map(id=>[id,o()]),false),
        GetActiveTransferableGroupInfo:()=>o({get_Type:()=> 'owner-type',get_Revision:()=> 'r1',get_ResourceName:()=>ownerResource}),
        ExecuteSyncCommand:command=>{commands++;const c=command.owner;if(c.name==='MoveBrushHairStrandControlPointCommand'){
            const [p,i,value]=c.args;assert.equal(value.owner.field('unknown').value,987);p.owner.native.s.points[i]=read({unbox:()=>value.owner}).point;
        }}});
    const main=o({get_GlobalBus:()=>o({get_ScreenNavigation:()=>o({get_ActiveScreen:()=>({class:{type:{name:'VRoid.Studio.EditRootScreen.ViewModel'}}})})})});
    const m={token:'fresh',context,main};
    const query={GetHairGroupListQuery:a=>{lists++;return groups.filter(g=>g.t===a[0]).map(g=>path(g));},
        GetHairGroupChildrenQuery:a=>{const {g}=a[0].owner.native;return g.strands.map(s=>path(wrongChild?groups[1]:g,s));},
        GetHairStrandControlPointCountQuery:a=>box(o({}, {m_value:a[0].owner.native.s.points.length})),
        GetHairStrandControlPointQuery:a=>box(cp(a[0].owner.native.s.points[a[1]])),
        GetBrushHairGroupParameterSetQuery:()=>o({get_HairMaterialReference:()=>mat}),GetBrushHairStrandParameterSetQuery:()=>o({get_HairMaterialReference:()=>mat}),
        GetGuideOriginTransformQuery:()=>box(guide)};
    const adapter=createHairGroupNative({model:()=>m,text:x=>x,groupHelpers:{prop:(x,k)=>x.method('get_'+k).invoke(),sequence:x=>x},
        helpers:{hairCategoryBindings:()=>[{category:'HairFront',types:['front-type']}],hairDesignEditor:()=>{editor++;throw Error('must not select visible editor');},hairNodeList:()=>[],seq:x=>x,boxArgument:(_,x)=>x,readPoint:read},
        inventory:()=>{inventory++;return {membership_complete:true,groups:['owner','sibling-owner','other-active'].map(id=>({id,type:'owner-type',resource_name:'original',revision:'r1',active:true}))};},
        retain:()=>{pins++;peak=Math.max(peak,pins);return {free(){pins--;}};},cls:(_,n)=>({alloc:()=>{const r=o();r.name=n.split('.').pop();return r;}}),
        invokeManaged(x,n,a=[]){if(n==='.ctor'){x.args=a;return;}if(n==='Execute')return query[x.name](x.args);return x.method(n).invoke(...a);},state:{frame:9}});
    return {adapter,groups,changeOwner:()=>owner='other-active',changeResource:()=>ownerResource='replaced',wrongChild:()=>wrongChild=true,count:()=>({pins,peak,inventory,lists,editor,commands,leafLookups,ownerLookups})};
}
const args={expected_model:'fresh',category:'HairFront',scope:'t/g'};
{
    const f=fixture(),s=f.adapter.begin(args),rows=f.adapter.list(s,'HairFront');
    assert.equal(rows.length,2,'discover exact active sibling absent from current editor');
    const g=f.adapter.snapshot(s,'HairFront','t/g');assert.equal(g.owner.id,'owner');assert.equal(g.strands[0].id,'t/g/a/s');
    f.adapter.move(s,g.scope,g.strands[0].id,1,{point:[5,6,7]},()=>{});assert.equal(f.count().inventory,1);
    f.changeOwner();let invoked=0;assert.throws(()=>f.adapter.move(s,g.scope,g.strands[0].id,0,{point:[8,8,8]},()=>invoked++),/OWNERSHIP/);
    assert.equal(invoked,0);assert.equal(f.count().editor,0);f.adapter.end(s);assert.equal(f.count().pins,0);
}
{
    const f=fixture(),s=f.adapter.begin(args);f.wrongChild();assert.throws(()=>f.adapter.snapshot(s,'HairFront','t/g'),/CHILD.*IDENTITY/);f.adapter.end(s);
}
{
    const f=fixture(),s=f.adapter.begin(args),g=f.groups[0];g.strands.push({...g.strands[0],part:'other'});
    assert.equal(new Set(f.adapter.snapshot(s,'HairFront','t/g').strands.map(x=>x.id)).size,2);
    g.strands.push(g.strands[0]);assert.throws(()=>f.adapter.snapshot(s,'HairFront','t/g'),/AMBIGUOUS|DUPLICATE/);f.adapter.end(s);
}
{
    const f=fixture(),api=createHairGroupApi({adapter:f.adapter});
    for(let i=0;i<30;i++)f.groups[0].strands.push({part:'more'+i,id:'s',points:Array.from({length:8},(_,j)=>[j,j,j])});
    assert.equal(api.operations.list_hair_groups(args).groups.length,2);
    assert.equal(f.count().inventory,1);assert.equal(f.count().lists,2,'one group list query per transferable');
    assert(f.count().peak<1200);assert.equal(f.count().pins,0);assert.equal(f.count().editor,0);
}
{
    const f=fixture(),api=createHairGroupApi({adapter:f.adapter});
    for(let i=0;i<20;i++)f.groups.push({t:'extra'+i,g:'g',strands:[{part:'p',id:'s',points:Array.from({length:64},(_,j)=>[j,j,j])}]});
    assert.equal(api.operations.list_hair_groups(args).groups.length,22);
    assert.equal(f.count().lists,22);assert.equal(f.count().inventory,1);
    assert(f.count().peak<1000,'native geometry roots must not accumulate across aggregate groups');
    assert.equal(f.count().pins,0);
}
{
    const f=fixture(),s=f.adapter.begin(args);
    f.groups[0].strands[0].points=Array.from({length:128},(_,i)=>[i,i,i]);
    const g=f.adapter.snapshot(s,'HairFront','t/g');
    for(let i=1;i<128;i++)f.adapter.move(s,g.scope,g.strands[0].id,i,{point:[i*2,i*2,i*2]},()=>{});
    assert.equal(f.count().inventory,1);assert.equal(f.count().leafLookups,127);assert.equal(f.count().ownerLookups,127);
    assert.equal(f.count().lists,2,'point commands must not rediscover all groups');f.adapter.end(s);assert.equal(f.count().pins,0);
}
console.log('Native active siblings, full grouplet identity, original owner and bounded catalog-free work passed');
{
    const f=fixture(),s=f.adapter.begin(args),g=f.adapter.snapshot(s,'HairFront','t/g');f.changeResource();let invoked=0;
    assert.throws(()=>f.adapter.move(s,g.scope,g.strands[0].id,0,{point:[8,8,8]},()=>invoked++),/OWNERSHIP/);
    assert.equal(invoked,0);f.adapter.end(s);
}
