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
const hairSelector = object({set_SelectedCategory() {}});
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
    categories: () => [object({get_TranslationKey: () => 'Native.HairSet'})],
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
