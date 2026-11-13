// Exercise the composed domain adapter, rather than only its colour helper.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const path = require('node:path');
for (const file of ['color_state.js', 'parameters.js'])
    vm.runInThisContext(fs.readFileSync(path.join(__dirname, '../agent', file), 'utf8'));
class Collection extends Array { get handle() { return {isNull: () => false}; } }
const list = (...items) => new Collection(...items);
const object = (methods = {}, fields = {}) => ({
    handle: {isNull: () => false}, class: {name: 'Fixture'},
    method(name) { if (!methods[name]) throw Error('Missing method ' + name); return {invoke: methods[name]}; },
    tryMethod: name => methods[name] ? {invoke: methods[name]} : null,
    field(name) { if (!(name in fields)) throw Error('Missing field ' + name); return {value: fields[name]}; },
    tryField: name => name in fields ? {value: fields[name]} : null,
});
global.Il2Cpp = {Array: Collection};
global.retain = () => ({free() {}});
global.state = {frame: 1};
global.Memory = {alloc: () => ({value: null, writeFloat(v) {this.value = v;}})};
let number = 0;
const parameter = object({get_ModelValue: () => number, set_ModelValue: buffer => {number = buffer.value;}});
const engine = {};
const color = object({}, {r: .2, g: .3, b: .4, a: 1});
let availabilityRead = false;
const colorModel = object({
    get_TranslationKey: () => 'Native.LeftEye',
    GetIsAvailable: actual => {assert.equal(actual, engine); availabilityRead = true; return true;},
});
const sub = object({get_Color: () => color}, {_model: colorModel});
const selection = object({get_SubColorSelections: () => list(sub)});
const colorView = object({get_ColorSelections: () => list(selection)});
const group = object({get_TransferableGroupType: () => 'Native.FaceSkin'});
const collection = object({}, {_categoryColorSelections: object({get_Values: () => list(group)})});
const faceSelector = object({}, {_categoryColorSelectionCollection: collection});
let selections=0;
const hairSelector = object({set_SelectedCategory() {selections++;}});
let hairCategories=[object({get_TranslationKey: () => 'Native.HairSet'})];
const hair = object({get_HairSetColor: () => color});
const context = {token: 'fresh', engine, root: object({get_Resources: () => object(),
    get_ColorPalette: () => object(), get_HairEditor: () => hair})};
const api = createParameterApi({
    model: token => {assert(!token || token === 'fresh'); return context;},
    cls: () => ({alloc: () => colorView}), text: x => x,
    entries: () => [{p: parameter, canonical: 'height'}],
    details: () => ({id: 'body/WholeBody/002', type: 'float', editable: true, value: number, min: -1, max: 1}),
    parameterMetadata: () => ({}),
    selector: (_, area) => area === 'face' ? faceSelector : hairSelector,
    categories: () => hairCategories,
    invokeManaged: (o, name, args = []) => name === '.ctor' ? undefined : o.method(name).invoke(...args),
});
const colors = api.operations.list_parameters({expected_model: 'fresh', domain: 'colors'});
assert(availabilityRead);
assert.deepEqual(colors.parameters.map(p => p.id), ['colors/FaceSkin/LeftEye', 'colors/Hair/All']);
const written = api.operations.set_parameters({expected_model: 'fresh', domain: 'body',
    changes: [{id: 'body/WholeBody/002', value: .25}]});
assert(written.ok);
assert.equal(number, .25);
assert.equal(written.applied[0].after, .25);
console.log('Composed parameter adapter: colour enumeration and typed write passed');
hairCategories=['HairFront','HairBack'].map((part,i)=>object({get_TranslationKey:()=> 'Native.'+part},
    {_categoryModel:object({}, {transferableGroupType:'native-group-type-'+i})}));
const hairLeaves=list(...[0,1].map(i=>object({get_GroupId:()=> 'owner-'+i,get_Type:()=> 'exact-native-type-'+i})),
    object({get_GroupId:()=> 'unrelated',get_Type:()=> 'body-type'}));
context.context=object({GetActiveLeafTransferables:()=>object({get_Values:()=>hairLeaves}),
    GetActiveTransferableGroupInfo:id=>object({get_Type:()=> id==='unrelated'?'body-group':'native-group-type-'+id.slice(-1)})});
const selectedBefore=selections;
assert.deepEqual(api.hairGroupHelpers.hairCategoryBindings(context),[
    {category:'HairFront',types:['exact-native-type-0']},{category:'HairBack',types:['exact-native-type-1']}]);
assert.equal(selections,selectedBefore,'read-only category binding must not select an editor');
hairCategories.push(object({get_TranslationKey:()=> 'Native.HairAhoge'},
    {_categoryModel:object({}, {transferableGroupType:'absent-native-group'})}));
assert.deepEqual(api.hairGroupHelpers.hairCategoryBindings(context).at(-1),{category:'HairAhoge',types:[]});
const nativeHair={class:{field:()=>({value:['TransferableType.N00.HairFront','TransferableType.N00.HairAhoge']})}};
const nativeCategory=object({}, {_categoryModel:object({}, {transferableGroupType:'TransferableGroupType.N00.Level1.HairAhoge'})});
assert.equal(api.hairGroupHelpers.hairCategoryNativeType(nativeHair,nativeCategory,'HairAhoge',[]),'TransferableType.N00.HairAhoge');
assert.throws(()=>api.hairGroupHelpers.hairCategoryNativeType(nativeHair,nativeCategory,'HairBack',[]),/AMBIGUOUS/);
assert.throws(()=>api.hairGroupHelpers.hairCategoryNativeType(nativeHair,nativeCategory,'HairAhoge',['a','b']),/AMBIGUOUS/);
