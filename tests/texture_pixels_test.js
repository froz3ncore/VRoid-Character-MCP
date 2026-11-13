const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
vm.runInThisContext(fs.readFileSync('agent/texture_layers.js','utf8'));
vm.runInThisContext(fs.readFileSync('agent/texture_pixels.js','utf8'));
function setup(){
 let bytes=[1,2,3,4],metadata={layer_id:'["t","i","n"]',Name:'Kept',Opacity:.5,Visibility:false,CompositionMode:'Normal'},commands=[],undo=[],redo=[];
 const image={transferable_id:'t',image_id:'i'},row={data:{...metadata,image}},model={token:'m'};
 const H={identity:a=>{if(a.expected_model!=='m')throw Error('STALE_MODEL');return model;},
  locate:()=>({region_id:'r',row,rows:[row]}),snapshot:()=>({width:1,height:1,rgba:[...bytes],base64:'actual'}),
  requireFlat:()=>{},execute:(m,r,p)=>{commands.push('LoadImageToEditableImageRasterLayerCommand');undo.push([...bytes]);redo=[];bytes=[...p];},
  decode:s=>s==='input'?{width:1,height:1,rgba:[9,8,7,4]}:{width:1,height:1,rgba:[1,2,3,4]},
  frame:()=>2};
 const api=createRasterReplacementApi(H),args={expected_model:'m',region_id:'r',image_id:JSON.stringify(image),
  layer_id:metadata.layer_id,expected_layer:metadata,expected_stack:[metadata],expected_rgba_base64:'old',png_base64:'input',width:1,height:1};
 return {api,args,commands,change:()=>bytes[0]++,rename:()=>row.data.Name='Changed',row,get bytes(){return bytes;},
  undo(){commands.push('UndoAsync');redo.push([...bytes]);bytes=undo.pop();},
  redo(){commands.push('RedoAsync');undo.push([...bytes]);bytes=redo.pop();}};
}
let s=setup();s.change();assert.throws(()=>s.api.replace(s.args),/STALE_LAYER_CONTENT/);assert.equal(s.commands.length,0);
s=setup();s.rename();assert.throws(()=>s.api.replace(s.args),/STALE_LAYER_STACK/);assert.equal(s.commands.length,0);
s=setup();assert.throws(()=>s.api.replace({...s.args,image_id:'foreign'}),/IMAGE_IDENTITY/);
assert.throws(()=>s.api.replace({...s.args,expected_model:'wrong'}),/STALE_MODEL/);
assert.throws(()=>s.api.replace({...s.args,width:2}),/DIMENSION/);assert.equal(s.commands.length,0);
s=setup();const out=s.api.replace(s.args);assert.deepEqual(s.bytes,[9,8,7,4]);assert.equal(out.history_command_count,1);
assert.deepEqual(s.commands,['LoadImageToEditableImageRasterLayerCommand']);assert.equal(out.preserved_nonpixel_state,true);
assert.equal(out.after.base64,'actual');assert.equal(s.row.data.Name,'Kept');
s.undo();assert.deepEqual(s.bytes,[1,2,3,4]);assert.equal(s.row.data.Name,'Kept');
s.redo();assert.deepEqual(s.bytes,[9,8,7,4]);
assert.deepEqual(s.commands,['LoadImageToEditableImageRasterLayerCommand','UndoAsync','RedoAsync']);
s=setup();s.api=createRasterReplacementApi({...s.api.driver,execute:()=>{throw Error('partial');}});
assert.throws(()=>s.api.replace(s.args),/LAYER_EDIT_UNCERTAIN/);
s=setup();s.api=createRasterReplacementApi({...s.api.driver,execute:()=>{s.rename();}});
assert.throws(()=>s.api.replace(s.args),/NONPIXEL_STATE_READBACK_MISMATCH/);
s=setup();s.api=createRasterReplacementApi({...s.api.driver,execute:()=>{}});
assert.throws(()=>s.api.replace(s.args),/PIXEL_READBACK_MISMATCH/);
console.log('Raster boundary: exact identity, metadata/content/dimensions, one history command and uncertain dispatch passed');
