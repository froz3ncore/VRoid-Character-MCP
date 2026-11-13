const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
if(fs.existsSync('agent/build_profiles.js'))vm.runInThisContext(fs.readFileSync('agent/build_profiles.js','utf8'));
if(fs.existsSync('agent/hair_procedural_fallback.js'))vm.runInThisContext(fs.readFileSync('agent/hair_procedural_fallback.js','utf8'));
assert.equal(typeof createProceduralHairFallback,'function','native-owned modifier fallback missing');
const hash='ed65ebbc1e806db635566347a9022b9577f6b3d373db128ea23f0e862e005296';
global.Il2Cpp={string:v=>({handle:v}),delegate:()=>{throw Error('JS-owned delegate forbidden');}};
const setType='VRoidCore.Common.SpecificTypes.ProceduralHairGroupParameterSet';
function fixture(options={}){
    let calls=0,allocations=0,history=[];const pointer=id=>({id,isNull:()=>false,equals:o=>o.id===id});
    const param=name=>({type:{name}});
    const object=()=>{const o={handle:pointer(++allocations),fields:{},field:n=>({get value(){return o.fields[n];},set value(v){o.fields[n]=v;}})};return o;};
    const owner={handle:pointer('owner')};
    function closure(name,method,type){
        const c={name,declaringClass:owner,field:()=>({type:{name:type}}),method:n=>{
            if(n==='.ctor')return {parameters:[]};
            assert.equal(n,method);
            return {handle:pointer(method+'-info'),virtualAddress:pointer(method+'-code'),parameters:[param(setType)],returnType:{name:'System.Void'}};
        },
            alloc:()=>{const o=object();o.class=c;return o;}};return c;
    }
    owner.nestedClasses=[closure('<>c__DisplayClass7_15',options.v216?'<CreateGroups>b__98':'<CreateGroups>b__97','System.Single'),
        closure('<>c__DisplayClass7_20',options.v216?'<CreateGroups>b__103':'<CreateGroups>b__102','System.Int32')];
    const actionClass={method:n=>n==='Invoke'?{parameters:[param(setType)],returnType:{name:'System.Void'}}:
        {parameters:[param('System.Object'),param('System.IntPtr')]},alloc:()=>{const o=object();o.class=actionClass;
            o.method=n=>({invoke:()=>o.target});return o;}};
    const ctor={parameters:[param('System.String'),param('VRoidCore.Common.SpecificTypes.ProceduralHairGroupPath'),
        {type:{name:'System.Action<'+setType+'>',class:actionClass}},param(options.badSignature?'System.Int32':'System.Boolean')]};
    const commandClass={method:()=>ctor,alloc:()=>object()};
    const path=object();
    const api=createProceduralHairFallback({assemblySha256:options.hash??hash,
        cls:(_,name)=>name.includes('History.Command')?commandClass:owner,
        pin:x=>x,boxArgument:(_,v)=>v,boxMethodInfo:m=>m.handle,
        prop:(o,k)=>o.fields[k],validate:()=>{if(options.invalid)throw Error('PATH_INVALID');},
        invokeManaged(o,n,args=[]){
            if(n==='.ctor'&&o.class===actionClass){
                o.target=args[0].nativeObject;
                o.fields.method_ptr=pointer(args[1].id.replace('-info','-code'));return;
            }
            if(n==='.ctor'&&!o.class)o.args=args;
        },execute:command=>{calls++;history.push(command);}});
    const fixObject=o=>{o.handle.nativeObject=o;return o;};
    for(const c of owner.nestedClasses){const alloc=c.alloc;c.alloc=()=>fixObject(alloc());}
    const alloc=actionClass.alloc;actionClass.alloc=()=>fixObject(alloc());
    return {controls:()=>api({path,configured:{length:.2,hair_count:8}}),state:()=>({calls,allocations,history})};
}
{
    const f=fixture(),controls=f.controls();const length=controls.find(c=>c.key==='length');
    assert.equal(length.min,Math.fround(.1));assert.equal(length.max,1);
    let attempted=0;length.write(.1,()=>attempted++);assert.equal(attempted,1);assert.equal(f.state().calls,1);
    const command=f.state().history[0],delegate=command.args[2].nativeObject;
    assert.equal(delegate.target.fields.v,Math.fround(.1));assert.equal(command.args[3],true);
    assert.match(length.range_source,/static/);
}
for(const build of [hash,'3334b166e298682eeda1ca1c5ca568b12f7085b76cc629668fe8b192af816bd8',
    'c8daa116938b40896e3a09208bbde71604a92d5ca6d86f9ff8b89fea3c1a5ad2']){
    const f=fixture({hash:build,v216:build!==hash});
    for(const c of f.controls()){
        assert.throws(()=>c.write(c.key==='length'?2:21),/RANGE/);
        c.write(c.key==='length'?.1:20);
    }
    assert.equal(f.state().calls,2);
    assert.deepEqual(f.state().history.map(command=>[command.args[0],command.args[3]]),
        [['ProceduralLength',true],['HairCount',false]]);
}
for(const options of [{hash:'wrong'},{badSignature:true},{invalid:true}]){
    const f=fixture(options);let attempted=0;
    assert.throws(()=>f.controls().find(c=>c.key==='length').write(.3,()=>attempted++));
    assert.equal(attempted,0);assert.equal(f.state().calls,0);
}
console.log('Native managed modifier/action construction, exact signatures, static UI bounds and zero-JS-delegate fallback passed');
