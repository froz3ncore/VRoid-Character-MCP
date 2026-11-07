const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
vm.runInThisContext(fs.readFileSync('agent/advanced_materials.js','utf8'));
const node=(type,data)=>({class:{name:type,type:{name:type}},...data});
const image={transferable_id:'t',image_id:'i'},path={id:'mat'},material=node('MaterialColor',{materialPath:path,parameterKey:'Tint',translationKey:'tint'});
const sections=[node('TopCategory',{childSections:[node('ColorGroup',{colors:[material,
 node('BaseColor',{colorId:'global',translationKey:'base'}),node('BaseColor',{colorId:'global',translationKey:'duplicate'})]}),
 node('Texture',{editableImagePath:image,translationKey:'texture'})]})];
const visited=[];
walkAdvancedTextureSections(sections,{prop:(o,k)=>o[k],seq:x=>x,visit:s=>visited.push(s.class.name)});
assert.deepEqual(visited,['MaterialColor','BaseColor','BaseColor','Texture']);
const color=[.2,.3,.4,1];let active=true,complete=true,writes=[],nativeColor=[0,0,0,1];
const api=createAdvancedMaterialsApi({identity:a=>{if(a.expected_model!=='m')throw Error('STALE_MODEL');return {token:'m'};},
 groups:()=>({membership_complete:complete,groups:[{id:'r',active,type:'Hair.Front',fingerprint:'f'}]}),
 leaves:()=>[{id:'t',group_id:'r',type:'Hair'}],materials:()=>['mat'],makePath:id=>({id}),
 sections:()=>sections,prop:(o,k)=>o[k],seq:x=>x,string:x=>x,pathData:x=>x,
 pathIdentity:p=>p.id,readColor:()=>nativeColor,execute:(m,name,args)=>{writes.push([name,args]);nativeColor=[...color];},
 colorValue:c=>c,frame:()=>3});
let result=api.inspect({expected_model:'m'});assert.equal(result.materials.length,1);
assert.deepEqual(result.materials[0].group_ids,['r']);assert.equal(result.materials[0].colors.length,2);
assert.equal(result.global_base_colors.length,1);assert.equal(result.materials[0].colors[1].value,null);
assert.equal(result.materials[0].textures[0].region_id,'["hair_material","mat"]');
api.setColor({expected_model:'m',material_id:'mat',key:'Tint',color});
assert.equal(writes[0][0],'SetMaterialColorCommand');assert.strictEqual(writes[0][1][0],path);
result=api.setColor({expected_model:'m',material_id:'mat',key:'base:global',color});
assert.equal(result.readback_available,false);assert.equal(writes[1][0],'SetBaseColorCommand');
assert.throws(()=>api.setColor({expected_model:'m',material_id:'mat',key:'Missing',color}),/COLOR_KEY/);
sections[0].childSections[0].colors.push(node('MaterialColor',{materialPath:{id:'other'},parameterKey:'Tint',translationKey:'ambiguous'}));
const count=writes.length;
assert.throws(()=>api.setColor({expected_model:'m',material_id:'mat',key:'Tint',color}),/AMBIGUOUS/);
assert.equal(writes.length,count);sections[0].childSections[0].colors.pop();
complete=false;assert.throws(()=>api.inspect({expected_model:'m'}),/MEMBERSHIP/);
complete=true;active=false;assert.throws(()=>api.beginHair({expected_model:'m',material_id:'mat'}),/ACTIVE_HAIR/);
active=true;result=api.beginHair({expected_model:'m',material_id:'mat'});
assert.equal(result.screen_entered,false);assert.equal(writes.at(-1)[0],'AdvancedEdit.BeginHairMaterialAdvancedEditCommand');
assert.deepEqual(writes.at(-1)[1].slice(1),['Layer',true]);
result=api.beginClothing({expected_model:'m',group_id:'r',group_fingerprint:'f'});
assert.equal(result.screen_entered,false);assert.equal(writes.at(-1)[0],'AdvancedEdit.BeginClothingAdvancedEditCommand');
assert.deepEqual(writes.at(-1)[1],[['t'],'r','Layer']);
assert.throws(()=>api.beginClothing({expected_model:'m',group_id:'r',group_fingerprint:'stale'}),/STALE_GROUP/);
console.log('Advanced materials: active ownership, nested exact channels, global deduplication, path-preserving commands and conversion passed');
