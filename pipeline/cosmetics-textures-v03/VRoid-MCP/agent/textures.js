// Native texture addressing. No caller-supplied managed code or method names.
globalThis.createMakeupEyePose=(api,closure)=>{
 if(closure===null||closure===undefined)return null;
 if(!Number.isFinite(closure)||closure<0||closure>1)throw Error('INVALID_EYE_CLOSURE');
 const names=['Fcl_EYE_Close','Fcl_EYE_Close_L','Fcl_EYE_Close_R'],shapes=api.shapes.filter(s=>names.includes(s.name));
 if(names.some(name=>shapes.filter(s=>s.name===name).length>1))throw Error('AMBIGUOUS_EYE_CLOSE_SHAPES');
 const combined=shapes.find(s=>s.name===names[0]),sides=names.slice(1).map(name=>shapes.find(s=>s.name===name));
 const active=combined&&!api.preferSides?[combined]:sides;
 if(active.some(s=>!s)||shapes.some(s=>!Number.isInteger(s.index)||s.index<0||!Number.isFinite(s.last_frame_weight)||s.last_frame_weight<=0))throw Error('UNSUPPORTED_NATIVE_EYE_CLOSE_SHAPES');
 const before=shapes.map(s=>({...s,weight:api.getWeight(s.index)}));if(before.some(s=>!Number.isFinite(s.weight)))throw Error('INVALID_NATIVE_SHAPE_WEIGHT');
 const metadata={closure,temporary_render_only:true,selected_shapes:active.map(s=>s.name),before:before.map(s=>({index:s.index,name:s.name,weight:s.weight})),restored:false};
 function restore(){for(const s of before)api.setWeight(s.index,s.weight);if(before.some(s=>Math.abs(api.getWeight(s.index)-s.weight)>1e-5))throw Error('EYE_POSE_RESTORE_READBACK_MISMATCH');metadata.restored=true;}
 try{for(const s of shapes)api.setWeight(s.index,active.includes(s)?s.last_frame_weight*closure:0);
  metadata.applied=shapes.map(s=>({index:s.index,name:s.name,weight:api.getWeight(s.index)}));
  if(shapes.some(s=>Math.abs(api.getWeight(s.index)-(active.includes(s)?s.last_frame_weight*closure:0))>1e-5))throw Error('EYE_POSE_APPLY_READBACK_MISMATCH');
 }
 catch(error){restore();throw error;}
 return {metadata,restore};
};
globalThis.createTextureApi=H=>{
 const {model,cls,core,text,invokeManaged}=H;
 const guideTasks=new Map();
 const detailQuality=createCaptureQuality({core,cls,invokeManaged});
 function readableTexture(source){
  const width=source.method('get_width').invoke(),height=source.method('get_height').invoke();
  if(width*height>4194304)throw Error('GUIDE_SIZE_EXCEEDS_LIMIT');
  const rtType=core('RenderTexture'),rt=rtType.method('GetTemporary',3).invoke(width,height,0),old=rtType.method('get_active').invoke();let texture=null;
  try{
   cls('UnityEngine.CoreModule','UnityEngine.Graphics').method('Blit').overload('UnityEngine.Texture','UnityEngine.RenderTexture').invoke(source,rt);rtType.method('set_active').invoke(rt);
   texture=core('Texture2D').alloc();invokeManaged(texture,'.ctor',[scalar('int',width),scalar('int',height)]);
   const p=Memory.alloc(16);[0,0,width,height].forEach((v,i)=>p.add(i*4).writeFloat(v));
   invokeManaged(texture,'ReadPixels',[p,scalar('int',0),scalar('int',0)]);invokeManaged(texture,'Apply',[]);
   const result=texture;texture=null;return result;
  }finally{rtType.method('set_active').invoke(old);rtType.method('ReleaseTemporary').invoke(rt);if(texture)core('Object').method('DestroyImmediate',1).invoke(texture);}
 }
 function pngOfTexture(source){
  const texture=readableTexture(source);
  try{const bytes=cls('UnityEngine.ImageConversionModule','UnityEngine.ImageConversion').method('EncodeToPNG',1).invoke(texture);
   return {width:texture.method('get_width').invoke(),height:texture.method('get_height').invoke(),base64:Il2Cpp.corlib.class('System.Convert').method('ToBase64String').overload('System.Byte[]').invoke(bytes).content};
  }finally{core('Object').method('DestroyImmediate',1).invoke(texture);}
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
 function nativeFieldOfType(object,type){
  let c=object.class;const fields=[];
  for(let depth=0;c&&depth<5;depth++,c=c.parent)for(const f of c.fields)if(!f.isStatic&&f.type.name===type)fields.push(f.name);
  if(fields.length!==1)throw Error('AMBIGUOUS_NATIVE_FIELD: '+type+' '+fields.join(','));return object.field(fields[0]).value;
 }
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
  export_renderer_texture(args){const m=identity(args),name=args.mesh_name,slot=args.material_slot;
   if(!['Face','Body','Hand','Foot'].includes(name)||!Number.isInteger(slot)||slot<0||slot>15)throw Error('INVALID_NATIVE_TEXTURE_TARGET');
   const origin=m.face.method('GetFaceSMR').invoke().method('get_transform').invoke().method('get_parent').invoke(),found=[];
   if(text(origin.method('get_name').invoke())!=='CurrentModelOrigin')throw Error('UNEXPECTED_AVATAR_ROOT');
   function walk(t,depth){if(depth>32)throw Error('AVATAR_DEPTH_LIMIT');if(text(t.method('get_name').invoke())===name){const r=t.method('get_gameObject').invoke().method('GetComponent',1).overload('System.Type').invoke(core('SkinnedMeshRenderer').type.object);if(!r.handle.isNull())found.push(r);}for(let i=0;i<t.method('get_childCount').invoke();i++)walk(t.method('GetChild').invoke(i),depth+1);}
   walk(origin,0);if(found.length!==1)throw Error('AMBIGUOUS_NATIVE_RENDERER');const materials=[...found[0].method('get_sharedMaterials').invoke()];
   if(slot>=materials.length||materials[slot].handle.isNull())throw Error('MISSING_MATERIAL_SLOT');const material=materials[slot],texture=material.method('GetTexture',1).overload('System.String').invoke(Il2Cpp.string('_MainTex'));
   if(texture.handle.isNull())throw Error('MISSING_MAIN_TEXTURE');
   return {model_token:m.token,mesh_name:name,material_slot:slot,material_name:text(material.method('get_name').invoke()),texture_instance_id:texture.method('GetInstanceID').invoke(),...pngOfTexture(texture),frame:state.frame,scope:'Actual renderer main texture; may be a generated atlas. This does not establish an editable-image UV transform.'};
  },
  capture_texture_detail(args){const m=identity(args),target=args.target,direction=args.direction,radius=args.radius_m,size=args.size;
   if(!Array.isArray(target)||target.length!==3||!target.every(Number.isFinite)||target.some(v=>Math.abs(v)>20)||!Array.isArray(direction)||direction.length!==3||!direction.every(Number.isFinite)||!Number.isFinite(radius)||radius<.005||radius>.3||!Number.isInteger(size)||size<256||size>1024)throw Error('INVALID_TEXTURE_DETAIL_CAMERA');
   const norm=Math.hypot(...direction);if(norm<1e-9)throw Error('ZERO_CAMERA_DIRECTION');const dir=direction.map(v=>v/norm);
   if(m.root.field('obsoleteLegacyPhotoBoothViewModel').value.method('get_IsActive').invoke())throw Error('RETURN_TO_EDIT_MODE_FIRST');
   const vector=(v)=>{const p=Memory.alloc(12);v.forEach((n,i)=>p.add(4*i).writeFloat(n));return new Il2Cpp.ValueType(p,core('Vector3').type);};
   const rtClass=core('RenderTexture'),old=rtClass.method('get_active').invoke();let go=null,capture=null,eyePose=null,poseMesh=null,poseGo=null,poseSource=null,poseSourceEnabled=null;
   try{
    if(args.eye_closure!==undefined&&args.eye_closure!==null){
     const face=m.face.method('GetFaceSMR').invoke(),mesh=face.method('get_sharedMesh').invoke(),shapes=[];
     for(let i=0;i<mesh.method('get_blendShapeCount').invoke();i++){const name=text(mesh.method('GetBlendShapeName').invoke(i));if(!['Fcl_EYE_Close','Fcl_EYE_Close_L','Fcl_EYE_Close_R'].includes(name))continue;const count=mesh.method('GetBlendShapeFrameCount').invoke(i);shapes.push({index:i,name,last_frame_weight:count?mesh.method('GetBlendShapeFrameWeight').invoke(i,count-1):null});}
     poseMesh=core('Mesh').alloc();poseMesh.method('.ctor').invoke();face.method('BakeMesh',1).invoke(poseMesh);
     const original=[...poseMesh.method('get_vertices').invoke()].map(v=>['x','y','z'].map(k=>v.field(k).value));
     const adapter={shapes,getWeight:i=>face.method('GetBlendShapeWeight').invoke(i),setWeight:(i,v)=>face.method('SetBlendShapeWeight').invoke(i,v)};
     function changed(){face.method('BakeMesh',1).invoke(poseMesh);const positions=[...poseMesh.method('get_vertices').invoke()];if(positions.length!==original.length)throw Error('EYE_POSE_VERTEX_COUNT_CHANGED');let maximum=0;for(let i=0;i<positions.length;i++)maximum=Math.max(maximum,Math.hypot(...['x','y','z'].map((k,j)=>positions[i].field(k).value-original[i][j])));return maximum;}
     eyePose=createMakeupEyePose(adapter,args.eye_closure);let delta=changed();
     if(args.eye_closure>0&&delta<1e-8){eyePose.restore();eyePose=null;eyePose=createMakeupEyePose({...adapter,preferSides:true},args.eye_closure);delta=changed();}
     if(args.eye_closure>0&&delta<1e-8)throw Error('NATIVE_EYE_SHAPES_DO_NOT_DEFORM_THIS_RENDERER');
     eyePose.metadata.baked_vertex_max_change_m=delta;eyePose.metadata.source_renderer_enabled=face.method('get_enabled').invoke();
     // Camera.Render reuses the frame's skinned GPU buffers. Render the actual BakeMesh result
     // through a temporary static renderer so a same-frame shape change is visible.
     if(poseMesh.method('get_subMeshCount').invoke()!==mesh.method('get_subMeshCount').invoke())throw Error('BAKED_FACE_SUBMESH_MISMATCH');
     if(poseMesh.method('get_uv').invoke().length!==original.length)poseMesh.method('set_uv').invoke(mesh.method('get_uv').invoke());
     poseGo=core('GameObject').alloc();poseGo.method('.ctor',1).invoke(Il2Cpp.string('MCP baked face detail pose'));
     poseGo.method('set_layer').invoke(face.method('get_gameObject').invoke().method('get_layer').invoke());
     poseGo.method('get_transform').invoke().method('SetParent').overload('UnityEngine.Transform','System.Boolean').invoke(face.method('get_transform').invoke(),false);
     poseGo.method('AddComponent',1).invoke(core('MeshFilter').type.object).method('set_sharedMesh').invoke(poseMesh);
     poseGo.method('AddComponent',1).invoke(core('MeshRenderer').type.object).method('set_sharedMaterials').invoke(face.method('get_sharedMaterials').invoke());
     poseSource=face;poseSourceEnabled=face.method('get_enabled').invoke();face.method('set_enabled').invoke(false);
     eyePose.metadata.render_path='Temporary static renderer of actual native BakeMesh, original materials/transform/layer; original renderer restored';
    }
    const source=m.main.method('get_GlobalBus').invoke().method('get_Common3D').invoke().method('get_AvatarCamera').invoke().field('_body').value.field('_templateCamera').value.method('get_PrimaryCamera').invoke();
    go=core('GameObject').alloc();go.method('.ctor',1).invoke(Il2Cpp.string('MCP texture detail capture'));
    const camera=go.method('AddComponent',1).invoke(core('Camera').type.object);camera.method('CopyFrom').invoke(source);camera.method('set_enabled').invoke(false);
    capture=detailQuality.begin(size,'high');camera.method('set_allowMSAA').invoke(true);camera.method('set_targetTexture').invoke(capture.target);camera.method('set_orthographic').invoke(true);camera.method('set_orthographicSize').invoke(radius);camera.method('set_nearClipPlane').invoke(.001);camera.method('set_farClipPlane').invoke(20);
    const transform=camera.method('get_transform').invoke(),position=target.map((v,i)=>v+dir[i]*radius*4);transform.method('set_position').invoke(vector(position));
    transform.method('LookAt').overload('UnityEngine.Vector3','UnityEngine.Vector3').invoke(vector(target),vector(Math.abs(dir[1])>.95?[0,0,1]:[0,1,0]));
    camera.method('Render').invoke();return {model_token:m.token,width:size,height:size,target,direction:dir,radius_m:radius,quality:capture.metadata,base64:capture.encode(),eye_pose:eyePose?eyePose.metadata:null,frame:state.frame};
   }finally{try{if(eyePose)eyePose.restore();}finally{try{if(poseSource)poseSource.method('set_enabled').invoke(poseSourceEnabled);}finally{rtClass.method('set_active').invoke(old);if(go)core('Object').method('DestroyImmediate',1).invoke(go);if(poseGo)core('Object').method('DestroyImmediate',1).invoke(poseGo);if(capture)capture.dispose();if(poseMesh)core('Object').method('DestroyImmediate',1).invoke(poseMesh);}}}
  },
  inspect_texture_renderers(args){const m=identity(args),origin=m.face.method('GetFaceSMR').invoke().method('get_transform').invoke().method('get_parent').invoke(),renderers=[];
   if(text(origin.method('get_name').invoke())!=='CurrentModelOrigin')throw Error('UNEXPECTED_AVATAR_ROOT');
   function vec(v){return ['x','y'].map(k=>v.field(k).value);}
   function walk(t,path,depth){
    if(depth>32)throw Error('AVATAR_DEPTH_LIMIT');const name=text(t.method('get_name').invoke()),here=path+'/'+name;
    if(['Body','Hand','Foot','Face'].includes(name)){
     const renderer=t.method('get_gameObject').invoke().method('GetComponent',1).overload('System.Type').invoke(core('SkinnedMeshRenderer').type.object);
     if(!renderer.handle.isNull()){
      const mesh=renderer.method('get_sharedMesh').invoke(),materials=[...renderer.method('get_sharedMaterials').invoke()].map((material,slot)=>{
       if(material.handle.isNull())return {slot,missing:true};
       const textures=[...material.method('GetTexturePropertyNames').invoke()].map(p=>{const property=new Il2Cpp.String(p.handle).content,texture=material.method('GetTexture',1).overload('System.String').invoke(Il2Cpp.string(property));
        if(texture.handle.isNull())return {property,texture:null};
        return {property,instance_id:texture.method('GetInstanceID').invoke(),name:text(texture.method('get_name').invoke()),width:texture.method('get_width').invoke(),height:texture.method('get_height').invoke(),offset:vec(material.method('GetTextureOffset',1).overload('System.String').invoke(Il2Cpp.string(property))),scale:vec(material.method('GetTextureScale',1).overload('System.String').invoke(Il2Cpp.string(property)))};
       });return {slot,instance_id:material.method('GetInstanceID').invoke(),name:text(material.method('get_name').invoke()),shader:text(material.method('get_shader').invoke().method('get_name').invoke()),textures};
      });const submesh_count=mesh.method('get_subMeshCount').invoke(),submesh_triangle_counts=Array.from({length:submesh_count},(_,i)=>[...mesh.method('GetTriangles',1).invoke(i)].length/3);
      const blend_shapes=name==='Face'?Array.from({length:mesh.method('get_blendShapeCount').invoke()},(_,i)=>{const count=mesh.method('GetBlendShapeFrameCount').invoke(i);return {index:i,name:text(mesh.method('GetBlendShapeName').invoke(i)),weight:renderer.method('GetBlendShapeWeight').invoke(i),frame_count:count,last_frame_weight:count?mesh.method('GetBlendShapeFrameWeight').invoke(i,count-1):null};}):undefined;
      renderers.push({name,path:here,vertex_count:mesh.method('get_vertexCount').invoke(),submesh_count,submesh_triangle_counts,materials,...(blend_shapes?{blend_shapes}:{})});
     }
    }
    for(let i=0;i<t.method('get_childCount').invoke();i++)walk(t.method('GetChild').invoke(i),here,depth+1);
   }walk(origin,'',0);
   return {model_token:m.token,renderers,frame:state.frame,scope:'Actual native renderer/material/texture identities and UV transforms; does not infer semantic nail masks'};
  },
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
   const screen=m.main.method('get_GlobalBus').invoke().method('get_ScreenNavigation').invoke().method('get_ActiveScreen').invoke();
   if(screen.class.type.name!=='VRoid.Studio.TextureEditorScreen.ViewModel')throw Error('OPEN_MATCHING_TEXTURE_EDITOR_FIRST');
   const editor=screen.method('get_TextureEditor').invoke();if(stringProp(editor,'CurrentTransferableGroupType')!==stringProp(r.value,'TypeId'))throw Error('TEXTURE_EDITOR_REGION_MISMATCH');
   const actions=nativeFieldOfType(editor,'VRoid.Studio.TextureEditor.ActionHandler');
   if(!Number.isFinite(args.opacity)||args.opacity<0||args.opacity>1||typeof args.layer_name!=='string'||!args.layer_name.length||args.layer_name.length>80)throw Error('INVALID_LAYER_SETTINGS');
   const before=layerRows(m,r).map(x=>x.data.layer_id),bytes=Il2Cpp.corlib.class('System.Convert').method('FromBase64String').invoke(Il2Cpp.string(args.png_base64));
   const no=Memory.alloc(1);no.writeU8(0);
   const widthOut=scalar('int',0),heightOut=scalar('int',0),yes=Memory.alloc(1);yes.writeU8(1);
   const decoded=invokeStatic(cls('VRoidCore','VRoidCore.Common.PNGUtil'),'LoadPNGToRGBABytes',[bytes.handle,yes,widthOut,heightOut]),decodedHold=retain(decoded);let pixelsHold=null;
   try{
    const width=widthOut.readS32(),height=heightOut.readS32();
    if(width!==args.width||height!==args.height||width*height>4194304)throw Error('PNG_DIMENSION_MISMATCH');
    const rgba=new Il2Cpp.Array(decoded.handle);if(rgba.length!==width*height*4)throw Error('DECODED_PIXEL_COUNT_MISMATCH');
    const channels=new Uint8Array(rgba.elements.handle.readByteArray(rgba.length)),floats=new Float32Array(channels.length);
    for(let i=0;i<channels.length;i++)floats[i]=channels[i]/255;
    const pixels=Il2Cpp.array(core('Color'),width*height);pixelsHold=retain(pixels.object);if(pixels.elementSize!==16)throw Error('UNEXPECTED_COLOR_ARRAY_LAYOUT');pixels.elements.handle.writeByteArray(floats.buffer);
    const sizeClass=cls('VRoidCore','VRoidCore.Draw.TiledBitmap.BitmapSize'),memory=Memory.alloc(8);memory.writeS32(width);memory.add(4).writeS32(height);
    const size=new Il2Cpp.ValueType(memory,sizeClass.type);
    const command=cls('VRoidCore','VRoidCore.Editing.History.Command.LoadImageAsNewRasterLayerCommand').alloc();
    invokeManaged(command,'.ctor',[image.handle,size.handle,pixels.handle]);invokeManaged(m.context,'ExecuteSyncCommand',[command.handle]);
    const added=layerRows(m,r).filter(x=>!before.includes(x.data.layer_id));if(added.length!==1)throw Error('UNCERTAIN_LAYER_IMPORT: inspect before further writes');
    const row=added[0],handler=cls('VRoid.Studio','VRoid.Studio.TextureEditor.ActionHandler');
    const nameCmd=handler.method('CreateModifyNameCommand').invoke(row.path,Il2Cpp.string(args.layer_name));invokeManaged(m.context,'ExecuteSyncCommand',[nameCmd.handle]);
    const opacityCmd=cls('VRoid.Studio','VRoid.Studio.TextureEditor.Layer.ViewModel.RasterLayerViewModel').method('CreateModifyOpacityCommand').invoke(row.path,args.opacity);invokeManaged(m.context,'ExecuteSyncCommand',[opacityCmd.handle]);
    // Ensure the new overlay is at the top, preserving the relative order of existing layers.
    let moves=0;while(actions.method('CanMoveUpLayer').invoke(row.path)){
     if(moves>=128)throw Error('UNCERTAIN_LAYER_ORDER: inspect before further writes');
     actions.method('MoveUpLayer').invoke(row.path);moves++;
    }
    const after=layerRows(m,r).find(x=>x.data.layer_id===row.data.layer_id).data;
    if(after.Name!==args.layer_name||Math.abs(after.Opacity-args.opacity)>1e-6)throw Error('LAYER_METADATA_READBACK_MISMATCH');
    return {model_token:m.token,region_id:r.key,layer:after,width,height,history_command_count:3+moves,promoted_to_top:true,layer_move_commands:moves,frame:state.frame};
   }finally{if(pixelsHold)pixelsHold.free();decodedHold.free();}
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
   const bake=Memory.alloc(1);bake.writeU8(args.bake_colors?1:0);const optional=Memory.alloc(2);optional.writeByteArray(args.bake_colors?[1,1]:[0,0]);
   invokeManaged(m.root,'MoveToTextureEditorScreen',[bake,NULL,Il2Cpp.string(type).handle,optional,NULL]);
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
   try{const width=texture.method('get_width').invoke(),height=texture.method('get_height').invoke(),rgba=row.raw.method('ComposeTiles',0).invoke(),yes=Memory.alloc(1);yes.writeU8(1);
    if(rgba.length!==width*height*4||width*height>4194304)throw Error('LAYER_PIXEL_COUNT_MISMATCH');
    const bytes=invokeStatic(cls('VRoidCore','VRoidCore.Common.PNGUtil'),'SavePNGFromRGBABytes',[rgba.handle,yes,scalar('int',width),scalar('int',height)]);
    return {model_token:m.token,region_id:r.key,layer:row.data,width,height,base64:Il2Cpp.corlib.class('System.Convert').method('ToBase64String').overload('System.Byte[]').invoke(bytes).content};
   }finally{core('Object').method('DestroyImmediate',1).invoke(texture);}
  }
 }};
};
