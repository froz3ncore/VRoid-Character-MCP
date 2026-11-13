// Direct raster history boundary, separate from canvas navigation.
globalThis.createRasterReplacementApi=H=>{
 const same=(a,b)=>a.length===b.length&&a.every((v,i)=>v===b[i]);
 const stack=rows=>JSON.stringify(rows.map(r=>textureLayerMetadata(r.data)));
 return {driver:H,replace(args){
  const m=H.identity(args),{region_id,row,rows}=H.locate(m,args);
  if(row.data.layer_id!==args.layer_id||JSON.stringify(row.data.image)!==args.image_id)
   throw Error('IMAGE_IDENTITY_MISMATCH');
  const hold=H.retainRow?.(row);
  try{
  H.requireFlat(m,row);
  if(stack(rows)!==stack((args.expected_stack||[]).map(data=>({data})))
   ||JSON.stringify(textureLayerMetadata(row.data))!==JSON.stringify(textureLayerMetadata(args.expected_layer||{})))
   throw Error('STALE_LAYER_STACK');
  const input=H.decode(args.png_base64),expected=H.decodeRgba?H.decodeRgba(args.expected_rgba_base64,args.width,args.height):H.decode(args.expected_rgba_base64).rgba;
  const before=H.snapshot(m,row);
  if(input.width!==args.width||input.height!==args.height||before.width!==input.width||before.height!==input.height
   ||input.rgba.length!==input.width*input.height*4)throw Error('PNG_DIMENSION_MISMATCH');
  if(!same(before.rgba,expected))throw Error('STALE_LAYER_CONTENT');
  const beforeStack=stack(rows);
  const unchanged=same(before.rgba,input.rgba);
  let after=before;
  if(!unchanged){
   try{
    H.execute(m,row,input.rgba,input.width,input.height);
    const fresh=H.locate(H.identity(args),args);
    if(stack(fresh.rows)!==beforeStack)throw Error('NONPIXEL_STATE_READBACK_MISMATCH');
    after=H.snapshot(m,fresh.row);
    if(after.width!==input.width||after.height!==input.height||!same(after.rgba,input.rgba))
     throw Error('PIXEL_READBACK_MISMATCH');
   }catch(error){throw Error('LAYER_EDIT_UNCERTAIN: '+error);}
  }
  const clean=s=>({width:s.width,height:s.height,base64:s.base64});
  return {model_token:m.token,region_id,layer:row.data,before:clean(before),after:clean(after),
   history_command_count:Number(!unchanged),changed:!unchanged,preserved_nonpixel_state:true,saved:false,frame:H.frame()};
  }finally{hold?.free();}
 }};
};
