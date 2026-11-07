// Source-proven advanced sections and commands, mcjo79/vroid-mcp 0dc7d5e, MIT.
// See licenses/mcjo79-0dc7d5e.txt. Concrete layouts are checked from native metadata.
globalThis.walkAdvancedTextureSections=(sections,H)=>{
 for(const section of H.seq(sections)){
  const name=section.class.name;
  if(['TopCategory','ClothingTemplate'].includes(name))walkAdvancedTextureSections(H.prop(section,'childSections'),H);
  else if(['ColorGroup','ColorSubGroup'].includes(name))walkAdvancedTextureSections(H.prop(section,'colors'),H);
  else H.visit(section);
 }
};
globalThis.createAdvancedMaterialsApi=H=>{
 function inventory(m){
  const result=H.groups(m);
  if(result.membership_complete!==true)throw Error('GROUP_MEMBERSHIP_INCOMPLETE');
  return result;
 }
 function discover(m){
  const groups=inventory(m).groups,found=new Map();
  for(const leaf of H.leaves(m)){
   const owner=groups.find(g=>g.id===leaf.group_id&&g.active===true);
   if(!owner||!leaf.type.includes('Hair'))continue;
   for(const id of H.materials(m,leaf.id)){
    const row=found.get(id)||{id,group_ids:[],transferable_ids:[]};
    if(!row.group_ids.includes(owner.id))row.group_ids.push(owner.id);
    if(!row.transferable_ids.includes(leaf.id))row.transferable_ids.push(leaf.id);
    found.set(id,row);
   }
  }
  const global=new Map(),native=new Map();
  for(const material of found.values()){
   const path=H.makePath(material.id),colors=[],textures=[],unknown=[];
   walkAdvancedTextureSections(H.sections(m,path),{...H,visit(section){
    const type=section.class.name;
    if(!['MaterialColor','BaseColor','Texture'].includes(type)){unknown.push(section.class.type.name);return;}
    const label=H.string(H.prop(section,'translationKey'));
    if(type==='MaterialColor'){
     const exactPath=H.prop(section,'materialPath'),key=H.string(H.prop(section,'parameterKey'));
     const binding_id=JSON.stringify(['material',H.pathIdentity(exactPath),key]);
     if(!colors.some(c=>c.binding_id===binding_id)){
      colors.push({key,label,binding_id,material_path:H.pathIdentity(exactPath),value:H.readColor(m,exactPath,key),readback_available:true});
      native.set(material.id+'\0'+key,{path:exactPath,key,binding_id});
     }
    }else if(type==='BaseColor'){
     const id=H.string(H.prop(section,'colorId')),key='base:'+id,binding_id=JSON.stringify(['global_base_color',id]);
     const row={key,label,binding_id,color_id:id,value:null,readback_available:false,
      readback_status:'Exact base-ID readback not established; aggregate HairSetColor is not substituted'};
     if(!colors.some(c=>c.binding_id===binding_id))colors.push(row);
     global.set(id,row);native.set(material.id+'\0'+key,{base:id,key,binding_id});
    }else if(type==='Texture'){
     const image=H.prop(section,'editableImagePath'),data=H.pathData(image),image_id=JSON.stringify(data);
     if(!textures.some(t=>t.image_id===image_id))textures.push({label,image:data,image_id,
      region_id:JSON.stringify(['hair_material',material.id]),native_path:image});
    }else unknown.push(section.class.type.name);
   }});
   Object.assign(material,{colors,textures,unknown_sections:unknown});
  }
  return {materials:[...found.values()],global_base_colors:[...global.values()],native};
 }
 function inspect(args){
  const m=H.identity(args),result=discover(m);
  return {model_token:m.token,materials:result.materials.map(material=>({...material,
   textures:material.textures.map(({native_path,...row})=>row)})),global_base_colors:result.global_base_colors,
   membership_complete:true,frame:H.frame(),scope:'Active shared material section bindings; visible result requires separate inspection'};
 }
 function exactMaterial(m,id){const d=discover(m),material=d.materials.find(r=>r.id===id);
  if(!material)throw Error('ACTIVE_HAIR_MATERIAL_REQUIRED');return {d,material};}
 function setColor(args){
  if(!Array.isArray(args.color)||args.color.length!==4||args.color.some(c=>typeof c!=='number'||!Number.isFinite(c)||c<0||c>1))throw Error('INVALID_COLOR');
  const m=H.identity(args),{d,material}=exactMaterial(m,args.material_id),binding=d.native.get(args.material_id+'\0'+args.key);
  if(!binding)throw Error('EXACT_MATERIAL_COLOR_KEY_REQUIRED');
  if(material.colors.filter(c=>c.key===args.key).length!==1)throw Error('AMBIGUOUS_MATERIAL_COLOR_KEY');
  const isBase=binding.base!==undefined;
  try{
   H.execute(m,isBase?'SetBaseColorCommand':'SetMaterialColorCommand',
    isBase?[binding.base,H.colorValue(args.color)]:[binding.path,binding.key,H.colorValue(args.color)]);
   const after=isBase?null:H.readColor(m,binding.path,binding.key);
   if(after&&after.some((v,i)=>Math.abs(v-args.color[i])>1e-5))throw Error('MATERIAL_COLOR_READBACK_MISMATCH');
   return {model_token:m.token,key:args.key,material_id:args.material_id,binding_id:binding.binding_id,
    requested:args.color,after,readback_available:!isBase,readback_verified:!isBase,
    readback_status:isBase?'Exact base-ID readback unavailable':'Exact GetMaterialColorQuery match',
    history_command_count:1,saved:false,visible_change_verified:false,frame:H.frame()};
  }catch(error){throw Error('LAYER_EDIT_UNCERTAIN: '+error);}
 }
 function beginHair(args){
  const m=H.identity(args);exactMaterial(m,args.material_id);
  try{H.execute(m,'AdvancedEdit.BeginHairMaterialAdvancedEditCommand',[H.makePath(args.material_id),'Layer',true]);}
  catch(error){throw Error('LAYER_EDIT_UNCERTAIN: '+error);}
  return {model_token:m.token,material_id:args.material_id,screen_entered:false,history_command_count:1,frame:H.frame()};
 }
 function beginClothing(args){
  const m=H.identity(args),groups=inventory(m).groups;
  const group=groups.find(g=>g.id===args.group_id&&g.active===true);
  if(!group||group.fingerprint!==args.group_fingerprint)throw Error('ACTIVE_OR_STALE_GROUP');
  const ids=H.leaves(m).filter(t=>t.group_id===group.id).map(t=>t.id);
  if(!ids.length)throw Error('NO_ACTIVE_TRANSFERABLES');
  try{H.execute(m,'AdvancedEdit.BeginClothingAdvancedEditCommand',[ids,group.id,'Layer']);}
  catch(error){throw Error('LAYER_EDIT_UNCERTAIN: '+error);}
  return {model_token:m.token,group_id:group.id,screen_entered:false,transferables:ids.length,history_command_count:1,frame:H.frame()};
 }
 function imagePaths(m,region){
  const match=typeof region==='string'?JSON.parse(region):region;
  if(!Array.isArray(match)||match.length!==2||match[0]!=='hair_material')throw Error('INVALID_MATERIAL_REGION');
  return exactMaterial(m,match[1]).material.textures.map(t=>t.native_path);
 }
 return {inspect,setColor,beginHair,beginClothing,imagePaths};
};
