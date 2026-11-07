// Match actual managed VM/delegate/accessor shape; labels, item order and values are decoys.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const file=path.join(__dirname,'../agent/hair_procedural.js');
if(fs.existsSync(file))vm.runInThisContext(fs.readFileSync(file,'utf8'));
assert.equal(typeof createProceduralHairBindings,'function','verified native procedural binding adapter missing');
const hash='ed65ebbc1e806db635566347a9022b9577f6b3d373db128ea23f0e862e005296';
const prefix='VRoid.Studio.HairEditor.DesignEditor.HairGroup.ViewModel.ProceduralHairGroupPropertyViewModel';
const pointer=value=>({value,equals:other=>value===other.value,isNull:()=>false});
let serial=0;
function object(type,methods={},fields={}){
    const metadata=Object.fromEntries(Object.keys(methods).map(name=>[name,{virtualAddress:pointer(type+'/'+name)}]));
    const nested=type.includes('/'),ownerType=nested?type.slice(0,type.lastIndexOf('/')):null;
    const o={handle:pointer(++serial),class:{handle:pointer(type),name:nested?type.split('/').pop():type.split('.').pop(),
        declaringClass:nested?{handle:pointer(ownerType)}:null,type:{name:type.replace('/','+')},method:n=>metadata[n]},
        method:n=>({invoke:(...args)=>methods[n](...args)}),field:n=>({value:fields[n]}),tryField:n=>n in fields?{value:fields[n]}:null};
    return o;
}
function fixture(options={}){
    let valid=true;
    const engine=object('Engine'),p=object('Path',{get_TransferableId:()=> 't',get_HairGroupId:()=> 'g'});
    const other=object('Path',{get_TransferableId:()=> 't',get_HairGroupId:()=> 'wrong'});
    const accessor=object(prefix+'/Accessor',{}, {_engine:engine,_proceduralHairGroupPath:options.wrongPath?other:p});
    const closure=object(prefix+'/<>c__DisplayClass7_0',{
        '<CreateGroups>b__7'(){},'<CreateGroups>b__41'(){},'<CreateGroups>b__42'(){},'<CreateGroups>b__51'(){},'<CreateGroups>b__52'(){}
    },{a:accessor});
    const otherClosure=object(prefix+'/<>c__DisplayClass7_0',{}, {a:accessor});
    otherClosure.class=closure.class;
    const delegate=(name)=>object('Delegate',{get_Target:()=>options.nullDecoy&&name==='<CreateGroups>b__7'?null
        :options.differentTargets&&name==='<CreateGroups>b__42'?otherClosure:closure},
        {method_ptr:options.badPointer?pointer('wrong'):closure.class.method(name).virtualAddress});
    let commands=[];
    const item=(integral,decoy=false)=>object('VRoid.Studio.HairEditor.DesignEditor.Parameter.ViewModel.'+(integral?'Int':'Float')+'ParameterViewModel',
        {get_MinValue:()=>integral?2:.01,get_MaxValue:()=>integral?77:3,get_Value:()=>integral?8:.2,
            set_Value:v=>commands.push(v)},
        {_getter:delegate(decoy?'<CreateGroups>b__7':integral?'<CreateGroups>b__51':'<CreateGroups>b__41'),
            _setter:delegate(integral?'<CreateGroups>b__52':'<CreateGroups>b__42'),
            validator:object('Delegate',{Invoke:()=>valid})});
    const items=[item(false,true),item(true),item(false)];
    if(options.duplicate)items.push(item(false));
    const property=object(prefix,{get_Groups:()=>[object('Group',{get_ParameterItems:()=>items})]},
        {_engine:engine,_proceduralHairGroupPath:p});
    const h={assemblySha256:Object.hasOwn(options,'hash')?options.hash:hash,prop:(o,k)=>o.tryField(k)?.value??o.method('get_'+k).invoke(),seq:x=>x,
        text:x=>x,pin:x=>x,invokeManaged:(o,n,args)=>o.method(n).invoke(...args),boxArgument:(_,v)=>v};
    return {bind:()=>createProceduralHairBindings(h)({property,path:p,engine}),commands,invalidate:()=>valid=false};
}
const f=fixture(),controls=f.bind();assert.deepEqual(controls.map(c=>c.key).sort(),['hair_count','length']);
assert.equal(fixture({nullDecoy:true}).bind().length,2);
assert.equal(controls.find(c=>c.key==='hair_count').max,77);
controls.find(c=>c.key==='length').write(.4);assert.deepEqual(f.commands,[.4]);
{
    const f=fixture(),controls=f.bind();f.invalidate();let attempted=0;
    assert.throws(()=>controls.find(c=>c.key==='length').write(.4,()=>attempted++),/NOT_VALID/);
    assert.equal(attempted,0);assert.equal(f.commands.length,0);
}
for(const options of [{hash:'793eb5fcff3093f344ee930fbfa0c0796ed7780ac91c45bdb7ce6bd34d62fd3c'},
    {hash:null},{badPointer:true},{wrongPath:true},{duplicate:true},{differentTargets:true}]){
    const f=fixture(options);assert.throws(f.bind,/PROCEDURAL/);assert.equal(f.commands.length,0);
}
console.log('Exact hash/native delegate pointer/accessor ownership, ranges, ordering and native VM setter passed');
