const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
vm.runInThisContext(fs.readFileSync('agent/texture_layers.js', 'utf8'));
assert.equal(validateTextureLayerOrder(['a','b','c'], ['a','b','c']), true);
assert.equal(validateTextureLayerOrder(['a','b','c'], ['c','a','b']), false);
for (const order of [null, [], ['a','b'], ['a','a','c'], ['a','b','foreign'], ['a','b','c','d']])
    assert.throws(() => validateTextureLayerOrder(['a','b','c'], order), /COMPLETE_PERMUTATION/);
assert.throws(() => validateTextureLayerOrder([], []), /COMPLETE_PERMUTATION/);
assert.deepEqual(textureLayerMetadata({layer_id:'a',Name:'A',Opacity:1,Visibility:true,
    CompositionMode:'CompositionNormal',state_sha256:'ignored',index:2}),
    {layer_id:'a',Name:'A',Opacity:1,Visibility:true,CompositionMode:'CompositionNormal',AlphaLocked:null});
console.log('Native layer order: complete permutations and stable metadata guards passed');

// A manual change after Python preflight must still be rejected by the native boundary.
const image = {};
const row = {path: {method: () => ({invoke: () => image})}, data: {layer_id:'a',Name:'Manual change',
    Opacity:1,Visibility:true,CompositionMode:'CompositionNormal'}};
const screen = {handle:{isNull:()=>false},class:{type:{name:'VRoid.Studio.TextureEditorScreen.ViewModel'}},
    method: () => ({invoke: () => ({})})};
let hasGroup=false;
const root={method:()=>({invoke:()=>[{method:()=>({invoke:()=> hasGroup?'LayerGroup':'RasterLayer'})}]})};
const m = {token:'model',context:{method:()=>({invoke:()=>({method:()=>({invoke:()=>({method:()=>({invoke:()=>root})})})})})},
    main:{method:()=>({invoke:()=>({method:()=>({invoke:()=>({method:()=>({invoke:()=>screen})})})})})}};
const api = createLayerManagementApi({identity:()=>m,region:()=>({key:'region',value:{}}),
    imagePaths:()=>[image],layerRows:()=>[row],pathKey:()=> 'image',nativeFieldOfType:()=> ({}),
    stringProp:()=> 'Type',seq:x=>x,cls:()=> {throw Error('A native command must not be created');},invokeManaged:()=> {throw Error('No dispatch');}});
global.state={frame:1};
const expected={...row.data,Name:'Before manual change'};
assert.throws(()=>api.operations.rename_texture_layer({layer_id:'a',name:'New',expected_layer:expected}),/STALE_LAYER_METADATA/);
assert.throws(()=>api.operations.delete_texture_layer({layer_id:'missing',expected_layer:expected}),/UNKNOWN_TEXTURE_LAYER/);
assert.throws(()=>api.operations.reorder_texture_layers({image_id:'image',layer_ids:['a'],expected_stack:[expected]}),/STALE_LAYER_STACK/);
const same=api.operations.rename_texture_layer({layer_id:'a',name:row.data.Name,expected_layer:row.data});
assert.equal(same.history_command_count,0);
hasGroup=true;
assert.throws(()=>api.operations.reorder_texture_layers({image_id:'image',layer_ids:['a'],expected_stack:[row.data]}),/NATIVE_LAYER_GROUP_UNSUPPORTED/);
console.log('Native layer preflight: stale edits and nested groups refused; no-op has zero commands');
