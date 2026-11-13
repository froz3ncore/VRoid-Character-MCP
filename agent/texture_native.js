// Native ABI adapters for source-proven texture/material commands.
// mcjo79/vroid-mcp 0dc7d5e, MIT; licenses/mcjo79-0dc7d5e.txt.
globalThis.createNativeTextureExtensions=H=>{
 const {identity,region,layerRows,pathData,cls,core,text,invokeManaged,invokeStatic,scalar,seq}=H;
 const property=(o,key)=>H.groupApi().helpers.prop(o,key);
 const nativeSeq=o=>H.groupApi().helpers.sequence(o);
 function advancedQuery(m,name,args){
  // Imports in the reference do not disambiguate section namespaces. Resolve
  // only declared VRoidCore query metadata; never guess a concrete namespace.
  const matches=Il2Cpp.domain.assembly('VRoidCore').image.classes.filter(c=>c.name===name&&c.type.name.startsWith('VRoidCore.Editing.Query.'));
  if(matches.length!==1)throw Error('UNSUPPORTED_OR_AMBIGUOUS_QUERY: '+name);
  const query=matches[0].alloc();invokeManaged(query,'.ctor',args);
  return invokeManaged(query,'Execute',[m.context.method('get_ActiveModel').invoke().handle]);
 }
 function executeSource(m,name,values){
  const held=[];
  try{
   const args=values.map(value=>{
    if(Array.isArray(value)){
     const list=Il2Cpp.corlib.class('System.Collections.Generic.List`1').inflate(Il2Cpp.corlib.class('System.String')).new();held.push(retain(list));
     for(const id of value)invokeManaged(list,'Add',[Il2Cpp.string(id).handle]);return list.handle;
    }
    if(typeof value==='string')return Il2Cpp.string(value).handle;
    if(typeof value==='boolean'){const p=Memory.alloc(1);p.writeU8(value?1:0);return p;}
    if(value.handle){held.push(retain(value instanceof Il2Cpp.ValueType?value.box():value));return value.handle;}
    throw Error('UNSUPPORTED_NATIVE_SOURCE_ARGUMENT');
   });
   const command=cls('VRoidCore','VRoidCore.Editing.History.Command.'+name).alloc();held.push(retain(command));
   invokeManaged(command,'.ctor',args);invokeManaged(m.context,'ExecuteSyncCommand',[command.handle]);
  }finally{for(const handle of held.reverse())handle.free();}
 }
 const materialApi=createAdvancedMaterialsApi({identity,groups:m=>H.groupApi().operations.list_groups({expected_model:m.token}),
  leaves:m=>nativeSeq(m.context.method('GetActiveLeafTransferables').invoke()).map(p=>{
   const value=property(p,'Value');return {id:text(property(p,'Key')),group_id:text(property(value,'GroupId')),type:text(property(value,'Type'))||''};}),
  materials:(m,id)=>nativeSeq(advancedQuery(m,'GetAllMaterialsQuery',[Il2Cpp.string(id).handle])).map(p=>text(property(p,'SharedHairMaterialId'))),
  makePath:id=>{const p=cls('VRoidCore','VRoidCore.Common.SpecificTypes.SharedHairMaterialPath').alloc();invokeManaged(p,'.ctor',[Il2Cpp.string(id).handle]);return p;},
  sections:(m,path)=>property(advancedQuery(m,'GetHairMaterialQuery',[path.handle]),'sections'),prop:property,seq:nativeSeq,string:text,pathData,
  pathIdentity:p=>{const id=text(property(p,'SharedHairMaterialId'));
   if(!id)throw Error('EXACT_SHARED_MATERIAL_PATH_ID_UNAVAILABLE');return JSON.stringify([p.class.type.name,id]);},
  readColor:(m,path,key)=>{const v=advancedQuery(m,'GetMaterialColorQuery',[path.handle,Il2Cpp.string(key).handle]);return ['r','g','b','a'].map(k=>v.field(k).value);},
  execute:executeSource,colorValue:channels=>{const p=Memory.alloc(16);channels.forEach((v,i)=>p.add(i*4).writeFloat(v));return new Il2Cpp.ValueType(p,core('Color').type);},frame:()=>state.frame});
 function rasterSnapshot(m,row){
  const texture=row.raw.method('CreateTexture2D').invoke();
  try{
   const width=texture.method('get_width').invoke(),height=texture.method('get_height').invoke(),bytes=row.raw.method('ComposeTiles',0).invoke();
   if(bytes.length!==width*height*4||width*height>4194304)throw Error('LAYER_PIXEL_COUNT_MISMATCH');
   const rgba=new Uint8Array(bytes.elements.handle.readByteArray(bytes.length)),yes=Memory.alloc(1);yes.writeU8(1);
   const png=invokeStatic(cls('VRoidCore','VRoidCore.Common.PNGUtil'),'SavePNGFromRGBABytes',[bytes.handle,yes,scalar('int',width),scalar('int',height)]);
   return {width,height,rgba,base64:Il2Cpp.corlib.class('System.Convert').method('ToBase64String').overload('System.Byte[]').invoke(png).content};
  }finally{core('Object').method('DestroyImmediate',1).invoke(texture);}
 }
 function base64Bytes(value){
  if(typeof value!=='string'||value.length>24*1024*1024)throw Error('INVALID_BOUNDED_BASE64');
  return Il2Cpp.corlib.class('System.Convert').method('FromBase64String').invoke(Il2Cpp.string(value));
 }
 const rasterApi=createRasterReplacementApi({identity,locate:(m,args)=>{
  const r=region(m,args.region_id);
  if(!r.shared_material){const inventory=H.groupApi().operations.list_groups({expected_model:m.token});
   if(!inventory.membership_complete||!inventory.groups.some(g=>g.id===r.key&&g.active===true))throw Error('ACTIVE_GROUP_MEMBERSHIP_REQUIRED');}
  const rows=layerRows(m,r).filter(row=>JSON.stringify(row.data.image)===args.image_id),row=rows.find(row=>row.data.layer_id===args.layer_id);
  if(!row)throw Error('EXACT_IMAGE_IDENTITY_REQUIRED');return {region_id:r.key,row,rows};
 },snapshot:rasterSnapshot,requireFlat:(m,row)=>{
  const image=row.path.method('get_EditableImagePath').invoke(),root=m.context.method('get_ActiveModel').invoke().method('GetEditableImage').invoke(image).method('get_RootLayerGroup').invoke();
  if(seq(root.method('get_Children').invoke()).some(child=>String(child.method('get_LayerTreeType').invoke())!=='RasterLayer'))throw Error('NATIVE_LAYER_GROUP_UNSUPPORTED');
 },decodeRgba:value=>{const bytes=base64Bytes(value);return new Uint8Array(bytes.elements.handle.readByteArray(bytes.length));},
 decode:value=>{
  const bytes=base64Bytes(value),yes=Memory.alloc(1);yes.writeU8(1);const w=scalar('int',0),h=scalar('int',0);
  const decoded=invokeStatic(cls('VRoidCore','VRoidCore.Common.PNGUtil'),'LoadPNGToRGBABytes',[bytes.handle,yes,w,h]),hold=retain(decoded);
  try{const rgba=new Il2Cpp.Array(decoded.handle),width=w.readS32(),height=h.readS32();
   if(width<1||height<1||width>4096||height>4096||width*height>4194304||rgba.length!==width*height*4)throw Error('PNG_DIMENSION_MISMATCH');
   return {width,height,rgba:new Uint8Array(rgba.elements.handle.readByteArray(rgba.length))};
  }finally{hold.free();}
 },execute:(m,row,rgba,width,height)=>{
  const pixels=Il2Cpp.array(core('Color'),width*height),pixelsHold=retain(pixels.object),floats=new Float32Array(rgba.length);let commandHold=null;
  try{
   if(pixels.elementSize!==16)throw Error('UNEXPECTED_COLOR_ARRAY_LAYOUT');
   for(let i=0;i<rgba.length;i++)floats[i]=rgba[i]/255;pixels.elements.handle.writeByteArray(floats.buffer);
   const size=Memory.alloc(8);size.writeS32(width);size.add(4).writeS32(height);
   const command=cls('VRoidCore','VRoidCore.Editing.History.Command.LoadImageToEditableImageRasterLayerCommand').alloc();commandHold=retain(command);
   invokeManaged(command,'.ctor',[row.path.handle,size,pixels.handle]);invokeManaged(m.context,'ExecuteSyncCommand',[command.handle]);
  }finally{if(commandHold)commandHold.free();pixelsHold.free();}
 },frame:()=>state.frame});
 return {materialApi,rasterApi,rasterSnapshot};
};
