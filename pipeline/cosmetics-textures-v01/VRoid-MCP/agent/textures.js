// Native texture addressing. No caller-supplied managed code or method names.
globalThis.createTextureApi=H=>{
 const {model,cls,core,text,invokeManaged}=H;
 const guideTasks=new Map();
 function pngOfTexture(source){
  const width=source.method('get_width').invoke(),height=source.method('get_height').invoke();
  if(width*height>4194304)throw Error('GUIDE_SIZE_EXCEEDS_LIMIT');
  const rtType=core('RenderTexture'),rt=rtType.method('GetTemporary',3).invoke(width,height,0),old=rtType.method('get_active').invoke();let texture=null;
  try{
   cls('UnityEngine.CoreModule','UnityEngine.Graphics').method('Blit').overload('UnityEngine.Texture','UnityEngine.RenderTexture').invoke(source,rt);rtType.method('set_active').invoke(rt);
   texture=core('Texture2D').alloc();invokeManaged(texture,'.ctor',[scalar('int',width),scalar('int',height)]);
   const p=Memory.alloc(16);[0,0,width,height].forEach((v,i)=>p.add(i*4).writeFloat(v));
   invokeManaged(texture,'ReadPixels',[p,scalar('int',0),scalar('int',0)]);invokeManaged(texture,'Apply',[]);
   const bytes=cls('UnityEngine.ImageConversionModule','UnityEngine.ImageConversion').method('EncodeToPNG',1).invoke(texture);
   return {width,height,base64:Il2Cpp.corlib.class('System.Convert').method('ToBase64String').overload('System.Byte[]').invoke(bytes).content};
  }finally{rtType.method('set_active').invoke(old);rtType.method('ReleaseTemporary').invoke(rt);if(texture)core('Object').method('DestroyImmediate',1).invoke(texture);}
 }
 function invokeStatic(c,name,args){
  const call=new NativeFunction(Il2Cpp.module.getExportByName('il2cpp_runtime_invoke'),'pointer',['pointer','pointer','pointer','pointer'],{exceptions:'propagate'}),ex=Memory.alloc(Process.pointerSize);ex.writePointer(NULL);
  const argv=Memory.alloc(Math.max(1,args.length)*Process.pointerSize);args.forEach((a,i)=>argv.add(i*Process.pointerSize).writePointer(a));
  const result=call(c.method(name,args.length).handle,NULL,argv,ex);
  if(!ex.readPointer().isNull())throw Error('MANAGED_TEXTURE_ERROR: '+new Il2Cpp.Object(ex.readPointer()).method('ToString').invoke().content);
  return new Il2Cpp.Object(result);
 }
 function seq(o){
  if(!o||o.handle.isNull())return [];
  if(o instanceof Il2Cpp.Array)return [...o];
  const it=o.method('GetEnumerator').invoke(),rows=[];
  const getter=it.tryMethod('get_Current')||it.class.methods.find(m=>m.name.endsWith('.get_Current')&&m.parameters.length===0);
  if(!getter)throw Error('UNSUPPORTED_NATIVE_ENUMERATOR');
  try{while(it.method('MoveNext').invoke())rows.push(it.method(getter.name).invoke());}
  finally{if(it.tryMethod('Dispose'))it.method('Dispose').invoke();}return rows;
 }
 const pairs=o=>seq(o).map(e=>({key:text(e.method('get_Key').invoke()),value:e.method('get_Value').invoke()}));
 function identity(args){if(!args.expected_model)throw Error('EXPECTED_MODEL_REQUIRED');return model(args.expected_model);}
 function q(m,name,args){const query=cls('VRoidCore','VRoidCore.Editing.Query.'+name).alloc();invokeManaged(query,'.ctor',args);return invokeManaged(query,'Execute',[m.context.method('get_ActiveModel').invoke().handle]);}
 const stringProp=(o,p)=>{const v=invokeManaged(o instanceof Il2Cpp.ValueType?o.box():o,'get_'+p);return v.handle.isNull()?null:new Il2Cpp.String(v.handle).content;};
 function pathData(p){return {transferable_id:stringProp(p,'TransferableId'),image_id:stringProp(p,'ImageId')};}
 const pathKey=p=>JSON.stringify(pathData(p));
 function scalar(type,value){const p=Memory.alloc(4);type==='float'?p.writeFloat(value):p.writeS32(value);return p;}
 function groups(m){return pairs(m.context.method('get_ActiveModel').invoke().method('get_TransferableGroups').invoke());}
 function region(m,id){const r=groups(m).find(r=>r.key===id);if(!r)throw Error('UNKNOWN_TEXTURE_REGION');return r;}
 function imagePaths(m,r){
  const active=m.context.method('get_ActiveModel').invoke();
  const ids=[...new Set(seq(active.method('GetAllTransferableIdsInTransferableGroup').invoke(Il2Cpp.string(r.key))).map(s=>new Il2Cpp.String(s.handle).content))],images=[];
  for(const id of ids)for(const p of seq(q(m,'GetEditableImagePathsForTransferableQuery',[Il2Cpp.string(id).handle])))
   if(!images.some(i=>pathKey(i)===pathKey(p)))images.push(p);
  return images;
 }
 function layerRows(m,r){
  const rows=[];
  for(const image of imagePaths(m,r))for(const p of seq(q(m,'GetEditableImageRasterLayersQuery',[image.handle]))){
   const raw=m.context.method('get_ActiveModel').invoke().method('GetEditableImageRasterLayer').invoke(p);
   const params=q(m,'GetEditableImageLayerTreeParameterSetQuery',[p.handle]);
   const description={};for(const key of ['Name','Opacity','Visibility','CompositionMode','AlphaLocked']){
    const meth=params.tryMethod('get_'+key);if(meth){const v=meth.invoke();description[key]=typeof v==='object'?(v instanceof Il2Cpp.String?text(v):String(v)):v;}
   }
   rows.push({path:p,raw,data:{layer_id:JSON.stringify([pathData(image).transferable_id,pathData(image).image_id,stringProp(p,'NodeId')]),image:pathData(image),node_id:stringProp(p,'NodeId'),...description}});
  }return rows;
 }
 return {operations:{
  export_texture_surface(args){const m=identity(args),screen=m.main.method('get_GlobalBus').invoke().method('get_ScreenNavigation').invoke().method('get_ActiveScreen').invoke();
   if(screen.class.type.name!=='VRoid.Studio.TextureEditorScreen.ViewModel')throw Error('TEXTURE_EDITOR_NOT_ACTIVE');
   const editor=screen.method('get_TextureEditor').invoke(),meshes=[];
   for(const o of seq(editor.field('_meshOverlays').value)){
    const image=pathData(o.method('get_EditableImagePath').invoke()),mesh=o.method('get_Mesh').invoke().method('ToResolvedShallow').invoke(Il2Cpp.string(image.transferable_id));
    const positions=[...mesh.method('get_Vertices').invoke()].map(p=>['x','y','z'].map(k=>p.field(k).value)),uv=[...mesh.method('get_UV').invoke()].map(p=>['x','y'].map(k=>p.field(k).value));
    if(positions.length!==uv.length||positions.length>100000)throw Error('UNEXPECTED_OVERLAY_VERTEX_UV_COUNT');
    const submeshes=seq(mesh.method('get_Submeshes').invoke()).map(s=>{
     const getters=['get_Triangles','get_TriangleIndices','get_Indices'].filter(n=>s.tryMethod(n));if(getters.length!==1)throw Error('UNSUPPORTED_NATIVE_SUBMESH: '+s.class.methods.map(m=>m.name).join(','));
     const indices=[...s.method(getters[0]).invoke()];if(indices.length%3||indices.some(i=>i<0||i>=positions.length))throw Error('INVALID_OVERLAY_INDICES');
     return {triangles:indices};
    });
    const weights=[...mesh.method('get_BoneWeights').invoke()].map(v=>{const keys=new Set(v.type.class.fields.map(f=>f.name));const field=k=>v.field(keys.has(k)?k:'m_'+k[0].toUpperCase()+k.slice(1)).value;return {indices:[0,1,2,3].map(i=>field('boneIndex'+i)),weights:[0,1,2,3].map(i=>field('weight'+i))};});
    const bone_ids=[...mesh.method('get_BoneNames').invoke()].map(v=>{
     if(v instanceof Il2Cpp.String)return {name:v.content};
     const fields=[];let c=v.class;for(let i=0;c&&i<4;i++,c=c.parent)for(const f of c.fields.filter(f=>!f.isStatic&&f.type.name==='System.String'))fields.push({name:f.name,value:text(v.field(f.name).value)});
     return {native_type:v.class.type.name,identity:text(v.method('ToString').invoke()),fields};
    });
    meshes.push({image,positions,uv0:uv,submeshes,bone_ids,weights});
   }
   return {schema:'vroid-native-texture-overlay-v1',model_token:m.token,current_group_type:stringProp(editor,'CurrentTransferableGroupType'),meshes,position_state:'Native texture-editor overlay mesh coordinates; not a world-space or posed rendering assertion',uv_origin:'UV coordinates as returned by the native mesh; Unity +V upward',scope:'Exact mesh/UV/image relationship; no automatic semantic nail mask or final makeup design',frame:state.frame};
  },
  export_texture_guide(args){const m=identity(args),screen=m.main.method('get_GlobalBus').invoke().method('get_ScreenNavigation').invoke().method('get_ActiveScreen').invoke();
   if(screen.class.type.name!=='VRoid.Studio.TextureEditorScreen.ViewModel')throw Error('TEXTURE_EDITOR_NOT_ACTIVE');
   const editor=screen.method('get_TextureEditor').invoke(),guide=editor.method('get_GuideTextureSource').invoke();if(guide.handle.isNull())throw Error('NO_UV_GUIDE');
   const key=m.token+'/'+guide.handle.toString();let record=guideTasks.get(key);
   if(!record){const task=guide.method('Create').invoke();record={task,hold:retain(task)};guideTasks.set(key,record);}
   if(!record.task.method('get_IsCompleted').invoke())return {model_token:m.token,pending:true};
   try{const texture=record.task.method('get_Result').invoke();return {model_token:m.token,pending:false,current_group_type:stringProp(editor,'CurrentTransferableGroupType'),...pngOfTexture(texture)};}
   finally{record.hold.free();guideTasks.delete(key);}
  },
  import_texture_layer(args){const m=identity(args),r=region(m,args.region_id),images=imagePaths(m,r),image=images.find(p=>pathKey(p)===args.image_id);
   if(!image)throw Error('UNKNOWN_EDITABLE_IMAGE');
   if(!Number.isFinite(args.opacity)||args.opacity<0||args.opacity>1||typeof args.layer_name!=='string'||!args.layer_name.length||args.layer_name.length>80)throw Error('INVALID_LAYER_SETTINGS');
   const before=layerRows(m,r).map(x=>x.data.layer_id),bytes=Il2Cpp.corlib.class('System.Convert').method('FromBase64String').invoke(Il2Cpp.string(args.png_base64));
   const no=Memory.alloc(1);no.writeU8(0);
   const texture=invokeStatic(cls('VRoidCore','VRoidCore.Common.PNGUtil'),'LoadPNGToRGBATexture2D',[bytes.handle,no,no,no]);
   try{
    const width=texture.method('get_width').invoke(),height=texture.method('get_height').invoke();
    if(width!==args.width||height!==args.height||width*height>4194304)throw Error('PNG_DIMENSION_MISMATCH');
    const sizeClass=cls('VRoidCore','VRoidCore.Draw.TiledBitmap.BitmapSize'),memory=Memory.alloc(8);memory.writeS32(width);memory.add(4).writeS32(height);
    const size=new Il2Cpp.ValueType(memory,sizeClass.type),pixels=texture.method('GetPixels',0).invoke();
    const command=cls('VRoidCore','VRoidCore.Editing.History.Command.LoadImageAsNewRasterLayerCommand').alloc();
    invokeManaged(command,'.ctor',[image.handle,size.handle,pixels.handle]);invokeManaged(m.context,'ExecuteSyncCommand',[command.handle]);
    const added=layerRows(m,r).filter(x=>!before.includes(x.data.layer_id));if(added.length!==1)throw Error('UNCERTAIN_LAYER_IMPORT: inspect before further writes');
    const row=added[0],handler=cls('VRoid.Studio','VRoid.Studio.TextureEditor.ActionHandler');
    const nameCmd=handler.method('CreateModifyNameCommand').invoke(row.path,Il2Cpp.string(args.layer_name));invokeManaged(m.context,'ExecuteSyncCommand',[nameCmd.handle]);
    const opacityCmd=cls('VRoid.Studio','VRoid.Studio.TextureEditor.Layer.ViewModel.RasterLayerViewModel').method('CreateModifyOpacityCommand').invoke(row.path,args.opacity);invokeManaged(m.context,'ExecuteSyncCommand',[opacityCmd.handle]);
    const after=layerRows(m,r).find(x=>x.data.layer_id===row.data.layer_id).data;
    if(after.Name!==args.layer_name||Math.abs(after.Opacity-args.opacity)>1e-6)throw Error('LAYER_METADATA_READBACK_MISMATCH');
    return {model_token:m.token,region_id:r.key,layer:after,width,height,history_command_count:3,frame:state.frame};
   }finally{core('Object').method('DestroyImmediate',1).invoke(texture);}
  },
  close_texture_editor(args){const m=identity(args),screen=m.main.method('get_GlobalBus').invoke().method('get_ScreenNavigation').invoke().method('get_ActiveScreen').invoke();
   if(screen.class.type.name!=='VRoid.Studio.TextureEditorScreen.ViewModel')throw Error('TEXTURE_EDITOR_NOT_ACTIVE');
   const yes=Memory.alloc(1);yes.writeU8(1);invokeManaged(screen,'Exit',[yes,NULL]);return {model_token:m.token,frame:state.frame};
  },
  open_texture_editor(args){const m=identity(args),r=region(m,args.region_id),type=stringProp(r.value,'TypeId');
   if(!/\.(FaceSkin|BodySkin|Cheek|Lip|Eyelid|Eyeline|Eyelash|Eyebrow|Iris|EyeWhite|EyeHighlight|Mouth|MouthLine|NoseLighting)$/.test(type))throw Error('UNSUPPORTED_TEXTURE_REGION');
   const modeClass=cls('VRoid.Studio','VRoid.Studio.EditRootScreen.EditMode'),modeName=type.endsWith('.BodySkin')?'Body':'Face';
   const modes=modeClass.fields.filter(f=>f.isStatic),matches=modes.filter(f=>f.name.toLowerCase().startsWith(modeName.toLowerCase()));
   const mode=modes.find(f=>f.name===modeName)||(matches.length===1?matches[0]:null);if(!mode)throw Error('UNSUPPORTED_NATIVE_EDIT_MODE: '+modes.map(f=>f.name).join(','));
   const rawMode=mode.value;invokeManaged(m.root,'set_EditMode',[scalar('int',typeof rawMode==='number'?rawMode:rawMode.field('value__').value)]);
   const no=Memory.alloc(1);no.writeU8(0);const optional=Memory.alloc(2);optional.writeByteArray([0,0]);
   invokeManaged(m.root,'MoveToTextureEditorScreen',[no,NULL,Il2Cpp.string(type).handle,optional,NULL]);
   const screen=m.main.method('get_GlobalBus').invoke().method('get_ScreenNavigation').invoke().method('get_ActiveScreen').invoke();
   return {model_token:m.token,region_id:r.key,native_type:type,active_screen:screen.class.type.name,frame:state.frame};
  },
  inspect_texture_canvas(args){const m=identity(args),screen=m.main.method('get_GlobalBus').invoke().method('get_ScreenNavigation').invoke().method('get_ActiveScreen').invoke();
   if(screen.class.type.name!=='VRoid.Studio.TextureEditorScreen.ViewModel')throw Error('TEXTURE_EDITOR_NOT_ACTIVE');
   const editor=screen.method('get_TextureEditor').invoke(),images=[];
   function sections(rows){for(const section of seq(rows)){
    if(section.tryMethod('get_Path')&&section.class.name==='TextureViewModel')images.push({label:stringProp(section,'TranslatedDisplayName'),image:pathData(section.method('get_Path').invoke()),referring_texture_paths:seq(section.method('get_ReferringTexturePaths').invoke()).map(p=>({native_class:p.class.type.name,value:stringProp(p,'TransferableId'),path:text(p.method('ToString').invoke())}))});
    if(section.tryMethod('get_ChildSections'))sections(section.method('get_ChildSections').invoke());
   }}
   for(const sub of seq(editor.field('_subCategories').value))sections(sub.method('get_Sections').invoke());
   const guide=editor.method('get_GuideTextureSource').invoke();
   const selected=editor.method('get_SelectedLayer').invoke();
   const overlays=seq(editor.field('_meshOverlays').value).map(o=>{const mesh=o.method('get_Mesh').invoke(),hierarchy=[];let c=mesh.class;
    for(let i=0;c&&i<4;i++,c=c.parent)hierarchy.push({type:c.type.name,fields:c.fields.map(f=>({name:f.name,type:f.type.name})),methods:c.methods.filter(m=>!m.name.startsWith('<')).map(m=>({name:m.name,return:m.returnType.name,params:m.parameters.map(p=>({name:p.name,type:p.type.name}))}))});
    return {image:pathData(o.method('get_EditableImagePath').invoke()),native_mesh_type:mesh.class.type.name,hierarchy};});
   return {model_token:m.token,current_group_type:stringProp(editor,'CurrentTransferableGroupType'),images,overlays,selected_layer:selected.handle.isNull()?null:{image:pathData(selected.method('get_Path').invoke().method('get_EditableImagePath').invoke()),node_id:stringProp(selected.method('get_Path').invoke(),'NodeId')},guide:guide.handle.isNull()?null:{native_type:guide.class.type.name,methods:guide.class.methods.map(m=>({name:m.name,return:m.returnType.name,params:m.parameters.map(p=>({name:p.name,type:p.type.name}))}))},frame:state.frame};
  },
  list_texture_regions(args){const m=identity(args);return {model_token:m.token,regions:groups(m).map(r=>{
   const type=stringProp(r.value,'TypeId');const bindings=[];
   for(const e of pairs(r.value.method('get_EditableElements').invoke()))
    if(e.value.tryMethod('get_ImageId'))bindings.push({native_key:e.key,image_id:stringProp(e.value,'ImageId'),native_type:e.value.class.type.name});
   return {region_id:r.key,native_type:type,part:type.split('.').pop(),image_bindings:bindings,editable_images:imagePaths(m,r).map(pathData),uv_mapping_status:'not_yet_exported'};
  })};},
  list_texture_layers(args){const m=identity(args),r=region(m,args.region_id);return {model_token:m.token,region_id:r.key,layers:layerRows(m,r).map(x=>x.data)};},
  export_texture_layer(args){const m=identity(args),r=region(m,args.region_id),row=layerRows(m,r).find(l=>l.data.layer_id===args.layer_id);if(!row)throw Error('UNKNOWN_TEXTURE_LAYER');
   const texture=row.raw.method('CreateTexture2D').invoke();
   try{const bytes=cls('UnityEngine.ImageConversionModule','UnityEngine.ImageConversion').method('EncodeToPNG',1).invoke(texture);
    return {model_token:m.token,region_id:r.key,layer:row.data,width:texture.method('get_width').invoke(),height:texture.method('get_height').invoke(),base64:Il2Cpp.corlib.class('System.Convert').method('ToBase64String').overload('System.Byte[]').invoke(bytes).content};
   }finally{core('Object').method('DestroyImmediate',1).invoke(texture);}
  }
 }};
};
