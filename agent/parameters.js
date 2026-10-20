// Typed adapters for the native editor parameters.
//
// Each domain maps native view models to a flat list of entries:
//   {data: {id, label, type, value, min, max, ...}, read?, write?}
// The operation layer validates a value against `data` and then either calls the
// entry's own writer or the native setter named by `prop`. No caller-supplied
// method names are ever executed.
globalThis.createParameterApi = H => {
    const { model, cls, core, text, array, invokeManaged, entries, details, value,
            selector, categories, parameterMetadata } = H;

    const cachedRoots = new Map();
    const colorState = createColorState({
        text, seq,
        readBinding(binding) {
            // A fresh single-key accessor only reads the engine: it does not
            // attach a UI view model, execute a command, or assume that the
            // aggregate colour getter behaves uniformly for every element.
            const accessor = cls('VRoid.Studio', 'VRoid.Studio.ColorSelection.Model.EditableElementColorAccessor')
                .method('Create').overload('System.String', 'System.String', 'System.String')
                .invoke(Il2Cpp.string(binding.group), Il2Cpp.string(binding.key), Il2Cpp.string(null));
            const colour = accessor.method('Get', 1).invoke(model().engine);
            return ['r', 'g', 'b', 'a'].map(channel => colour.field(channel).value);
        },
    });

    const lastSegment = value => value.split('.').pop();

    // Native collections come in four shapes: arrays, view models with an
    // `array` field, indexable collections, and plain enumerators.
    function seq(object) {
        if (!object || object.handle.isNull()) return [];
        if (object instanceof Il2Cpp.Array) return [...object];
        if (object.tryField('array')) return array(object);
        if (object.tryMethod('get_Count') && object.tryMethod('get_Item')) {
            const count = object.method('get_Count').invoke();
            return Array.from({ length: count }, (_unused, index) => object.method('get_Item').invoke(index));
        }
        const iterator = object.method('GetEnumerator').invoke();
        const items = [];
        try {
            while (iterator.method('MoveNext').invoke()) items.push(iterator.method('get_Current').invoke());
        } finally {
            if (iterator.tryMethod('Dispose')) iterator.method('Dispose').invoke();
        }
        return items;
    }

    // Native editors are rebuilt when the file changes, so objects created for
    // the current model token are kept alive and reused inside it.
    function cached(m, key, create) {
        const cacheKey = m.token + '/' + key;
        if (!cachedRoots.has(cacheKey)) {
            const object = create();
            cachedRoots.set(cacheKey, { object, hold: retain(object) });
        }
        return cachedRoots.get(cacheKey).object;
    }

    function displayLabel(object, fallback) {
        for (const name of ['TranslatedDisplayName', 'Label', 'Name']) {
            if (object.tryMethod('get_' + name)) return text(object.method('get_' + name).invoke()) || fallback;
        }
        return fallback;
    }

    function readValue(object, prop, type) {
        const raw = object.method('get_' + prop).invoke();
        if (type === 'string') return text(raw);
        if (type === 'curve') {
            return seq(raw.method('get_RawControlPoints').invoke())
                .map(point => [point.field('x').value, point.field('y').value]);
        }
        if (type === 'screen_color') return ['_r', '_g', '_b'].map(key => raw.field(key).value / 255);
        const channels = {
            color: ['r', 'g', 'b', 'a'], vector2: ['x', 'y'], vector3: ['x', 'y', 'z'],
            quaternion: ['x', 'y', 'z', 'w'],
        }[type];
        return channels ? channels.map(key => raw.field(key).value) : raw;
    }

    function boxArgument(type, raw) {
        if (type === 'string') return Il2Cpp.string(raw).handle;
        if (type === 'screen_color') {
            const components = raw.map(component => component * 255);
            return cls('VRoid.UI', 'VRoid.UI.ScreenColor').method('FromRgb').invoke(...components).handle;
        }
        if (type === 'curve') {
            const points = Il2Cpp.array(core('Vector2'), raw.length);
            raw.forEach((pair, index) => {
                const point = Memory.alloc(8);
                point.writeFloat(pair[0]);
                point.add(4).writeFloat(pair[1]);
                points.set(index, new Il2Cpp.ValueType(point, core('Vector2').type));
            });
            const curve = cls('VRoidCore', 'VRoidCore.Common.Types.Curve2').alloc();
            invokeManaged(curve, '.ctor', [points.handle, boxArgument('int', 64), boxArgument('float', .001)]);
            return curve.handle;
        }
        const buffer = Memory.alloc(Array.isArray(raw) ? raw.length * 4 : 4);
        if (Array.isArray(raw)) raw.forEach((component, index) => buffer.add(index * 4).writeFloat(component));
        else if (type === 'bool') buffer.writeU8(raw ? 1 : 0);
        else if (type === 'int' || type === 'enum') buffer.writeS32(raw);
        else buffer.writeFloat(raw);
        return buffer;
    }

    function makeParameter(object, prop, id, type = 'float', extra = {}) {
        return {
            o: object, prop,
            data: { ...parameterMetadata(object), id, label: displayLabel(object, prop), type,
                    value: readValue(object, prop, type), editable: true, ...extra },
        };
    }

    // A model parameter entry (face/body/clothing) reuses the enumeration from
    // operations.js, which already knows how to describe and identify aliases.
    function morphEntry(entry) {
        const described = details(entry);
        return {
            o: entry.p,
            alias: entry.canonical,
            prop: entry.p.tryMethod('get_CombinedValue') ? 'CombinedValue' : 'ModelValue',
            data: { ...described, type: 'float', native_type: described.type },
        };
    }

    function collectColorEntries(viewModel, prefix, out) {
        if (!viewModel || viewModel.handle.isNull()) return;
        for (const selection of seq(viewModel.method('get_ColorSelections').invoke())) {
            for (const sub of seq(selection.method('get_SubColorSelections').invoke())) {
                const colorModel = sub.field('_model').value;
                const key = lastSegment(text(colorModel.method('get_TranslationKey').invoke()));
                out.push(makeParameter(sub, 'Color', prefix + '/' + key, 'color', {
                    category: displayLabel(selection, ''),
                    editable: colorModel.method('GetIsAvailable').invoke(model().engine),
                    min: 0, max: 1,
                    format: 'RGBA floats 0..1; sRGB',
                }));
                const entry = out[out.length - 1];
                entry.colorInfo = colorState.inspect(colorModel);
                entry.data.side = { LeftEye: 'left', RightEye: 'right', BothEyes: 'both' }[key] || null;
                entry.data.side_reference = entry.data.side ? 'native_ui' : null;
            }
        }
    }

    function colorDomain(m) {
        const out = [];
        const collection = selector(m, 'face').field('_categoryColorSelectionCollection').value;
        const groups = seq(collection.field('_categoryColorSelections').value.method('get_Values').invoke());
        for (const group of groups) {
            const key = lastSegment(text(group.method('get_TransferableGroupType').invoke()));
            const viewModel = cached(m, 'color/' + key, () => {
                const created = cls('VRoid.Studio', 'VRoid.Studio.ColorSelection.ViewModel.CategoryColorSelection').alloc();
                invokeManaged(created, '.ctor', [
                    m.root.method('get_Resources').invoke().handle, m.engine.handle, group.handle,
                    m.root.method('get_ColorPalette').invoke().handle,
                ]);
                return created;
            });
            collectColorEntries(viewModel, 'colors/' + key, out);
        }
        const hair = m.root.method('get_HairEditor').invoke();
        selectHairPart(m, 'HairSet');
        out.push(makeParameter(hair, 'HairSetColor', 'colors/Hair/All', 'color',
            { min: 0, max: 1, scope: 'all hair', format: 'RGBA floats 0..1; sRGB' }));
        return colorState.decorate(out);
    }

    const expressionGroups = m => seq(m.face.method('get_ExpressionParameterCategories').invoke());

    function expressionDomain(m, scope) {
        const out = [];
        for (const group of expressionGroups(m)) {
            const id = lastSegment(text(group.method('get_SynthesizedCompatKey').invoke()));
            if (scope && id !== scope) continue;
            seq(group.method('get_ParameterParts').invoke()).forEach((part, partIndex) => {
                seq(part.method('get_Parameters').invoke()).forEach((parameter, index) => {
                    out.push(makeParameter(parameter, 'Value',
                        'expressions/' + id + '/' + partIndex + '/' + index, 'float', {
                            category: displayLabel(group, id), part: displayLabel(part, ''),
                            min: parameter.method('get_MinValue').invoke(),
                            max: parameter.method('get_MaxValue').invoke(),
                        }));
                });
            });
        }
        return out;
    }

    // The general domain has no uniform model API: each editor exposes a fixed
    // set of properties, listed here with the operating range this project uses.
    const GENERAL_LAYOUT = {
        EyeExcursionEditor: { '': ['HorizontalInner', 'HorizontalOuter', 'VerticalUpper', 'VerticalLower'] },
        OutlineParameterEditor: {
            HairParameterSet: ['OutlineWidth'], FaceParameterSet: ['OutlineWidth'],
            BodyParameterSet: ['OutlineWidth'], AccessoryParameterSet: ['OutlineWidth'],
        },
        RimLightEditor: {
            HairParameterSet: ['Strength', 'Compression'], FaceParameterSet: ['Strength', 'Compression'],
            BodyParameterSet: ['Strength', 'Compression'],
        },
        ShadingParameterEditor: {
            FaceParameterSet: ['NormalSmoothing', 'ShadingShift', 'ShadingToony'],
            HairParameterSet: ['ShadingShift', 'ShadingToony'],
            BodyParameterSet: ['ShadingShift', 'ShadingToony'],
        },
        SpringBonePropertyEditor: {
            '': ['ErrorReduction'], ClothingParameterSet: ['Amplitude'],
            AccessoryParameterSet: ['Amplitude'], BodyParameterSet: ['Amplitude'],
        },
    };

    function rangeFor(name) {
        if (name === 'ShadingShift') return [-1, 1];
        if (['ShadingToony', 'NormalSmoothing', 'OutlineWidth'].includes(name)) return [0, 1];
        return [0, 100];
    }

    function generalDomain(m) {
        const general = m.root.method('get_GeneralEditor').invoke();
        const out = [];
        for (const [editorName, sets] of Object.entries(GENERAL_LAYOUT)) {
            const editor = general.method('get_' + editorName).invoke();
            for (const [setName, names] of Object.entries(sets)) {
                for (const name of names) {
                    const target = setName ? editor.method('get_' + setName).invoke() : editor;
                    const [min, max] = rangeFor(name);
                    out.push(makeParameter(target, name,
                        'general/' + editorName + '/' + (setName ? setName + '/' : '') + name,
                        name === 'ErrorReduction' ? 'bool' : 'float',
                        { label: name, category: displayLabel(editor, editorName), min, max,
                          range_source: 'MCP validated operating range' }));
                }
            }
        }
        return out;
    }

    function accessoryFeature(m) {
        const editor = m.root.method('get_AccessoryEditor').invoke();
        // The instance collections only exist while this native feature is active.
        if (!editor.method('get_IsFeatureActive').invoke()) invokeManaged(editor, 'OnEnterFeature');
        return editor;
    }

    const accessoryIdentity = object =>
        text(object.field('transferableInfo').value.method('get_Id').invoke());

    function accessoryItems(m) {
        const editor = accessoryFeature(m);
        const out = [];
        const seen = new Set();
        for (const category of seq(editor.method('get_ShapeParameterCategories').invoke())) {
            invokeManaged(editor, 'set_SelectedShapeParameterCategory', [category.handle]);
            for (const instance of seq(editor.method('get_Instances').invoke())) {
                const id = accessoryIdentity(instance);
                if (seen.has(id)) continue;
                seen.add(id);
                out.push(instance);
            }
        }
        return out;
    }

    function accessoryDomain(m, scope) {
        if (!scope) throw Error('ACCESSORY_SCOPE_REQUIRED: list_accessories first');
        const out = [];
        for (const instance of accessoryItems(m)) {
            const id = accessoryIdentity(instance);
            if (scope && scope !== id) continue;
            const prefix = 'accessories/' + id;
            const editor = accessoryFeature(m);
            const groupType = text(instance.field('transferableInfo').value.method('get_GroupType').invoke());
            const category = seq(editor.method('get_ShapeParameterCategories').invoke())
                .find(item => text(item.method('get_TransferableGroupType').invoke()) === groupType);
            if (category) invokeManaged(editor, 'set_SelectedShapeParameterCategory', [category.handle]);
            invokeManaged(editor, 'set_SelectedInstance', [instance.handle]);

            for (const prop of ['IsVisible', 'IsEditable']) {
                const entry = makeParameter(instance, prop, prefix + '/' + prop, 'bool',
                    { label: prop, category: displayLabel(instance, id) });
                entry.write = checked => invokeManaged(instance,
                    prop === 'IsVisible' ? 'SetVisibility' : 'SetEditability', [boxArgument('bool', checked)]);
                out.push(entry);
            }

            const partOrigin = () => {
                const query = cls('VRoidCore', 'VRoidCore.Editing.Query.GetPartOriginQuery').alloc();
                invokeManaged(query, '.ctor', [Il2Cpp.string(id).handle]);
                const origin = invokeManaged(query, 'Execute',
                    [m.context.method('get_ActiveModel').invoke().handle]);
                return invokeManaged(origin, 'get_Transform').unbox();
            };
            const transforms = [
                ['Scale', 'vector3', ['x', 'y', 'z']],
                ['Position', 'vector3', ['x', 'y', 'z']],
                ['Rotation', 'quaternion', ['x', 'y', 'z', 'w']],
            ];
            for (const [field, type, channels] of transforms) {
                const readTransform = () => {
                    const component = partOrigin().field(field).value;
                    return channels.map(channel => component.field(channel).value);
                };
                out.push({
                    data: { id: prefix + '/PartOriginLocal' + field, label: 'Local ' + field, type,
                            value: readTransform(), editable: true,
                            units: field === 'Position' ? 'meters' : undefined },
                    read: readTransform,
                    write: next => {
                        const transform = partOrigin();
                        const component = transform.field(field).value;
                        channels.forEach((channel, index) => { component.field(channel).value = next[index]; });
                        const command = cls('VRoidCore',
                            'VRoidCore.Editing.History.Command.SetPartOriginTransformCommand').alloc();
                        invokeManaged(command, '.ctor', [Il2Cpp.string(id).handle, transform.handle]);
                        invokeManaged(m.context, 'ExecuteSyncCommand', [command.handle]);
                    },
                });
            }

            const bones = seq(instance.method('get_Bones').invoke());
            if (bones.length) {
                out.push(makeParameter(instance, 'SelectedBoneIndex', prefix + '/bone', 'enum', {
                    options: bones.map((bone, index) => ({ value: index, label: displayLabel(bone, String(index)) })),
                    min: 0, max: bones.length - 1,
                }));
            }
            seq(instance.method('get_Parameters').invoke())
                .forEach((parameter, index) => out.push(morphEntry({ p: parameter, id: prefix + '/shape/' + index,
                    category: displayLabel(instance, id) })));
            // Current accessories expose their shape controls through the
            // instance parameters above; the category's old hard-coded group ids
            // are obsolete, so colours are read from the instance instead.
            collectColorEntries(instance.method('get_CategoryColorSelection').invoke(), prefix + '/colors', out);
        }
        return colorState.decorate(out);
    }

    function validateValue(entry, next) {
        const data = entry.data;
        if (!data.editable) throw Error('PARAMETER_NOT_EDITABLE: ' + data.id);
        if (data.type === 'curve') {
            const valid = Array.isArray(next) && next.length >= 2 && next.length <= 64
                && next.every(point => Array.isArray(point) && point.length === 2
                    && point.every(component => typeof component === 'number'
                        && Number.isFinite(component) && Math.abs(component) <= 10));
            if (!valid) throw Error('CURVE_CONTROL_POINTS: 2..64 finite [x,y] pairs within -10..10');
            return;
        }
        if (data.type === 'bool') {
            if (typeof next !== 'boolean') throw Error('BOOLEAN_REQUIRED: ' + data.id);
            return;
        }
        if (data.type === 'string') {
            if (typeof next !== 'string' || next.length > 128) throw Error('INVALID_STRING');
            return;
        }
        if (['color', 'screen_color', 'vector2', 'vector3', 'quaternion'].includes(data.type)) {
            const width = data.type === 'vector2' ? 2
                : ['vector3', 'screen_color'].includes(data.type) ? 3 : 4;
            if (!Array.isArray(next) || next.length !== width
                || next.some(component => typeof component !== 'number' || !Number.isFinite(component))) {
                throw Error('INVALID_VECTOR: ' + data.id);
            }
            if (['color', 'screen_color'].includes(data.type)
                && next.some(component => component < 0 || component > 1)) {
                throw Error('COLOR_RANGE');
            }
            if (data.type === 'quaternion'
                && Math.abs(next.reduce((sum, component) => sum + component * component, 0) - 1) > .01) {
                throw Error('NORMALIZED_QUATERNION_REQUIRED');
            }
            if ((data.id.endsWith('LocalScale') || data.id.endsWith('/Scale'))
                && next.some(component => component <= 0 || component > 100)) {
                throw Error('SCALE_RANGE: (0,100]');
            }
            if (next.some(component => Math.abs(component) > 10000)) throw Error('VECTOR_RANGE');
            return;
        }
        const integral = ['int', 'enum'].includes(data.type);
        if (typeof next !== 'number' || !Number.isFinite(next) || (integral && !Number.isInteger(next))) {
            throw Error('INVALID_NUMBER: ' + data.id);
        }
        if ((data.min !== undefined && next < data.min) || (data.max !== undefined && next > data.max)) {
            throw Error('OUT_OF_RANGE: ' + data.id);
        }
    }

    function domainEntries(m, args) {
        switch (args.domain) {
            case 'face':
            case 'body':
                return entries(m, args.domain).map(morphEntry);
            case 'clothing':
                return clothingDomain(m);
            case 'colors':
                return colorDomain(m);
            case 'expressions':
                return expressionDomain(m, args.scope);
            case 'general':
                return generalDomain(m);
            case 'hair_bones':
                return hairBoneDomain(m, args);
            case 'photo':
                return photoDomain(m);
            case 'accessories':
                return accessoryDomain(m, args.scope);
            case 'hair':
                return hairNodeParameters(m, args);
            default:
                throw Error('UNKNOWN_DOMAIN');
        }
    }

    function listDomain(args) {
        const m = model(args.expected_model);
        const all = domainEntries(m, args);
        const offset = args.offset ?? 0;
        const limit = args.limit ?? 200;
        if (!Number.isInteger(offset) || offset < 0 || !Number.isInteger(limit) || limit < 1 || limit > 500) {
            throw Error('INVALID_PAGINATION');
        }
        return {
            model_token: m.token, domain: args.domain, scope: args.scope || null,
            total: all.length,
            next_offset: offset + limit < all.length ? offset + limit : null,
            parameters: all.slice(offset, offset + limit).map(entry => entry.data),
        };
    }

    function writeDomain(args) {
        if (!args.expected_model) throw Error('EXPECTED_MODEL_REQUIRED');
        const m = model(args.expected_model);
        const index = new Map(domainEntries(m, args).map(entry => [entry.data.id, entry]));
        if (!Array.isArray(args.changes) || args.changes.length < 1 || args.changes.length > 64) {
            throw Error('BATCH_SIZE: 1..64');
        }
        const seen = new Set();
        const planned = args.changes.map(change => {
            const entry = index.get(change.id);
            if (!entry) throw Error('UNKNOWN_PARAMETER: ' + change.id);
            const identity = entry.alias || change.id;
            if (seen.has(identity)) throw Error('DUPLICATE_PARAMETER');
            seen.add(identity);
            validateValue(entry, change.value);
            return { entry, next: change.value };
        });
        colorState.validateBatch(planned.map(({ entry }) => ({ e: entry })));
        const affected = [...new Set(planned.flatMap(({ entry }) => entry.data.affected_parameter_ids || []))].sort();
        const applied = [];
        for (const { entry, next } of planned) {
            try {
                if (entry.write) entry.write(next);
                else invokeManaged(entry.o, 'set_' + entry.prop, [boxArgument(entry.data.type, next)]);
                applied.push({
                    id: entry.data.id,
                    before: entry.data.value,
                    after: entry.read ? entry.read() : readValue(entry.o, entry.prop, entry.data.type),
                    ...(entry.data.type === 'color' ? { requested_value: next } : {}),
                });
            } catch (error) {
                return { ok: false, model_token: m.token, applied, affected_color_parameter_ids: affected,
                         error: String(error), frame: state.frame };
            }
        }
        return { ok: true, model_token: m.token, applied, affected_color_parameter_ids: affected,
                 frame: state.frame };
    }

    const HAIR_PARTS = ['HairFront', 'HairBack', 'AllHair', 'HairTied', 'HairSideburns', 'HairAhoge', 'HairHanege'];

    function selectHairPart(m, category) {
        const match = categories(m, 'hair')
            .find(item => lastSegment(text(item.method('get_TranslationKey').invoke())) === category);
        if (!match) throw Error('UNKNOWN_HAIR_CATEGORY');
        invokeManaged(selector(m, 'hair'), 'set_SelectedCategory', [match.handle]);
        return match;
    }

    function hairDesignEditor(m, category) {
        if (!HAIR_PARTS.includes(category)) throw Error('HAIR_PART_CATEGORY_REQUIRED');
        const selected = selectHairPart(m, category);
        const hair = m.root.method('get_HairEditor').invoke();
        const hairModel = hair.method('get_Model').invoke();
        const types = [...selected.field('_categoryModel').value.field('transferableTypes').value];
        if (types.length !== 1) throw Error('HAIR_CATEGORY_TYPE_AMBIGUOUS');
        invokeManaged(hairModel, 'SetTransferableType', [types[0].handle]);
        let design = hair.method('get_DesignEditor').invoke();
        if (design.handle.isNull()) {
            design = cached(m, 'hair-design', () => {
                const created = cls('VRoid.Studio', 'VRoid.Studio.HairEditor.DesignEditor.ViewModel').alloc();
                invokeManaged(created, '.ctor', [
                    m.root.method('get_Resources').invoke().handle,
                    m.main.method('get_CurrentFile').invoke().handle,
                    m.main.method('get_GlobalBus').invoke().handle,
                    hairModel.handle, m.engine.handle,
                    m.main.method('get_CurrentFile').invoke().method('get_Engine').invoke().handle,
                    hair.handle, m.main.method('get_ActionHandler').invoke().handle,
                ]);
                return created;
            });
            invokeManaged(hair, 'set_DesignEditor', [design.handle]);
        }
        invokeManaged(design, 'UpdateLists');
        return design;
    }

    function hairNodeId(node) {
        const getter = node.tryMethod('get_HairStrandPath') ? 'get_HairStrandPath' : 'get_HairGroupPath';
        const path = node.method(getter).invoke();
        return ['TransferableId', 'HairGroupId', 'HairStrandId']
            .filter(name => path.tryMethod('get_' + name))
            .map(name => text(path.method('get_' + name).invoke()))
            .join('/');
    }

    function hairNodeList(design) {
        const out = [];
        function walk(node, parent) {
            const id = hairNodeId(node);
            out.push({ n: node, id, parent });
            for (const child of seq(node.method('get_Children').invoke())) walk(child, id);
        }
        for (const group of seq(design.method('get_HairGroups').invoke())) walk(group, null);
        return out;
    }

    function hairNodeParameters(m, args) {
        const design = hairDesignEditor(m, args.category);
        const found = hairNodeList(design).find(node => node.id === args.scope);
        if (!found) throw Error('UNKNOWN_HAIR_NODE: list_hair_nodes first');
        const node = found.n;
        const prefix = 'hair/' + found.id;
        const out = [];
        out.push(makeParameter(node, 'TranslatedDisplayName', prefix + '/name', 'string', { label: 'Name' }));
        for (const prop of ['IsVisible', 'IsEditable']) {
            out.push(makeParameter(node, prop, prefix + '/' + prop, 'bool', { label: prop }));
        }
        if (node.method('get_IsGroupColorShown').invoke()) {
            out.push(makeParameter(node, 'GroupColor', prefix + '/color', 'color',
                { label: 'Group color', min: 0, max: 1 }));
        }
        if (node.tryMethod('get_HairGroupPath')) {
            const path = node.method('get_HairGroupPath').invoke();
            const guideOrigin = () => {
                const query = cls('VRoidCore', 'VRoidCore.Editing.Query.GetGuideOriginTransformQuery').alloc();
                invokeManaged(query, '.ctor', [path.handle]);
                return invokeManaged(query, 'Execute',
                    [m.context.method('get_ActiveModel').invoke().handle]).unbox();
            };
            const guideFields = [
                ['Position', 'vector3', ['x', 'y', 'z']],
                ['Rotation', 'quaternion', ['x', 'y', 'z', 'w']],
                ['Scale', 'vector3', ['x', 'y', 'z']],
            ];
            for (const [field, type, channels] of guideFields) {
                const readGuide = () => {
                    const component = guideOrigin().field(field).value;
                    return channels.map(channel => component.field(channel).value);
                };
                out.push({
                    data: { id: prefix + '/guide/' + field, label: 'Guide ' + field, type,
                            value: readGuide(), editable: true,
                            units: field === 'Position' ? 'meters' : undefined },
                    read: readGuide,
                    write: next => {
                        const transform = guideOrigin();
                        const component = transform.field(field).value;
                        channels.forEach((channel, index) => { component.field(channel).value = next[index]; });
                        const command = cls('VRoidCore',
                            'VRoidCore.Editing.History.Command.SetGuideOriginTransformCommand').alloc();
                        invokeManaged(command, '.ctor', [path.handle, transform.handle]);
                        invokeManaged(m.context, 'ExecuteSyncCommand', [command.handle]);
                    },
                });
            }
        }
        const property = cached(m, 'hair-property/' + found.id,
            () => design.method('get_Mode').invoke().method('CreateProperty').invoke(node));
        seq(property.method('get_Groups').invoke()).forEach((group, groupIndex) => {
            seq(group.method('get_ParameterItems').invoke()).forEach((item, itemIndex) => {
                const id = prefix + '/' + groupIndex + '/' + itemIndex;
                const extra = { category: text(group.method('get_TranslatedHeader').invoke()) };
                if (item.tryMethod('get_MinValue') && item.tryMethod('set_Value')) {
                    const integral = item.method('get_Value').returnType.name === 'System.Int32';
                    out.push(makeParameter(item, 'Value', id, integral ? 'int' : 'float', {
                        ...extra, min: item.method('get_MinValue').invoke(),
                        max: item.method('get_MaxValue').invoke(), range_source: 'native UI',
                    }));
                } else if (item.tryMethod('get_Index') && item.tryMethod('get_Items')) {
                    const options = seq(item.method('get_Items').invoke())
                        .map((option, index) => ({ value: index, label: displayLabel(option, String(index)) }));
                    out.push(makeParameter(item, 'Index', id, 'enum',
                        { ...extra, options, min: 0, max: options.length - 1 }));
                } else if (item.tryMethod('get_Curve')) {
                    const options = seq(item.method('get_CurveTemplates').invoke())
                        .map((option, index) => ({ value: index, label: displayLabel(option, String(index)) }));
                    out.push(makeParameter(item, 'SelectedCurveTemplateIndex', id + '/template', 'enum',
                        { ...extra, options, min: 0, max: options.length - 1 }));
                    out.push(makeParameter(item, 'Curve', id + '/curve', 'curve', extra));
                }
                if (item.tryMethod('set_IsOverriding')) {
                    out.push(makeParameter(item, 'IsOverriding', id + '/override', 'bool',
                        { ...extra, label: displayLabel(item, '') + ' override' }));
                }
            });
        });
        return out;
    }

    function accessoryTemplateList(m) {
        const editor = accessoryFeature(m);
        const out = [];
        for (const category of seq(editor.method('get_ShapeParameterCategories').invoke())) {
            invokeManaged(editor, 'set_SelectedShapeParameterCategory', [category.handle]);
            const groupType = text(category.method('get_TransferableGroupType').invoke());
            for (const template of seq(editor.method('get_Templates').invoke())) {
                const id = text(template.field('transferableGroupTemplate').value.field('id').value);
                out.push({ category, template, data: { id: groupType, label: displayLabel(template, id) } });
            }
        }
        return out;
    }

    function hairBoneEditor(m) {
        const hair = m.root.method('get_HairEditor').invoke();
        let editor = hair.method('get_BoneEditor').invoke();
        if (editor.handle.isNull()) {
            editor = cached(m, 'hair-bone-editor', () => {
                const created = cls('VRoid.Studio', 'VRoid.Studio.HairEditor.BoneEditor.ViewModel').alloc();
                invokeManaged(created, '.ctor', [
                    m.root.method('get_Resources').invoke().handle,
                    m.main.method('get_CurrentFile').invoke().handle,
                    m.main.method('get_GlobalBus').invoke().handle,
                    hair.method('get_Model').invoke().handle, hair.handle,
                    hair.method('get_MultiCustomItemSavingModelNonBaseHair').invoke().handle,
                ]);
                return created;
            });
            invokeManaged(hair, 'set_BoneEditor', [editor.handle]);
        }
        invokeManaged(editor, 'UpdateLists');
        return editor;
    }

    function clothingDomain(m) {
        const out = entries(m, 'clothing').map(morphEntry);
        const editor = m.root.method('get_ClothingEditor').invoke();
        for (const instance of seq(editor.method('get_Instances').invoke())) {
            const id = text(instance.field('transferableGroupInfo').value.method('get_Id').invoke());
            const bones = seq(instance.method('get_Bones').invoke());
            if (bones.length) {
                out.push(makeParameter(instance, 'SelectedBoneIndex', 'clothing/' + id + '/bone', 'enum', {
                    min: 0, max: bones.length - 1,
                    options: bones.map((bone, index) => ({ value: index, label: displayLabel(bone, String(index)) })),
                }));
            }
            if (instance.method('get_PartOriginPositionGizmoEnabled').invoke()) {
                out.push(makeParameter(instance, 'PartOriginGlobalPosition',
                    'clothing/' + id + '/position', 'vector3', { units: 'meters' }));
            }
        }
        return out;
    }

    function boneGroupList(editor) {
        return seq(editor.method('get_GroupedBoneGroups').invoke()).map(node => {
            const path = node.field('boneGroupPath').value;
            return {
                n: node, path,
                id: text(path.method('get_TransferableId').invoke()) + '/'
                    + text(path.method('get_BoneGroupId').invoke()),
            };
        });
    }

    const BONE_PROPERTIES = [
        ['BoneCount', 'int', 1, 20], ['SpringRootRate', 'float', 0, 1],
        ['Stiffness', 'float', 0, 1], ['Gravity', 'float', 0, 1], ['ColliderRadius', 'float', 0, 1],
    ];

    function hairBoneDomain(m, args) {
        hairDesignEditor(m, args.category || 'HairFront');
        const editor = hairBoneEditor(m);
        const out = [];
        const generation = editor.method('get_BoneGroupGeneration').invoke();
        out.push(makeParameter(generation, 'Count', 'hair_bones/generation/count', 'int',
            { min: 1, max: 100, persistent: false, label: 'Generated bone group count' }));
        out.push(makeParameter(generation, 'Edge', 'hair_bones/generation/edge', 'float',
            { min: 0, max: 1, persistent: false, label: 'Generation grouping threshold' }));
        for (const { n, path, id } of boneGroupList(editor)) {
            if (args.scope && args.scope !== id) continue;
            const property = cached(m, 'bone-property/' + id, () => {
                const created = cls('VRoid.Studio',
                    'VRoid.Studio.HairEditor.BoneEditor.Property.ViewModel.BoneGroupPropertyViewModel').alloc();
                invokeManaged(created, '.ctor', [
                    m.root.method('get_Resources').invoke().handle, m.engine.handle,
                    m.main.method('get_CurrentFile').invoke().method('get_Engine').invoke().handle,
                    editor.handle, path.handle,
                ]);
                return created;
            });
            for (const [name, type, min, max] of BONE_PROPERTIES) {
                out.push(makeParameter(property, name, 'hair_bones/' + id + '/' + name, type,
                    { min, max, label: name, category: displayLabel(n, id), range_source: 'MCP operating range' }));
            }
            out.push(makeParameter(n, 'TranslatedDisplayName', 'hair_bones/' + id + '/name', 'string',
                { label: 'Name' }));
        }
        return out;
    }

    function photoBooth(m) {
        const viewModel = m.root.field('obsoleteLegacyPhotoBoothViewModel').value;
        if (!viewModel.method('get_IsActive').invoke()) {
            throw Error('PHOTO_MODE_REQUIRED: set_preview_mode(photo) first');
        }
        return viewModel;
    }

    const PHOTO_TYPES = {
        'System.Single': 'float', 'System.Int32': 'int', 'System.Boolean': 'bool',
        'UnityEngine.Vector2': 'vector2', 'VRoid.UI.ScreenColor': 'screen_color',
    };
    const PHOTO_SCALARS = ['ColorAlpha', 'ImageAlpha', 'CurrentColor', 'IsAutoBlink', 'IsLookAtCameraOn',
        'LeftEyeGazeOffset', 'RightEyeGazeOffset', 'IsGazeOffsetSyncOn', 'LightIntencity',
        'LightDegreeAltitude', 'LightDegreeAzimuth'];
    const POST_EFFECT_GROUPS = ['bloomParam', 'colorGradingParam', 'comicBookParam',
        'antiAliasingParam', 'motionBlurParam'];

    function photoDomain(m) {
        const booth = photoBooth(m);
        const out = [];
        function addParameter(object, name, id, extra = {}) {
            const type = PHOTO_TYPES[object.method('get_' + name).returnType.name];
            if (!type) throw Error('UNSUPPORTED_PHOTO_PARAMETER');
            out.push(makeParameter(object, name, id, type, { label: name, persistent: false, ...extra }));
        }
        for (const name of PHOTO_SCALARS) addParameter(booth, name, 'photo/' + name);
        addParameter(booth, 'LightColor', 'photo/LightColor');

        const wind = booth.method('get_WindViewModel').invoke();
        for (const name of ['DirectionX', 'DirectionY', 'DirectionZ']) {
            addParameter(wind, name, 'photo/wind/' + name, { min: -100, max: 100 });
        }

        const effects = booth.method('get_PostEffectSettings').invoke();
        for (const groupName of POST_EFFECT_GROUPS) {
            const group = effects.method('get_' + groupName).invoke();
            const props = group.class.methods.filter(method => method.name.startsWith('get_')
                && PHOTO_TYPES[method.returnType.name]
                && group.tryMethod('set_' + method.name.slice(4)));
            for (const method of props) {
                addParameter(group, method.name.slice(4), 'photo/effects/' + groupName + '/' + method.name.slice(4));
            }
        }

        const poses = booth.method('get_PosesViewModel').invoke();
        const poseOptions = seq(poses.method('get_PoseAnimationList').invoke())
            .map((pose, index) => ({ value: index, label: displayLabel(pose, String(index)) }));
        addParameter(poses, 'SelectedIndex', 'photo/pose',
            { min: 0, max: poseOptions.length - 1, options: poseOptions });
        out[out.length - 1].data.type = 'enum';

        const poseModeType = cls('VRoidStudio', 'VRoidStudio.GUI.AvatarEditor.PhotoBooth.PoseMode');
        const poseModes = ['FemaleAnimation', 'MaleAnimation', 'ManualPose'].map(name => {
            const raw = poseModeType.field(name).value;
            return { label: name, value: typeof raw === 'number' ? raw : raw.field('value__').value };
        });
        const manualMode = poseModes.find(mode => mode.label === 'ManualPose').value;
        out[out.length - 1].write = next => {
            invokeManaged(booth, 'set_PoseModeIndex', [boxArgument('int', manualMode)]);
            invokeManaged(poses, 'set_SelectedIndex', [boxArgument('int', next)]);
        };
        out.push(makeParameter(booth, 'PoseModeIndex', 'photo/mode', 'enum', {
            options: poseModes, min: Math.min(...poseModes.map(mode => mode.value)),
            max: Math.max(...poseModes.map(mode => mode.value)), persistent: false,
        }));

        const animations = booth.method('get_AnimationsViewModel').invoke();
        const animationItems = [
            ...seq(animations.method('get_FemaleAnimationList').invoke()),
            ...seq(animations.method('get_MaleAnimationList').invoke()),
        ];
        const currentAnimation = () => {
            const selected = animations.method('get_SelectedAnimation').invoke();
            return selected.handle.isNull() ? -1
                : animationItems.findIndex(item => item.handle.equals(selected.handle));
        };
        out.push({
            data: { id: 'photo/animation', label: 'Animation', type: 'enum', value: currentAnimation(),
                    editable: true, persistent: false, min: 0, max: animationItems.length - 1,
                    options: animationItems.map((item, index) => ({ value: index,
                        label: displayLabel(item, String(index)) })) },
            read: currentAnimation,
            write: next => {
                const female = animations.method('IsFemaleAnimation').invoke(animationItems[next]);
                const mode = poseModes.find(entry =>
                    entry.label === (female ? 'FemaleAnimation' : 'MaleAnimation')).value;
                invokeManaged(booth, 'set_PoseModeIndex', [boxArgument('int', mode)]);
                invokeManaged(animations, 'set_SelectedAnimation', [animationItems[next].handle]);
            },
        });
        out.push({
            data: { id: 'photo/animation_playing', label: 'Animation playing', type: 'bool',
                    value: animations.method('get_IsAnimationPlaying').invoke(), editable: true,
                    persistent: false },
            read: () => animations.method('get_IsAnimationPlaying').invoke(),
            write: next => {
                if (animations.method('get_IsAnimationPlaying').invoke() !== next) {
                    invokeManaged(animations, 'TogglePlayAnimation');
                }
            },
        });

        const controller = poses.field('_posesModel').value.field('_poseController').value;
        if (!controller.handle.isNull()) {
            seq(controller.field('poseSerializers').value).forEach((serializer, serializerIndex) => {
                const definition = serializer.method('Serialize').invoke();
                const settable = definition.class.methods.filter(method => method.name.startsWith('get_')
                    && /Current/i.test(method.name)
                    && definition.tryMethod('set_' + method.name.slice(4)));
                for (const method of settable) {
                    const name = method.name.slice(4);
                    const type = { 'UnityEngine.Quaternion': 'quaternion', 'UnityEngine.Vector3': 'vector3',
                        'System.Single': 'float' }[method.returnType.name];
                    if (!type) continue;
                    const readPose = () => readValue(serializer.method('Serialize').invoke(), name, type);
                    out.push({
                        data: { id: 'photo/pose_controls/' + serializerIndex + '/' + name,
                                label: displayLabel(serializer, String(serializerIndex)) + ' ' + name,
                                type, value: readPose(), editable: true, persistent: false },
                        read: readPose,
                        write: next => {
                            const fresh = serializer.method('Serialize').invoke();
                            invokeManaged(fresh, 'set_' + name, [boxArgument(type, next)]);
                            invokeManaged(serializer, 'Deserialize', [fresh.handle]);
                        },
                    });
                }
            });
        }

        const hands = booth.method('get_HandPosesViewModel').invoke();
        for (const side of ['Left', 'Right']) {
            const options = seq(hands.method('get_' + side + 'HandAnimationSource').invoke())
                .map((item, index) => ({ value: index, label: displayLabel(item, String(index)) }));
            addParameter(hands, side + 'HandAnimationIndex', 'photo/hands/' + side + '/pose',
                { min: 0, max: options.length - 1, options });
            out[out.length - 1].data.type = 'enum';
            addParameter(hands, side + 'HandAnimationWeight', 'photo/hands/' + side + '/weight',
                { min: 0, max: 1 });
        }

        const camera = booth.method('get_PhotoBoothCamera').invoke();
        out.push(makeParameter(camera, 'fieldOfView', 'photo/camera/field_of_view', 'float',
            { min: 1, max: 179, persistent: false, units: 'degrees' }));
        out.push(makeParameter(camera, 'orthographic', 'photo/camera/orthographic', 'bool', { persistent: false }));
        out.push(makeParameter(camera, 'orthographicSize', 'photo/camera/orthographic_size', 'float',
            { min: .01, max: 100, persistent: false }));
        for (const name of ['ColorAlpha', 'ImageAlpha']) {
            const entry = out.find(item => item.data.id === 'photo/' + name);
            entry.data.min = 0;
            entry.data.max = 1;
        }
        return out;
    }

    // ------------------------------------------------------- hair authoring
    function findHairNode(m, category, nodeId) {
        const design = hairDesignEditor(m, category);
        const node = hairNodeList(design).find(candidate => candidate.id === nodeId);
        if (!node) throw Error('UNKNOWN_HAIR_NODE');
        return { d: design, n: node };
    }

    function hairPath(node, kind) {
        const getter = kind === 'strand' ? 'get_HairStrandPath' : 'get_HairGroupPath';
        if (!node.n.tryMethod(getter)) throw Error(kind === 'strand' ? 'NOT_A_HAIR_STRAND' : 'NOT_A_HAIR_GROUP');
        return node.n.method(getter).invoke();
    }

    const activeModelOf = m => m.context.method('get_ActiveModel').invoke();

    function runQuery(m, queryClass, constructorArgs) {
        const query = queryClass.alloc();
        invokeManaged(query, '.ctor', constructorArgs);
        return invokeManaged(query, 'Execute', [activeModelOf(m).handle]);
    }

    function readPoint(boxed) {
        const value = boxed.unbox();
        const vector = field => {
            const component = value.field(field).value;
            return ['x', 'y', 'z'].map(channel => component.field(channel).value);
        };
        const uv = value.field('<Uv>k__BackingField').value;
        return {
            point: vector('<Point>k__BackingField'),
            normal: vector('<Normal>k__BackingField'),
            uv: ['x', 'y'].map(channel => uv.field(channel).value),
        };
    }

    function buildPoint(point, normal, uv) {
        const pointType = cls('VRoidCore', 'VRoidCore.Common.SpecificTypes.ControlPoint');
        const memory = Memory.alloc(64);
        memory.writeByteArray(new Uint8Array(64));
        const controlPoint = new Il2Cpp.ValueType(memory, pointType.type);
        const setVector = (field, components) => {
            const target = controlPoint.field(field).value;
            ['x', 'y', 'z'].forEach((channel, index) => { target.field(channel).value = components[index]; });
        };
        setVector('<Point>k__BackingField', point);
        setVector('<Normal>k__BackingField', normal);
        const uvField = controlPoint.field('<Uv>k__BackingField').value;
        uvField.field('x').value = uv[0];
        uvField.field('y').value = uv[1];
        return controlPoint;
    }

    function dictionaryPairs(dictionary) {
        const iterator = dictionary.method('GetEnumerator').invoke();
        const out = [];
        try {
            while (iterator.method('MoveNext').invoke()) out.push(iterator.method('get_Current').invoke());
        } finally {
            if (iterator.tryMethod('Dispose')) iterator.method('Dispose').invoke();
        }
        return out;
    }

    // OrderedDictionary hides get_Current behind explicit interfaces. Prefer
    // indexed access, then both enumerator shapes; the caller normalises the
    // raw entries.
    function orderedDictionaryEntries(dictionary) {
        try {
            const count = dictionary.method('get_Count').invoke();
            if (dictionary.tryMethod('get_Item')) {
                const indexed = [];
                for (let index = 0; index < count; index += 1) indexed.push(dictionary.method('get_Item').invoke(index));
                return indexed;
            }
        } catch (error) { /* not indexable */ }
        const iterator = dictionary.method('GetEnumerator').invoke();
        const out = [];
        let current = null;
        for (const candidate of ['get_Current', 'System.Collections.IEnumerator.get_Current',
            'System.Collections.Generic.IEnumerator<T>.get_Current']) {
            if (iterator.tryMethod(candidate)) {
                current = iterator.method(candidate);
                break;
            }
        }
        try {
            while (iterator.method('MoveNext').invoke()) out.push(current ? current.invoke() : iterator);
        } finally {
            if (iterator.tryMethod('Dispose')) iterator.method('Dispose').invoke();
        }
        return out;
    }

    function keyAndValue(entry) {
        if (entry.tryMethod && entry.tryMethod('get_Key') && entry.tryMethod('get_Value')) {
            return { key: text(entry.method('get_Key').invoke()), value: entry.method('get_Value').invoke() };
        }
        return { key: null, value: entry };
    }

    function makePath(pathClass, key) {
        const path = cls('VRoidCore', 'VRoidCore.Common.TransferableTypes.Path.' + pathClass).alloc();
        invokeManaged(path, '.ctor', [Il2Cpp.string(key).handle]);
        return path;
    }

    const makeColorPath = key => makePath('ColorPath', key);
    const makeBoolPath = key => makePath('BoolPath', key);

    function makeTemplateColorPath(templateKey, innerKey) {
        const template = cls('VRoidCore', 'VRoidCore.Common.TransferableTypes.Path.TemplatePath').alloc();
        invokeManaged(template, '.ctor', [Il2Cpp.string(templateKey).handle]);
        const path = cls('VRoidCore', 'VRoidCore.Common.TransferableTypes.Path.TemplateColorPath').alloc();
        invokeManaged(path, '.ctor', [template.handle, makeColorPath(innerKey).handle]);
        return path;
    }

    function makeColor(rgba) {
        const memory = Memory.alloc(16);
        memory.writeByteArray(new Uint8Array(16));
        const colour = new Il2Cpp.ValueType(memory, cls('UnityEngine.CoreModule', 'UnityEngine.Color').type);
        ['r', 'g', 'b', 'a'].forEach((channel, index) => { colour.field(channel).value = rgba[index]; });
        return colour;
    }

    function readColorValue(boxed) {
        const value = boxed.unbox ? boxed.unbox() : boxed;
        return ['r', 'g', 'b', 'a'].map(channel => value.field(channel).value);
    }

    // Element type ordinals exposed by the native enum.
    const ELEMENT_TYPES = ['BoneTransform', 'Color', 'BlendShapeTransform', 'Image', 'Bool', 'Float', 'Template'];

    function elementTypeName(raw) {
        const value = raw.unbox ? raw.unbox() : raw;
        const ordinal = value.field('value__').value;
        return ELEMENT_TYPES[ordinal] || String(ordinal);
    }

    // Colour element discovery: only the address/path combinations the binary
    // actually accepts are reported, and each probe failure is swallowed.
    const TEMPLATE_INNER_KEYS = ['OverlayColor', 'EmissionColor', 'MaterialColor', 'Overlay', 'Emission'];

    function collectTemplateReads(model, groupKey, transferableId, templateKey, reads) {
        const addresses = [['group', groupKey], ['tid', transferableId],
            ['template', templateKey], ['mixed', groupKey + '/' + templateKey]];
        for (const [addressLabel, address] of addresses) {
            if (!address) continue;
            for (const inner of TEMPLATE_INNER_KEYS) {
                for (const [pathLabel, makePathValue] of [['color', () => makeColorPath(inner)],
                    ['templ', () => makeTemplateColorPath(templateKey, inner)]]) {
                    try {
                        const colour = invokeManaged(model, 'GetColorParameter',
                            [Il2Cpp.string(address).handle, makePathValue().handle]);
                        reads.push({ group_key: groupKey, template_key: templateKey, address: addressLabel,
                                     path: pathLabel, inner, transferable_id: transferableId,
                                     color: readColorValue(colour) });
                    } catch (error) { /* combination not addressable */ }
                }
            }
        }
    }

    return {
        operations: {
            list_parameters: listDomain,
            set_parameters: writeDomain,

            set_preview_mode(args) {
                if (!args.expected_model) throw Error('EXPECTED_MODEL_REQUIRED');
                const m = model(args.expected_model);
                const booth = m.root.field('obsoleteLegacyPhotoBoothViewModel').value;
                const active = booth.method('get_IsActive').invoke();
                if (args.mode === 'photo') {
                    if (!active) invokeManaged(m.root, 'EnterToPhotoBooth');
                } else if (args.mode === 'edit') {
                    if (active) {
                        const navigation = m.main.method('get_GlobalBus').invoke()
                            .method('get_ScreenNavigation').invoke();
                        const screen = navigation.method('get_ActiveScreen').invoke();
                        if (screen.class.type.name !== 'VRoid.Studio.PhotoBoothScreen.ViewModel') {
                            throw Error('UNEXPECTED_SCREEN');
                        }
                        invokeManaged(navigation, 'Pop', [screen.handle, boxArgument('bool', false)]);
                    }
                } else {
                    throw Error('INVALID_PREVIEW_MODE');
                }
                return { model_token: m.token, mode: args.mode, frame: state.frame };
            },

            set_photo_camera(args) {
                if (!args.expected_model) throw Error('EXPECTED_MODEL_REQUIRED');
                const m = model(args.expected_model);
                photoBooth(m);
                validateValue({ data: { id: 'camera_position', type: 'vector3', editable: true } }, args.position);
                validateValue({ data: { id: 'camera_target', type: 'vector3', editable: true } }, args.target);
                const camera = m.main.method('get_GlobalBus').invoke()
                    .method('get_PhotoBoothAvatarCameraPosition').invoke();
                invokeManaged(camera, 'SetCustomView',
                    [boxArgument('vector3', args.position), boxArgument('vector3', args.target)]);
                return { model_token: m.token, frame: state.frame };
            },

            list_hair_nodes(args) {
                const m = model(args.expected_model);
                const design = hairDesignEditor(m, args.category);
                return {
                    model_token: m.token, category: args.category,
                    nodes: hairNodeList(design).map(({ n, id, parent }) =>
                        ({ id, parent, label: displayLabel(n, id), kind: n.class.name })),
                };
            },

            list_hair_bone_groups(args) {
                const m = model(args.expected_model);
                hairDesignEditor(m, args.category || 'HairFront');
                return {
                    model_token: m.token,
                    groups: boneGroupList(hairBoneEditor(m)).map(({ n, id }) => ({ id, label: displayLabel(n, id) })),
                };
            },

            generate_hair_bones(args) {
                if (!args.expected_model) throw Error('EXPECTED_MODEL_REQUIRED');
                const m = model(args.expected_model);
                hairDesignEditor(m, args.category || 'HairFront');
                invokeManaged(hairBoneEditor(m), 'GenHairBoneGroup');
                return { model_token: m.token, frame: state.frame };
            },

            edit_hair_structure(args) {
                if (!args.expected_model) throw Error('EXPECTED_MODEL_REQUIRED');
                const m = model(args.expected_model);
                const design = hairDesignEditor(m, args.category);
                if (args.action === 'add_procedural') invokeManaged(design, 'AddProceduralGuide');
                else if (args.action === 'add_brush') invokeManaged(design, 'AddBrushGuide');
                else if (args.action === 'remove') {
                    const node = hairNodeList(design).find(candidate => candidate.id === args.node_id);
                    if (!node) throw Error('UNKNOWN_HAIR_NODE');
                    invokeManaged(design, 'set_SelectedItem', [node.n.handle]);
                    invokeManaged(design, 'DeleteSelectedItem');
                } else {
                    throw Error('UNKNOWN_HAIR_ACTION');
                }
                const groups = hairNodeList(design).filter(node => !node.parent).map(node => node.id);
                return { model_token: m.token, frame: state.frame, groups };
            },

            list_hair_strand_points(args) {
                const m = model(args.expected_model);
                const { n } = findHairNode(m, args.category, args.node_id);
                const path = hairPath(n, 'strand');
                const countQuery = cls('VRoidCore', 'VRoidCore.Editing.Query.GetHairStrandControlPointCountQuery');
                const raw = runQuery(m, countQuery, [path.handle]).unbox().field('m_value').value;
                const total = raw | 0;
                if (total < 0 || total > 512) throw Error('UNEXPECTED_CONTROL_POINT_COUNT: ' + total);
                const pointQuery = cls('VRoidCore', 'VRoidCore.Editing.Query.GetHairStrandControlPointQuery');
                const points = [];
                for (let index = 0; index < total; index += 1) {
                    points.push({
                        index,
                        ...readPoint(runQuery(m, pointQuery, [path.handle, boxArgument('int', index)])),
                    });
                }
                return { model_token: m.token, node_id: args.node_id, total, points };
            },

            move_hair_strand_point(args) {
                if (!args.expected_model) throw Error('EXPECTED_MODEL_REQUIRED');
                const m = model(args.expected_model);
                const { n } = findHairNode(m, args.category, args.node_id);
                const path = hairPath(n, 'strand');
                if (path.class.type.name !== 'VRoidCore.Common.SpecificTypes.BrushHairStrandPath') {
                    throw Error('NOT_A_BRUSH_HAIR_STRAND');
                }
                const index = Number.isInteger(args.index) ? args.index : -1;
                if (index < 0 || index > 511) throw Error('INVALID_POINT_INDEX');
                validateValue({ data: { id: 'point', type: 'vector3', editable: true } }, args.point);
                validateValue({ data: { id: 'normal', type: 'vector3', editable: true } }, args.normal);
                validateValue({ data: { id: 'uv', type: 'vector2', editable: true } }, args.uv);
                const controlPoint = buildPoint(args.point, args.normal, args.uv);
                const command = cls('VRoidCore',
                    'VRoidCore.Editing.History.Command.MoveBrushHairStrandControlPointCommand').alloc();
                invokeManaged(command, '.ctor', [path.handle, boxArgument('int', index), controlPoint.handle]);
                invokeManaged(m.context, 'ExecuteSyncCommand', [command.handle]);
                const pointQuery = cls('VRoidCore', 'VRoidCore.Editing.Query.GetHairStrandControlPointQuery');
                const after = readPoint(runQuery(m, pointQuery, [path.handle, boxArgument('int', index)]));
                return { model_token: m.token, frame: state.frame, node_id: args.node_id, index,
                         applied: true, point: after };
            },

            duplicate_hair_strand(args) {
                if (!args.expected_model) throw Error('EXPECTED_MODEL_REQUIRED');
                const m = model(args.expected_model);
                const { d, n } = findHairNode(m, args.category, args.node_id);
                const path = hairPath(n, 'strand');
                if (path.class.type.name !== 'VRoidCore.Common.SpecificTypes.BrushHairStrandPath') {
                    throw Error('NOT_A_BRUSH_HAIR_STRAND');
                }
                const before = new Set(hairNodeList(d).map(node => node.id));
                const command = cls('VRoidCore',
                    'VRoidCore.Editing.History.Command.CloneBrushHairStrandCommand').alloc();
                invokeManaged(command, '.ctor', [path.handle]);
                invokeManaged(m.context, 'ExecuteSyncCommand', [command.handle]);
                invokeManaged(d, 'UpdateLists');
                const added = hairNodeList(d).filter(node => !before.has(node.id))
                    .map(node => ({ id: node.id, parent: node.parent, kind: node.n.class.name }));
                return { model_token: m.token, frame: state.frame, source: args.node_id, added };
            },

            list_hair_materials(args) {
                const m = model(args.expected_model);
                const design = hairDesignEditor(m, args.category || 'HairFront');
                const collection = design.field('materialThumbnailCollection').value;
                if (collection.handle.isNull()) throw Error('MATERIAL_COLLECTION_UNAVAILABLE');
                invokeManaged(collection, 'UpdateMaterialThumbnails');
                const dictionary = collection.method('get_MaterialThumbnails').invoke();
                // seq() would fall back to get_Item(index); dictionaries need GetEnumerator.
                const iterator = dictionary.method('GetEnumerator').invoke();
                const pairs = [];
                try {
                    while (iterator.method('MoveNext').invoke()) pairs.push(iterator.method('get_Current').invoke());
                } finally {
                    if (iterator.tryMethod('Dispose')) iterator.method('Dispose').invoke();
                }
                const out = [];
                for (const entry of pairs) {
                    const key = entry.method('get_Key').invoke();
                    const thumbnail = entry.method('get_Value').invoke();
                    const colour = thumbnail.method('get_MainColor').invoke();
                    const item = {
                        id: text(key.method('get_SharedHairMaterialId').invoke())
                            || text(key.method('ToString').invoke()),
                        color: ['r', 'g', 'b', 'a'].map(channel => colour.field(channel).value),
                    };
                    try {
                        const viewModel = cls('VRoid.Studio',
                            'VRoid.Studio.TextureEditor.Category.ViewModel.HairMaterialCategoryViewModel').alloc();
                        invokeManaged(viewModel, '.ctor', [m.root.method('get_Resources').invoke().handle,
                                                          m.engine.handle, key.handle]);
                        item.color_key = text(viewModel.field('colorKey').value);
                        item.editor_color = readColorValue(invokeManaged(viewModel, 'get_Color'));
                    } catch (error) {
                        item.color_key_error = String(error).slice(0, 120);
                    }
                    out.push(item);
                }
                return { model_token: m.token, count: out.length, materials: out };
            },

            set_hair_material(args) {
                if (!args.expected_model) throw Error('EXPECTED_MODEL_REQUIRED');
                const m = model(args.expected_model);
                const { n } = findHairNode(m, args.category, args.node_id);
                const strand = !!n.n.tryMethod('get_HairStrandPath');
                const path = hairPath(n, strand ? 'strand' : 'group');
                const expectedPath = strand ? 'VRoidCore.Common.SpecificTypes.BrushHairStrandPath'
                    : 'VRoidCore.Common.SpecificTypes.BrushHairGroupPath';
                if (path.class.type.name !== expectedPath) throw Error('NOT_A_BRUSH_HAIR_NODE');

                const materialId = String(args.shared_material_id || '');
                if (!materialId) throw Error('MATERIAL_ID_REQUIRED');
                const reference = cls('VRoidCore', 'VRoidCore.Common.SpecificTypes.HairMaterialReference')
                    .method('CreateSharedHairMaterial').invoke(Il2Cpp.string(materialId));
                const commandClass = cls('VRoidCore', strand
                    ? 'VRoidCore.Editing.History.Command.ModifyBrushHairStrandParameterSetCommand'
                    : 'VRoidCore.Editing.History.Command.ModifyBrushHairGroupParameterSetCommand');
                const queryClass = cls('VRoidCore', strand
                    ? 'VRoidCore.Editing.Query.GetBrushHairStrandParameterSetQuery'
                    : 'VRoidCore.Editing.Query.GetBrushHairGroupParameterSetQuery');
                const readMaterial = () => {
                    const parameterSet = runQuery(m, queryClass, [path.handle]);
                    const material = parameterSet.method('get_HairMaterialReference').invoke();
                    return material.handle.isNull() ? null
                        : (text(material.method('get_SharedHairMaterialId').invoke())
                            || text(material.method('get_TransferableMaterialId').invoke()));
                };
                const before = readMaterial();
                const command = commandClass.alloc();
                const actionClass = commandClass.method('.ctor').parameters[2].type.class;
                const delegate = Il2Cpp.delegate(actionClass,
                    parameterSet => { invokeManaged(parameterSet, 'set_HairMaterialReference', [reference.handle]); });
                invokeManaged(command, '.ctor',
                    [Il2Cpp.string('MCP set_hair_material').handle, path.handle, delegate.handle]);
                invokeManaged(m.context, 'ExecuteSyncCommand', [command.handle]);
                const current = readMaterial();
                return { model_token: m.token, frame: state.frame, node_id: args.node_id,
                         kind: strand ? 'strand' : 'group', applied: current === materialId,
                         before, material_id: current };
            },

            list_hair_color_elements(args) {
                const m = model(args.expected_model);
                findHairNode(m, args.category, args.node_id);
                const modelObject = activeModelOf(m);
                const withColors = [];
                const candidateKeys = new Set();
                let templateReads = null;
                for (const entry of dictionaryPairs(modelObject.method('get_TransferableGroups').invoke())) {
                    const groupKey = text(entry.method('get_Key').invoke()) || '';
                    const group = entry.method('get_Value').invoke();
                    const elements = [];
                    try {
                        for (const raw of orderedDictionaryEntries(group.method('get_EditableElements').invoke())) {
                            const { key: dictKey, value: element } = keyAndValue(raw);
                            const elementKey = dictKey !== null && dictKey !== undefined
                                ? dictKey : (text(element.method('get_Key').invoke()) || '');
                            let type = '?';
                            try { type = elementTypeName(invokeManaged(element, 'get_Type')); } catch (error) { /* unknown */ }
                            elements.push({
                                key: elementKey, type,
                                transferable_id: text(element.method('get_TransferableId').invoke()),
                            });
                            if (type === 'Color' && elementKey) candidateKeys.add(elementKey);
                            if (type === 'Template' && elementKey) {
                                const transferableId = text(element.method('get_TransferableId').invoke()) || '';
                                templateReads = templateReads || [];
                                collectTemplateReads(modelObject, groupKey, transferableId, elementKey, templateReads);
                            }
                        }
                    } catch (error) {
                        elements.push({ error: String(error).slice(0, 80) });
                    }
                    if (elements.length && withColors.length < 60) withColors.push({ group_key: groupKey, elements });
                }
                return {
                    model_token: m.token, node_id: args.node_id,
                    groups_with_color_elements: withColors, candidate_keys: [...candidateKeys],
                    template_reads: templateReads || [],
                    requested_transferable_id: String(args.node_id).split('/')[0],
                };
            },

            set_hair_color(args) {
                if (!args.expected_model) throw Error('EXPECTED_MODEL_REQUIRED');
                const m = model(args.expected_model);
                findHairNode(m, args.category, args.node_id);
                const modelObject = activeModelOf(m);
                const address = String(args.address || '');
                if (!address) throw Error('ADDRESS_REQUIRED: pass the group key from list_hair_color_elements');
                const applied = [];
                for (const change of args.changes || []) {
                    validateValue({ data: { id: change.key || 'key', type: 'color', editable: true } }, change.color);
                    const key = String(change.key);
                    let before = null;
                    try {
                        before = readColorValue(invokeManaged(modelObject, 'GetColorParameter',
                            [Il2Cpp.string(address).handle, makeColorPath(key).handle]));
                    } catch (error) {
                        before = null;
                    }
                    invokeManaged(modelObject, 'SetColorParameter',
                        [Il2Cpp.string(address).handle, makeColorPath(key).handle, makeColor(change.color).handle]);
                    // Every colour channel is gated by a paired <key>DisableFlag;
                    // the UI clears it, so the written value has to do the same.
                    let flag = null;
                    try {
                        const flagKey = key + 'DisableFlag';
                        invokeManaged(modelObject, 'SetBoolParameter',
                            [Il2Cpp.string(address).handle, makeBoolPath(flagKey).handle, boxArgument('bool', false)]);
                        flag = {
                            key: flagKey,
                            value: invokeManaged(modelObject, 'GetBoolParameter',
                                [Il2Cpp.string(address).handle, makeBoolPath(flagKey).handle])
                                .unbox().field('m_value').value,
                        };
                    } catch (error) {
                        flag = 'ERR: ' + String(error).slice(0, 100);
                    }
                    const after = invokeManaged(modelObject, 'GetColorParameter',
                        [Il2Cpp.string(address).handle, makeColorPath(key).handle]);
                    const value = readColorValue(after);
                    applied.push({
                        key, before, after: value, requested: change.color, disable_flag: flag,
                        applied: value.every((component, index) => Math.abs(component - change.color[index]) < 1e-4),
                    });
                }
                return { model_token: m.token, frame: state.frame, node_id: args.node_id, address, applied };
            },

            list_accessory_templates(args) {
                const m = model(args.expected_model);
                return { model_token: m.token, templates: accessoryTemplateList(m).map(entry => entry.data) };
            },

            list_accessories(args) {
                const m = model(args.expected_model);
                return {
                    model_token: m.token,
                    instances: accessoryItems(m).map(instance => ({
                        id: accessoryIdentity(instance), label: displayLabel(instance, ''),
                        visible: instance.method('get_IsVisible').invoke(),
                    })),
                };
            },

            edit_accessories(args) {
                if (!args.expected_model) throw Error('EXPECTED_MODEL_REQUIRED');
                const m = model(args.expected_model);
                const editor = accessoryFeature(m);
                if (args.action === 'add') {
                    const template = accessoryTemplateList(m).find(item => item.data.id === args.template_id);
                    if (!template) throw Error('UNKNOWN_TEMPLATE');
                    invokeManaged(editor, 'set_SelectedShapeParameterCategory', [template.category.handle]);
                    invokeManaged(editor, 'set_SelectedTemplate', [template.template.handle]);
                } else {
                    const instance = accessoryItems(m).find(item => accessoryIdentity(item) === args.instance_id);
                    if (!instance) throw Error('UNKNOWN_ACCESSORY');
                    invokeManaged(editor, 'set_SelectedInstance', [instance.handle]);
                    if (args.action === 'remove') invokeManaged(editor, 'RemoveSelectedInstance');
                    else if (args.action === 'duplicate') invokeManaged(editor, 'DuplicateSelectedInstance');
                    else throw Error('UNKNOWN_ACCESSORY_ACTION');
                }
                return { model_token: m.token, frame: state.frame };
            },

            list_expressions(args) {
                const m = model(args.expected_model);
                return {
                    model_token: m.token,
                    expressions: expressionGroups(m).map(group => ({
                        id: lastSegment(text(group.method('get_SynthesizedCompatKey').invoke())),
                        label: displayLabel(group, ''),
                    })),
                };
            },

            preview_expression(args) {
                if (!args.expected_model) throw Error('EXPECTED_MODEL_REQUIRED');
                const m = model(args.expected_model);
                if (args.expression === null) {
                    invokeManaged(m.face, 'ResetExpression');
                } else {
                    const group = expressionGroups(m).find(candidate =>
                        lastSegment(text(candidate.method('get_SynthesizedCompatKey').invoke())) === args.expression);
                    if (!group) throw Error('UNKNOWN_EXPRESSION');
                    invokeManaged(m.face, 'set_SelectedExpressionParameterCategory', [group.handle]);
                    invokeManaged(m.face, 'UpdateExpression');
                }
                return { model_token: m.token, frame: state.frame };
            },

            get_height(args) {
                const m = model(args.expected_model);
                const height = m.root.method('get_BodyEditor').invoke().method('get_BodyHeight').invoke();
                return {
                    model_token: m.token,
                    centimeters: height.method('get_BodyHeightValue').invoke(),
                    live_centimeters: height.method('GetBodyHeight').invoke() * 100,
                    label: text(height.method('get_BodyHeightLabel').invoke()),
                };
            },

            inspect_native_api(args) {
                // Read-only metadata listing for one managed class. No caller-supplied
                // method name is invoked; this only reports what the binary declares.
                const assemblies = ['VRoid.Studio', 'VRoidCore', 'VRoid.UI', 'UnityEngine.CoreModule', 'VRM10'];
                const name = String(args.class_name || '');
                if (!/^[A-Za-z0-9_.<>`]+$/.test(name) || name.length > 160) throw Error('INVALID_CLASS_NAME');
                if (!assemblies.includes(args.assembly)) throw Error('UNSUPPORTED_ASSEMBLY');
                const filter = String(args.filter || '').toLowerCase();
                const target = cls(args.assembly, name);
                const allMethods = target.methods;
                const allFields = target.fields;
                const methods = allMethods
                    .filter(method => !filter || method.name.toLowerCase().includes(filter))
                    .slice(0, 400)
                    .map(method => ({ name: method.name, static: method.isStatic,
                                      return: method.returnType.name,
                                      params: method.parameters.map(parameter =>
                                          ({ name: parameter.name, type: parameter.type.name })) }));
                const fields = allFields
                    .filter(field => !filter || field.name.toLowerCase().includes(filter))
                    .slice(0, 200)
                    .map(field => ({ name: field.name, static: field.isStatic, type: field.type.name }));
                let base = null;
                try { base = target.parent ? target.parent.name : null; } catch (error) { /* no parent */ }
                return { assembly: args.assembly, class_name: target.name, base,
                         method_count: allMethods.length, field_count: allFields.length, methods, fields };
            },

            search_native_classes(args) {
                // Read-only bounded class-name search inside one whitelisted assembly.
                const assemblies = ['VRoid.Studio', 'VRoidCore', 'VRoid.UI', 'UnityEngine.CoreModule', 'VRM10'];
                if (!assemblies.includes(args.assembly)) throw Error('UNSUPPORTED_ASSEMBLY');
                const needle = String(args.substring || '').toLowerCase();
                if (needle.length < 3 || !/^[a-z0-9_.<>`]+$/.test(needle)) throw Error('INVALID_SUBSTRING');
                const image = Il2Cpp.domain.assembly(args.assembly).image;
                const matches = image.classes
                    .filter(candidate => candidate.type.name.toLowerCase().includes(needle))
                    .slice(0, 100)
                    .map(candidate => candidate.type.name);
                return { assembly: args.assembly, substring: args.substring, matches };
            },
        },
    };
};
