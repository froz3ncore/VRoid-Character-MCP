const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
// Execute the actual import operation with a GC-sensitive managed-path double.
const source=fs.readFileSync('agent/textures.js','utf8');
const operation=source.slice(source.indexOf('  import_texture_layer(args)'),source.indexOf('  close_texture_editor(args)'));
function fixture(boxed=true,failAt=null){
 const held=new Set(),events=[],pathData={transferable:'real',image:'skin'};
 const handle={kind:'struct-data',value:pathData},header={kind:'box-header'};
 const owner={class:{isValueType:boxed},handle:boxed?header:handle,unbox:()=>({handle})};
 const method=fn=>({invoke:fn}),object=fn=>({method:()=>method(fn)});
 let added=false,name='',opacity=0;
 const row={path:{},data:{layer_id:'new',get Name(){return name;},get Opacity(){return opacity;}}};
 const actions={method:()=>method(()=>false)};
 const screen={class:{type:{name:'VRoid.Studio.TextureEditorScreen.ViewModel'}},method:()=>method(()=>({}))};
 const model={token:'model',context:{},main:object(()=>object(()=>object(()=>screen)))};
 const rgba=new Uint8Array([1,2,3,255]);
 const pointer=()=>({value:0,writeU8(){},writeS32(v){this.value=v;},readS32(){return this.value;},
  add(){return this;},writeByteArray(){}});
 let returned=owner;
 const context={Uint8Array,Float32Array,Number,Math,Error,JSON,state:{frame:1},
  identity:()=>model,region:()=>({value:{}}),imagePaths:()=>[returned],pathKey:()=> 'image',
  retain:value=>{held.add(value);return {free(){held.delete(value);}};},
  stringProp:()=> 'Type',nativeFieldOfType:()=>actions,
  layerRows:()=>added?[row]:[],
  Memory:{alloc:pointer},scalar:(_,v)=>{const p=pointer();p.value=v;return p;},
  cls:(_,type)=>({type:{},alloc:()=>({type,handle:{kind:'command'}}),method:methodName=>method((_,v)=>({methodName,v,handle:{methodName,v}}))}),
  core:()=>({}),
  invokeStatic:(_,name,args)=>{
   assert(held.has(owner),'image owner must survive allocations during PNG decoding');
   if(failAt==='decode')throw Error('decode failed');
   args[2].value=1;args[3].value=1;return {handle:rgba};
  },
  invokeManaged:(object,methodName,args)=>{
   if(methodName==='.ctor'){
    assert(held.has(owner));assert(held.has(object),'command must survive construction');
    assert.equal(args[0],handle,'boxed path headers must never be passed as struct data');
    object.image={...args[0].value};events.push('construct');
   }else{
    if(failAt==='execute')throw Error('native execution failed');
    const command=args[0];
    if(command.methodName==='CreateModifyNameCommand')name=command.v.content;
    else if(command.methodName==='CreateModifyOpacityCommand')opacity=command.v;
    else{added=true;events.push('execute');}
   }
  }};
 class ValueType{constructor(memory){this.handle=memory;}}
 if(boxed==='value'){returned=new ValueType(handle);returned.box=()=>owner;}
 context.Il2Cpp={ValueType,string:v=>({content:v}),
  Array:class{constructor(){this.length=4;this.elements={handle:{readByteArray:()=>rgba.buffer}};}},
  corlib:{class:()=>({method:()=>method(()=>({handle:{}}))})},
  array:()=>{assert(held.has(owner));return {object:{},elementSize:16,handle:{},elements:{handle:{writeByteArray(){}}}};}};
 const api=vm.runInNewContext('({'+operation+'})',context);
 return {api,held,events,args:{image_id:'image',opacity:.5,layer_name:'paint',png_base64:'png',width:1,height:1}};
}
for(const boxed of [true,false,'value']){
 const f=fixture(boxed),result=f.api.import_texture_layer(f.args);
 assert.equal(result.history_command_count,3);assert.equal(result.layer.Name,'paint');
 assert.deepEqual(f.events,['construct','execute']);assert.equal(f.held.size,0);
}
for(const phase of ['decode','execute']){
 const f=fixture(true,phase);assert.throws(()=>f.api.import_texture_layer(f.args),/failed/);assert.equal(f.held.size,0);
}
console.log('Native image import: boxed/class ABI, image/command lifetimes and failure cleanup passed');
