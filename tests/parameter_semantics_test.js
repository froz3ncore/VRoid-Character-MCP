// Native-wrapper doubles test binding direction, missing data and inherited field access.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class NativeString{constructor(value){this.value=value;this.handle={isNull:()=>value===null};}}
global.Il2Cpp={String:NativeString};
const str=s=>new NativeString(s);
function object(name,fields={},methods={}){
    return {class:{name},handle:{isNull:()=>false},tryField:n=>n in fields?{value:fields[n]}:undefined,
        tryMethod:n=>n in methods?{invoke:methods[n]}:undefined,
        method(n){if(!(n in methods))throw Error('Missing method '+n);return {invoke:methods[n]};}};
}
const path=key=>object('BoneTransformPath',{},key===null?{}:{get_Key:()=>str(key)});
function parameter(name,fields={}){
    const target=object('LabelClosure',{translationKey:str('Main.ModelEditor.Category.ParameterModel.name.NoseSize')});
    return object(name,{_transferableGroupType:str('Native.Group'),_translateLabel:object('Delegate',{}, {get_Target:()=>target}),...fields});
}
vm.runInThisContext(fs.readFileSync(require('node:path').join(__dirname,'../agent/parameter_semantics.js'),'utf8'));
const metadata=createParameterSemantics({text:v=>v.value});
const combined=metadata(parameter('CombinedBoneTransformParameterViewModel',{_pathNegative:path('negative'),_pathPositive:path('positive')}));
assert.equal(combined.semantic_key,'negative|positive');
assert.deepEqual(combined.semantic_bindings.map(b=>[b.role,b.key]),[['negative','negative'],['positive','positive']]);
assert.equal(combined.translation_key,'Main.ModelEditor.Category.ParameterModel.name.NoseSize');
assert.equal(combined.semantic_group,'Native.Group');
const blend=metadata(parameter('CombinedBlendShapeTransformParameterViewModel',{_negativeBlendShapePath:path('thin'),_positiveBlendShapePath:path('thick')}));
assert.equal(blend.semantic_key,'thin|thick'); // Real build has different field names than combined bones.
const partial=metadata(parameter('CombinedBoneTransformParameterViewModel',{_pathNegative:path('only-one')}));
assert.equal(partial.semantic_key,null);assert.equal(partial.semantic_status,'partial');
const missing=metadata(parameter('BlendShapeTransformParameterViewModel',{_path:path(null)}));
assert.equal(missing.semantic_key,null);assert.equal(missing.semantic_status,'unavailable');
const unsupported=metadata(object('UnknownControl',{Label:str('Do not turn a display name into a binding ID')}));
assert.equal(unsupported.semantic_key,null);assert.equal(unsupported.translation_key,null);
assert.equal(unsupported.semantic_status,'unavailable');
const single=metadata(parameter('BoneTransformParameterViewModel',{_path:path('native')}));
assert.equal(single.semantic_key,'native');assert.equal(single.semantic_kind,'single');
function template(mesh){
    const t=object('TemplatePath',{templateId:str(mesh)});
    t.class.fields=[{name:'templateId',isStatic:false}];
    return object('TemplateBlendShapeTransformPath',{templatePath:t,editableElementPath:path('same-shape-key')});
}
const a=metadata(parameter('BlendShapeTransformParameterViewModel',{_path:template('body-mesh')}));
const b=metadata(parameter('BlendShapeTransformParameterViewModel',{_path:template('sleeve-mesh')}));
assert.equal(a.semantic_key,'same-shape-key');assert.equal(b.semantic_key,'same-shape-key');
assert.notDeepEqual(a.semantic_bindings[0].template,b.semantic_bindings[0].template);
assert.equal(a.semantic_status,'complete'); // Shared meaning does not imply the same write target.
console.log('PARAMETER_SEMANTICS_JS_PASSED');
