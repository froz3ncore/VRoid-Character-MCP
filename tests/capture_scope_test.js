const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
vm.runInThisContext(fs.readFileSync('agent/capture_scope.js','utf8'));
function fixture(){
 const values={Outline:17,UI:7,UI3D:12,UI3DGizmo:19,BrushPreview:20,MaskAvatarCamera:-1};
 let selected=0,bones=0,needsUpdate=false,owner=true,writes=[];
 const layers={class:{type:{name:'VRoid.UI.LayerConstants'}},method:n=>({invoke:()=>values[n.slice(4)]})};
 const resources={field:()=>({value:layers})};
 const modifier={handle:'modifier',class:{type:{name:'VRoid.Studio.Engine.BuildModifier'}},field:n=>({value:n==='_resources'?resources:{method:()=>({invoke:()=>n==='_selectedHairStrands'?selected:bones})}}),method:()=>({invoke:()=>needsUpdate})};
 const m={token:'token',engine:{handle:'engine',method:()=>({invoke:()=>modifier})},root:{handle:'root'}};
 let mask=0;const camera={method:n=>({invoke(v){if(n==='set_cullingMask'){writes.push(v);mask=v;}else return mask;}})};
 const scope=createCleanCaptureScope({model:()=>owner?m:{...m,root:{handle:'replacement'}}});
 return {scope,m,camera,values,writes,setSelected:v=>selected=v,setBones:v=>bones=v,setOwner:v=>owner=v,setPending:v=>needsUpdate=v};
}
{
 const f=fixture(),proof=f.scope.inspect(f.m);f.scope.apply(f.camera,proof);
 assert(proof.culling_mask&(1<<f.values.Outline),'Outline may carry the actual selected strand');
 for(const name of ['UI','UI3D','UI3DGizmo','BrushPreview'])assert.equal(proof.culling_mask&(1<<f.values[name]),0);
 f.setOwner(false);assert.throws(()=>f.scope.verify(f.m,proof),/OWNER_CHANGED/);assert.equal(f.writes.length,1);
}
{
 const f=fixture();f.setSelected(3);const proof=f.scope.inspect(f.m,{clonedCamera:true});f.scope.apply(f.camera,proof);
 assert.equal(proof.selected_hair_overrides,3);assert(proof.cloned_camera_without_selection_outline);
 assert(proof.culling_mask&(1<<f.values.Outline));assert.doesNotThrow(()=>f.scope.verify(f.m,proof));
 assert.throws(()=>f.scope.inspect(f.m),/photo hair selection/);
}
for(const modify of [f=>f.setSelected(1),f=>f.setBones(1),f=>f.setPending(true)]){
 const f=fixture();modify(f);assert.throws(()=>f.scope.inspect(f.m),/CAPTURE_PRESENTATION/);assert.equal(f.writes.length,0);
}
console.log('native avatar/Outline mask, auxiliary guides, empty modifier proof and no selection/UI writes passed');
