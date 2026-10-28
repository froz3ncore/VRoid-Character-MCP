// Native operation dispatch for one disposable VRoid copy.
//
// Everything here runs synchronously on the Unity main thread (the queue in
// main_thread.js guarantees that), so no await, no callback and no Promise may
// escape. The module is organised as layers:
//
//   session   - which model is live, and its identity token
//   reading   - enumerate parameters and presets, with their metadata
//   writing   - validated batches, native history
//   capture   - one-off screenshots and photo-mode renders
//   dispatch  - mode gates, then the operation table
//
// `dispatch` is the only export; the sub-APIs (parameters, wear, textures,
// body reference, preset previews) register themselves into its table.

globalThis.vroid = (() => {
    // A model token is session-scoped and generation-scoped: opening another
    // file in the same copy invalidates every id issued before it.
    const sessionTag = Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
    let modelGeneration = 0;
    let boundEngine = '';
    const tasks = new Map();
    let nextTaskId = 0;

    const SUPPORTED_PARAMETERS = new Set([
        'BlendShapeTransformParameterViewModel',
        'CombinedBlendShapeTransformParameterViewModel',
        'BoneTransformParameterViewModel',
        'CombinedBoneTransformParameterViewModel',
    ]);

    const core = name => cls('UnityEngine.CoreModule', 'UnityEngine.' + name);
    const text = value => (value && !value.handle.isNull() ? value.content : null);
    const parameterMetadata = createParameterSemantics({ text });
    const captureQuality = createCaptureQuality({ core, cls, invokeManaged });
    const captureFraming = createCaptureFraming({ core, text });
    const attachedState = createAttachedState({main: mainViewModel, text, state});

    // ---------------------------------------------------------------- session
    function mainViewModel() {
        const reference = state.refs['VRoid.Studio.MainViewModel'];
        if (!reference) throw Error('NOT_READY: MainViewModel has not been constructed');
        return new Il2Cpp.Object(ptr(reference));
    }

    function modelContext(expected) {
        const main = mainViewModel();
        const file = main.field('_mainModel').value.field('currentFile').value;
        if (file.handle.isNull()) throw Error('NO_MODEL: initialize a disposable model first');
        const engine = file.field('engine').value;
        if (engine.handle.isNull() || engine.method('get_Disposed').invoke()) throw Error('MODEL_DISPOSED');
        const rootReference = state.refs['VRoid.Studio.EditRootScreen.ViewModel'];
        if (!rootReference) throw Error('MODEL_LOADING: EditRootScreen is not ready');
        const root = new Il2Cpp.Object(ptr(rootReference));
        if (!root.field('_engineModel').value.handle.equals(engine.handle)) throw Error('MODEL_LOADING');
        if (boundEngine !== engine.handle.toString()) {
            boundEngine = engine.handle.toString();
            modelGeneration += 1;
        }
        const token = sessionTag + ':' + modelGeneration;
        if (expected && expected !== token) throw Error('STALE_MODEL: list parameters again');
        return { main, file, engine, root, token, face: root.method('get_FaceEditor').invoke(),
                 context: engine.method('get_Context').invoke() };
    }

    function status() {
        const base = {
            pid: Process.id,
            unity: Il2Cpp.unityVersion,
            main_thread: state.mainThread,
            callback_thread: Process.getCurrentThreadId(),
            frame: state.frame || 0,
            background: core('Application').method('get_runInBackground').invoke(),
            focused: core('Application').method('get_isFocused').invoke(),
            model_ready: false,
            png_decoder: state.pngDecoder,
            ...(ATTACHED ? {attached_state: attachedState.snapshot()} : {}),
        };
        try {
            const m = modelContext();
            const photo = m.root.field('obsoleteLegacyPhotoBoothViewModel').value;
            const photoActive = photo.method('get_IsActive').invoke();
            let photoUpdating = false;
            if (photoActive) {
                const booth = photo.method('get_V1PhotoBooth').invoke();
                if (booth.handle.isNull()) {
                    photoUpdating = true;
                } else {
                    const preview = booth.method('get_PreviewModelTransform').invoke();
                    photoUpdating = preview.tryMethod('get_IsUpdatingModel')
                        ? preview.method('get_IsUpdatingModel').invoke() : false;
                }
            }
            const areas = ['face', 'body', 'hair', 'clothing'];
            return {
                ...base, model_ready: true, model_token: m.token,
                photo_active: photoActive, photo_updating: photoUpdating,
                presets_loading: areas.some(area => selector(m, area).method('get_IsLoading').invoke()),
                command_busy: !m.context.method('get_IsCommandExecutable').invoke(),
                updating: m.main.field('_editModelTransform').value.method('get_IsUpdatingModel').invoke(),
            };
        } catch (error) {
            return { ...base, reason: String(error) };
        }
    }

    // ---------------------------------------------------------------- reading
    function toArray(immutable) {
        const data = immutable.field('array').value;
        return data.handle.isNull() ? [] : [...data];
    }

    function readValue(parameter) {
        const getter = parameter.tryMethod('get_CombinedValue') ? 'get_CombinedValue' : 'get_ModelValue';
        return parameter.method(getter).invoke();
    }

    // Two parameters that share this key write the same native property, which
    // is how aliases and combined/raw pairs are detected.
    function identityKey(parameter) {
        const parts = [parameter.class.name, text(parameter.field('_transferableGroupType').value)];
        for (const field of parameter.class.fields) {
            if (field.isStatic || !/path|boneElementKey/i.test(field.name)) continue;
            const value = parameter.field(field.name).value;
            parts.push(value.handle.isNull() ? ''
                : value instanceof Il2Cpp.String ? value.content
                    : value.method('ToString').invoke().content);
        }
        return parts.join('|');
    }

    const EDITOR_NAMES = { face: 'Face', body: 'Body', hair: 'Hair', clothing: 'Clothing' };

    function selector(m, area) {
        if (!Object.hasOwn(EDITOR_NAMES, area)) throw Error('UNKNOWN_AREA');
        return m.root.method('get_' + EDITOR_NAMES[area] + 'Editor').invoke()
            .method('get_PresetsSelector').invoke();
    }

    function categories(m, area) {
        const found = [];
        const seen = new Set();
        function visit(category) {
            const address = category.handle.toString();
            if (seen.has(address)) return;
            seen.add(address);
            found.push(category);
            for (const child of toArray(category.method('get_Children').invoke())) visit(child);
        }
        visit(selector(m, area).method('get_Categories').invoke());
        return found;
    }

    function clothingEntries(m) {
        const editor = m.root.method('get_ClothingEditor').invoke();
        const found = [];
        for (const instance of editor.method('get_Instances').invoke()) {
            const info = instance.field('transferableGroupInfo').value;
            const group = text(info.method('get_Id').invoke());
            const type = text(info.method('get_Type').invoke());
            [...instance.method('get_BlendShapeParameters').invoke()].forEach((parameter, index) => {
                if (!SUPPORTED_PARAMETERS.has(parameter.class.name)) {
                    throw Error('UNSUPPORTED_CLOTHING_PARAMETER: ' + parameter.class.name);
                }
                if (!parameter.field('_context').value.handle.equals(m.context.handle)) {
                    throw Error('CONTEXT_MISMATCH');
                }
                found.push({
                    p: parameter, canonical: identityKey(parameter),
                    id: 'clothing/' + group + '/' + String(index).padStart(3, '0'),
                    category: type.split('.').pop(), category_key: type,
                });
            });
        }
        return found;
    }

    function faceOrBodyEntries(m, area) {
        const found = [];
        const seen = new Set();
        function visit(category) {
            const address = category.handle.toString();
            if (seen.has(address)) return;
            seen.add(address);
            const withModel = category.tryMethod('get_ParameterCategoryViewModel');
            const container = withModel ? withModel.invoke()
                : category.tryMethod('get_Parameters') ? category : null;
            if (container && !container.handle.isNull()) {
                const key = text(category.method('get_TranslationKey').invoke());
                const name = text(category.method('get_Name').invoke());
                toArray(container.method('get_Parameters').invoke()).forEach((parameter, index) => {
                    if (!SUPPORTED_PARAMETERS.has(parameter.class.name)) {
                        throw Error('UNSUPPORTED_FACE_PARAMETER: ' + parameter.class.name);
                    }
                    if (!parameter.field('_context').value.handle.equals(m.context.handle)) {
                        throw Error('CONTEXT_MISMATCH');
                    }
                    found.push({
                        p: parameter, canonical: identityKey(parameter),
                        id: area + '/' + key.split('.').pop() + '/' + String(index).padStart(3, '0'),
                        category: name, category_key: key,
                    });
                });
            }
            for (const child of toArray(category.method('get_Children').invoke())) visit(child);
        }
        visit(selector(m, area).method('get_Categories').invoke());
        if (!found.length) throw Error('NO_PARAMETERS: ' + area);
        return found;
    }

    function parameterEntries(m, area) {
        if (area === 'clothing') return clothingEntries(m);
        if (area !== 'face' && area !== 'body') throw Error('NO_PARAMETER_API_FOR_AREA');
        return faceOrBodyEntries(m, area);
    }

    function describeParameter(entry) {
        const parameter = entry.p;
        return {
            ...parameterMetadata(parameter), id: entry.id,
            label: text(parameter.method('get_Label').invoke()),
            category: entry.category, category_key: entry.category_key,
            type: parameter.class.name, value: readValue(parameter),
            min: parameter.method('get_MinValue').invoke(),
            max: parameter.method('get_MaxValue').invoke(),
            editable: parameter.method('get_IsEditable').invoke(),
        };
    }

    function listParameters(args = {}, area = 'face') {
        const m = modelContext(args.expected_model);
        const aliases = new Map();
        const parameters = parameterEntries(m, area).map(entry => {
            const described = describeParameter(entry);
            described.alias_of = aliases.get(entry.canonical) || null;
            if (!described.alias_of) aliases.set(entry.canonical, entry.id);
            return described;
        });
        return {
            model_token: m.token, schema: 'vroid-2.14.0-' + area + '-v1', area,
            count: parameters.length, unique_parameters: aliases.size, parameters,
        };
    }

    // ---------------------------------------------------------------- writing
    function applyChanges(args, area = 'face') {
        if (!args.expected_model) throw Error('EXPECTED_MODEL_REQUIRED');
        const m = modelContext(args.expected_model);
        const index = new Map(parameterEntries(m, area).map(entry => [entry.id, entry]));
        if (!Array.isArray(args.changes) || !args.changes.length || args.changes.length > 64) {
            throw Error('BATCH_SIZE: 1..64');
        }
        const seen = new Set();
        const changes = args.changes.map(change => {
            const entry = index.get(change.id);
            if (!entry) throw Error('UNKNOWN_PARAMETER: ' + change.id);
            if (seen.has(entry.canonical)) throw Error('DUPLICATE_PARAMETER_OR_ALIAS: ' + change.id);
            seen.add(entry.canonical);
            const described = describeParameter(entry);
            const target = change.value;
            if (typeof target !== 'number' || !Number.isFinite(target)
                || target < described.min || target > described.max) {
                throw Error('OUT_OF_RANGE: ' + change.id + ' [' + described.min + ',' + described.max + ']');
            }
            if (!described.editable) throw Error('PARAMETER_NOT_EDITABLE: ' + change.id);
            return { entry, before: described.value, value: target };
        });
        const applied = [];
        for (const change of changes) {
            try {
                if (Math.abs(change.before - change.value) > 1e-7) {
                    const payload = Memory.alloc(4);
                    payload.writeFloat(change.value);
                    const setter = change.entry.p.tryMethod('set_CombinedValue')
                        ? 'set_CombinedValue' : 'set_ModelValue';
                    invokeManaged(change.entry.p, setter, [payload]);
                }
                applied.push({ id: change.entry.id, before: change.before, after: readValue(change.entry.p) });
            } catch (error) {
                return { model_token: m.token, ok: false, partial: true, applied,
                         error: String(error), frame: state.frame || 0 };
            }
        }
        return {
            model_token: m.token, ok: true, applied, frame: state.frame || 0,
            history_policy: 'native VRoid history; a batch may require multiple undo steps',
        };
    }

    // ---------------------------------------------------------------- presets
    function collectPresets(m, area) {
        if (!['face', 'body', 'hair', 'clothing'].includes(area)) throw Error('UNSUPPORTED_PRESET_AREA');
        const entries = [];
        const clears = [];
        for (const category of categories(m, area)) {
            const withModel = category.tryMethod('get_PresetCategoryViewModel');
            const container = withModel ? withModel.invoke()
                : category.tryMethod('get_PresetOptions') ? category : null;
            if (!container || container.handle.isNull()) continue;
            const key = text(category.method('get_TranslationKey').invoke()).split('.').pop();
            const name = text(category.method('get_Name').invoke());
            const options = container.method('get_PresetOptions').invoke();
            const count = options.method('get_Count').invoke();
            for (let index = 0; index < count; index += 1) {
                const option = options.method('get_Item').invoke(index);
                if (option.class.name === 'ClearOptionViewModel') {
                    clears.push({
                        p: option, id: area + '/' + key + '/none', category: key, category_name: name,
                        label: name + ' / None', resource_name: null, clear: true, owned: true,
                        selected: null,
                    });
                    continue;
                }
                if (option.class.name !== 'PresetOptionViewModel') continue;
                const presetModel = option.field('_model').value;
                const presetId = text(option.method('get_TransferableGroupId').invoke());
                const resource = text(presetModel.field('resourceName').value);
                entries.push({
                    p: option, id: area + '/' + key + '/' + presetId,
                    category: key, category_name: name,
                    label: name + ' / ' + resource.split('/').slice(0, -1).pop(),
                    resource_name: resource,
                    owned: option.method('get_IsOwned').invoke(),
                    selected: option.method('get_IsSelected').invoke(),
                });
            }
        }
        return entries.concat(clears);
    }

    function listPresets(args, area) {
        const m = modelContext(args.expected_model);
        const all = collectPresets(m, area);
        const counts = new Map();
        for (const preset of all) {
            const bucket = counts.get(preset.category)
                || { id: preset.category, name: preset.category_name, count: 0 };
            bucket.count += 1;
            counts.set(preset.category, bucket);
        }
        if (args.category && !counts.has(args.category)) throw Error('UNKNOWN_PRESET_CATEGORY');
        const matching = all.filter(preset => (!args.category || preset.category === args.category)
            && (!args.owned_only || preset.owned));
        const offset = args.offset ?? 0;
        const limit = args.limit ?? 100;
        if (!Number.isInteger(offset) || offset < 0 || !Number.isInteger(limit) || limit < 1 || limit > 200) {
            throw Error('INVALID_PAGINATION');
        }
        return {
            model_token: m.token, area, categories: [...counts.values()], total: matching.length, offset,
            next_offset: offset + limit < matching.length ? offset + limit : null,
            presets: matching.slice(offset, offset + limit).map(({ p, ...data }) => data),
        };
    }

    function snapshotGroups(m) {
        const active = m.context.method('get_ActiveModel').invoke()
            .method('GetActiveTransferableGroups').invoke();
        const iterator = active.method('get_Values').invoke().method('GetEnumerator').invoke();
        const groups = [];
        try {
            while (iterator.method('MoveNext').invoke()) {
                const value = iterator.method('get_Current').invoke();
                groups.push({
                    id: text(value.method('get_Id').invoke()),
                    revision: text(value.method('get_Revision').invoke()),
                    type: text(value.method('get_Type').invoke()),
                });
            }
        } finally {
            iterator.method('Dispose').invoke();
        }
        return groups.sort((a, b) => a.id.localeCompare(b.id));
    }

    function withShoeTemplates(m, visit) {
        const editor = m.root.method('get_ClothingEditor').invoke();
        const clothing = selector(m, 'clothing');
        const previous = clothing.method('get_SelectedCategory').invoke();
        const category = categories(m, 'clothing')
            .find(item => text(item.method('get_TranslationKey').invoke()).split('.').pop() === 'Shoes');
        if (!category) throw Error('SHOE_CATEGORY_UNAVAILABLE');
        try {
            invokeManaged(clothing, 'set_SelectedCategory', [category.handle]);
            invokeManaged(editor, 'ResetTemplates');
            const templates = [...editor.method('get_Templates').invoke()].map((entry, index) => {
                const template = entry.field('transferableGroupTemplate').value;
                return {
                    entry, index,
                    id: text(template.field('id').value),
                    label: text(entry.method('get_TranslatedDisplayName').invoke()),
                };
            });
            return visit(editor, templates);
        } finally {
            invokeManaged(clothing, 'set_SelectedCategory', [previous.handle]);
        }
    }

    function listShoeTemplates(args) {
        if (!args.expected_model) throw Error('EXPECTED_MODEL_REQUIRED');
        const m = modelContext(args.expected_model);
        const before = snapshotGroups(m);
        const templates = withShoeTemplates(m, (_editor, rows) =>
            rows.map(({ id, label }) => ({ id, label, category: 'Shoes' })));
        if (JSON.stringify(before) !== JSON.stringify(snapshotGroups(m))) {
            throw Error('MODEL_CHANGED_DURING_TEMPLATE_LIST');
        }
        return { model_token: m.token, templates, model_modified: false, frame: state.frame };
    }

    function addShoeTemplate(args) {
        if (!args.expected_model) throw Error('EXPECTED_MODEL_REQUIRED');
        const m = modelContext(args.expected_model);
        const before = snapshotGroups(m);
        if (before.some(group => group.type.split('.').pop() === 'Shoes')) {
            throw Error('REMOVE_EXISTING_NATIVE_SHOES_FIRST');
        }
        const selected = withShoeTemplates(m, (editor, rows) => {
            const row = rows.find(template => template.id === args.template_id);
            if (!row) throw Error('UNKNOWN_SHOE_TEMPLATE');
            const index = Memory.alloc(4);
            index.writeS32(row.index);
            invokeManaged(editor, 'set_SelectedTemplateIndex', [index]);
            const actual = editor.method('get_SelectedTemplate').invoke();
            if (!actual.handle.equals(row.entry.handle)) throw Error('TEMPLATE_SELECTION_MISMATCH');
            invokeManaged(editor, 'AddSelectedTemplate');
            return { id: row.id, label: row.label };
        });
        return { model_token: m.token, template_id: selected.id, label: selected.label,
                 before_groups: before, frame: state.frame };
    }

    function applyPreset(args, area) {
        if (!args.expected_model) throw Error('EXPECTED_MODEL_REQUIRED');
        const m = modelContext(args.expected_model);
        const entry = collectPresets(m, area).find(preset => preset.id === args.preset_id);
        if (!entry) throw Error('UNKNOWN_PRESET');
        if (!entry.owned) throw Error('PRESET_NOT_OWNED');
        if (entry.selected) return { model_token: m.token, preset_id: entry.id, changed: false, frame: state.frame };
        const beforeGroups = snapshotGroups(m);
        const enabled = Memory.alloc(1);
        enabled.writeU8(1);
        if (entry.clear) invokeManaged(entry.p, 'ClearTransferableGroup');
        else invokeManaged(entry.p, 'set_IsSelected', [enabled]);
        return { model_token: m.token, preset_id: entry.id, category: entry.category,
                 clear: !!entry.clear, changed: true, before_groups: beforeGroups, frame: state.frame };
    }

    function presetState(args) {
        const m = modelContext(args.expected_model);
        const entry = collectPresets(m, args.area).find(preset => preset.id === args.preset_id);
        if (!entry) throw Error('UNKNOWN_PRESET');
        return { selected: entry.selected, model_token: m.token, active_groups: snapshotGroups(m) };
    }

    function shoeTemplateState(args) {
        const m = modelContext(args.expected_model);
        return { model_token: m.token, active_groups: snapshotGroups(m) };
    }

    // ------------------------------------------------------------------ tasks
    function rememberTask(task) {
        const id = String(++nextTaskId);
        tasks.set(id, { task, handle: retain(task) });
        return { task_id: id };
    }

    function taskStatus({ task_id }) {
        const holder = tasks.get(task_id);
        if (!holder) throw Error('UNKNOWN_TASK');
        const task = holder.task;
        if (!task.method('get_IsCompleted').invoke()) return { completed: false };
        const faulted = task.method('get_IsFaulted').invoke();
        const canceled = task.method('get_IsCanceled').invoke();
        const result = { completed: true, faulted, canceled };
        const getter = task.class.tryMethod('get_Result', 0);
        if (!faulted && !canceled && getter && getter.returnType.name === 'System.Boolean') {
            result.result = task.method('get_Result').invoke();
        }
        if (faulted) result.error = text(task.method('get_Exception').invoke().method('ToString').invoke());
        holder.handle.free();
        tasks.delete(task_id);
        return result;
    }

    // ------------------------------------------------------- managed invocation
    function invokeManaged(object, method, parameters = []) {
        // IL2CPP must see the normal Windows exception path: Frida's default
        // "steal" would abort on exceptions VRoid handles internally.
        const invoke = new NativeFunction(Il2Cpp.module.getExportByName('il2cpp_runtime_invoke'),
            'pointer', ['pointer', 'pointer', 'pointer', 'pointer'], { exceptions: 'propagate' });
        const exception = Memory.alloc(Process.pointerSize);
        exception.writePointer(NULL);
        const argv = parameters.length ? Memory.alloc(parameters.length * Process.pointerSize) : NULL;
        parameters.forEach((parameter, index) =>
            argv.add(index * Process.pointerSize).writePointer(parameter));
        const result = invoke(object.method(method, parameters.length).handle, object.handle, argv, exception);
        if (!exception.readPointer().isNull()) {
            const managed = new Il2Cpp.Object(exception.readPointer());
            throw Error('MANAGED_OPERATION_ERROR: ' + method + ': '
                + managed.method('ToString').invoke().content);
        }
        return new Il2Cpp.Object(result);
    }

    // ------------------------------------------------------- model operations
    function history(args, method) {
        if (!args.expected_model) throw Error('EXPECTED_MODEL_REQUIRED');
        return { ...rememberTask(invokeManaged(modelContext(args.expected_model).engine, method)),
                 frame: state.frame || 0 };
    }

    function newModel(args) {
        const variant = args.variant || 'F00';
        if (!['F00', 'M00'].includes(variant)) throw Error('UNSUPPORTED_VARIANT');
        const current = mainViewModel().field('_mainModel').value.field('currentFile').value;
        if (!current.handle.isNull()) throw Error('MODEL_ALREADY_OPEN');
        const preset = variant === 'F00' ? 'Preset_F' : 'Preset_M';
        mainViewModel().method('InitializeCurrentFileAndMoveToEditRoot', 2)
            .invoke(Il2Cpp.string(preset), Il2Cpp.string(variant));
        return { requested: true, variant };
    }

    function saveAs(args) {
        const m = modelContext(args.expected_model);
        if (!args.expected_model) throw Error('EXPECTED_MODEL_REQUIRED');
        const handler = m.main.method('get_ActionHandler').invoke();
        const path = Il2Cpp.string(args.path);
        const access = Memory.alloc(1);
        access.writeU8(0);
        const success = invokeManaged(handler, 'SaveSync', [path.handle, access])
            .unbox().field('m_value').value;
        if (!success) throw Error('SAVE_FAILED');
        // The host publishes the file under a new name itself. Leaving this
        // session untitled stops a UI autosave from targeting an older file.
        m.file.field('path').value = Il2Cpp.string('');
        handler.method('UpdateWindowTitle').invoke();
        return { saved: true, model_token: m.token };
    }

    function openModel(args) {
        const path = Il2Cpp.string(args.path);
        const keepPath = Memory.alloc(1);
        const fromXRoid = Memory.alloc(1);
        keepPath.writeU8(1);
        fromXRoid.writeU8(0);
        return rememberTask(invokeManaged(mainViewModel(), 'ImportFileAndMoveToEditRoot',
            [path.handle, keepPath, fromXRoid]));
    }

    // ---------------------------------------------------------------- capture
    function vector(x, y, z) {
        const boxed = core('Vector3').alloc();
        const value = boxed.unbox();
        value.method('.ctor', 3).invoke(x, y, z);
        return value;
    }

    function photoScreenshot(m, size, quality) {
        const photo = m.root.field('obsoleteLegacyPhotoBoothViewModel').value;
        if (!photo.method('get_IsActive').invoke()) throw Error('PHOTO_MODE_REQUIRED');
        const camera = photo.method('get_PhotoBoothCamera').invoke();
        const renderTexture = core('RenderTexture');
        const previousTarget = camera.method('get_targetTexture').invoke();
        const previousActive = renderTexture.method('get_active').invoke();
        const wasEnabled = camera.method('get_enabled').invoke();
        let capture = null;
        let backupObject = null;
        let backupCamera = null;
        try {
            // allowMSAA has no getter in this binary, so CopyFrom snapshots the
            // whole camera configuration and restores it in the finally block.
            backupObject = core('GameObject').alloc();
            backupObject.method('.ctor', 1).invoke(Il2Cpp.string('MCP photo capture settings backup'));
            backupCamera = backupObject.method('AddComponent', 1).invoke(core('Camera').type.object);
            backupCamera.method('CopyFrom').invoke(camera);
            backupCamera.method('set_enabled').invoke(false);
            capture = captureQuality.begin(size, quality);
            camera.method('set_allowMSAA').invoke(true);
            invokeManaged(camera, 'set_targetTexture', [capture.target.handle]);
            invokeManaged(camera, 'Render');
            const base64 = capture.encode();
            return { model_token: m.token, view: 'photo', width: size, height: size,
                     mime_type: 'image/png', quality: capture.metadata, base64 };
        } finally {
            if (backupCamera) {
                camera.method('CopyFrom').invoke(backupCamera);
                camera.method('set_enabled').invoke(wasEnabled);
            }
            invokeManaged(camera, 'set_targetTexture', [previousTarget.handle]);
            renderTexture.method('set_active').invoke(previousActive);
            if (backupObject) core('Object').method('DestroyImmediate', 1).invoke(backupObject);
            if (capture) capture.dispose();
        }
    }

    function screenshot(args) {
        const m = modelContext(args.expected_model);
        const view = args.view || 'front';
        const size = args.size === undefined ? 512 : args.size;
        if (!Number.isInteger(size) || size < 256 || size > 2048) {
            throw Error('CAPTURE_SIZE_RANGE: 256..2048');
        }
        captureQualityPlan(size, args.quality);
        if (view === 'photo') return photoScreenshot(m, size, args.quality);
        const parsed = parseCaptureView(view);
        if (parsed.regional
            && m.root.field('obsoleteLegacyPhotoBoothViewModel').value.method('get_IsActive').invoke()) {
            throw Error('RETURN_TO_EDIT_MODE_FIRST');
        }
        const plan = parsed.regional ? captureFraming.modelPlan(m, parsed, args.framing_reference) : null;
        const renderTexture = core('RenderTexture');
        const unityObject = core('Object');
        const previousActive = renderTexture.method('get_active').invoke();
        let holder = null;
        let capture = null;
        try {
            const body = m.main.method('get_GlobalBus').invoke().method('get_Common3D').invoke()
                .method('get_AvatarCamera').invoke().field('_body').value;
            const source = body.field('_templateCamera').value.method('get_PrimaryCamera').invoke();
            holder = core('GameObject').alloc();
            holder.method('.ctor', 1).invoke(Il2Cpp.string('VRoid MCP temporary capture'));
            const camera = holder.method('AddComponent', 1).invoke(core('Camera').type.object);
            camera.method('CopyFrom').invoke(source);
            camera.method('set_enabled').invoke(false);
            capture = captureQuality.begin(size, args.quality);
            camera.method('set_allowMSAA').invoke(true);
            camera.method('set_targetTexture').invoke(capture.target);
            camera.method('set_orthographic').invoke(false);
            camera.method('set_fieldOfView').invoke(30);

            const faceBounds = m.face.method('GetFaceSMR').invoke().method('get_bounds').invoke();
            const center = faceBounds.method('get_center').invoke();
            const extents = faceBounds.method('get_extents').invoke();
            let x = center.field('x').value;
            let y = center.field('y').value;
            let z = center.field('z').value;
            let radius = Math.max(extents.field('y').value, extents.field('x').value) * 1.8;
            if (view.startsWith('full_')) {
                // The character stands on y=0: frame the feet through the top of
                // the head with room for the T-pose arms, whatever the height.
                const top = y + extents.field('y').value;
                y = top / 2;
                radius = top * .68;
            }
            const distance = radius / Math.tan(Math.PI / 12);
            const transform = camera.method('get_transform').invoke();
            const diagonal = distance / Math.sqrt(2);
            if (plan) {
                [x, y, z] = plan.target;
                transform.method('set_position').invoke(vector(...plan.position));
            } else {
                transform.method('set_position').invoke(
                    view.endsWith('three_quarter') ? vector(x + diagonal, y, z + diagonal)
                        : view.endsWith('front') ? vector(x, y, z + distance)
                            : view.endsWith('back') ? vector(x, y, z - distance)
                                : vector(x + distance, y, z));
            }
            transform.method('LookAt').overload('UnityEngine.Vector3', 'UnityEngine.Vector3')
                .invoke(vector(x, y, z), vector(0, 1, 0));
            camera.method('Render').invoke();
            const base64 = capture.encode();
            return { model_token: m.token, view, width: size, height: size, mime_type: 'image/png',
                     quality: capture.metadata,
                     ...(plan ? { framing: captureFraming.readback(camera, plan) } : {}), base64 };
        } finally {
            renderTexture.method('set_active').invoke(previousActive);
            if (holder) unityObject.method('DestroyImmediate', 1).invoke(holder);
            if (capture) capture.dispose();
        }
    }

    // ------------------------------------------------------------- composition
    const extended = createParameterApi({
        model: modelContext, cls, core, text, array: toArray, invokeManaged,
        entries: parameterEntries, details: describeParameter, value: readValue,
        selector, categories, parameterMetadata,
    });
    const wear = createWearApi({ main: mainViewModel, cls, core, text, invokeManaged,
                                 rememberTask, captureQuality, captureFraming });
    const bodyReference = createBodyReferenceApi({ model: modelContext, cls, core, text, invokeManaged });
    const presetPreviews = createPresetPreviewApi({ model: modelContext, main: mainViewModel,
                                                     presetEntries: collectPresets, core, text });
    const textureApi = createTextureApi({ model: modelContext, cls, core, text, invokeManaged });
    const ordinary = createOrdinaryExtensions({model: modelContext, cls, core, text, invokeManaged, retain, state});

    function prepareCapture(args) {
        if (!args.expected_model) throw Error('EXPECTED_MODEL_REQUIRED');
        const m = modelContext(args.expected_model);
        const hair = m.root.method('get_HairEditor').invoke();
        const bone = hair.method('get_BoneEditor').invoke();
        const design = hair.method('get_DesignEditor').invoke();
        if (!bone.handle.isNull()) {
            invokeManaged(bone, 'ClearSelection');
            invokeManaged(bone, 'OnLeaveFeature');
        }
        if (!design.handle.isNull()) invokeManaged(design, 'ClearSelectHairOutLine');
        const photo = m.root.field('obsoleteLegacyPhotoBoothViewModel').value;
        if (photo.method('get_IsActive').invoke()) {
            const hidden = Memory.alloc(1);
            hidden.writeU8(0);
            invokeManaged(photo.method('get_PosesViewModel').invoke(), 'set_IsVisibleController', [hidden]);
        }
        return { model_token: m.token, frame: state.frame };
    }

    const operations = {
        ...textureApi.operations,
        ...ordinary.operations,
        ...attachedState.operations,
        native_png_status: () => state.pngDecoder,
        ...presetPreviews.operations,
        ...bodyReference.operations,
        ...wear.operations,
        ...extended.operations,
        status,
        list_face_params: listParameters,
        set_face_params: applyChanges,
        task_status: taskStatus,
        capture_framing_reference(args) {
            return captureFraming.reference(modelContext(args.expected_model));
        },
        prepare_capture: prepareCapture,
        list_presets: args => listPresets(args, args.area),
        apply_preset: args => applyPreset(args, args.area),
        list_body_params: args => listParameters(args, 'body'),
        set_body_params: args => applyChanges(args, 'body'),
        list_clothing_params: args => listParameters(args, 'clothing'),
        set_clothing_params: args => applyChanges(args, 'clothing'),
        list_hair_presets: args => listPresets(args, 'hair'),
        apply_hair_preset: args => applyPreset(args, 'hair'),
        list_clothing_presets: args => listPresets(args, 'clothing'),
        apply_clothing_preset: args => applyPreset(args, 'clothing'),
        list_shoe_templates: listShoeTemplates,
        add_shoe_template: addShoeTemplate,
        shoe_template_state: shoeTemplateState,
        preset_state: presetState,
        undo: args => history(args, 'UndoAsync'),
        redo: args => history(args, 'RedoAsync'),
        new_model: newModel,
        save_as: saveAs,
        open_model: openModel,
        screenshot,
        gc_check() {
            Il2Cpp.gc.collect(2);
            return listParameters();
        },
    };

    // ---------------------------------------------------------------- dispatch
    const EDIT_OPERATION = new RegExp('^(set_(face|body|clothing)_params|apply_.*preset|add_shoe_template|'
        + 'edit_hair_structure|edit_accessories|generate_hair_bones|move_hair_strand_point|'
        + 'duplicate_hair_strand|set_hair_material|set_hair_color|set_texture_layer_state|'
        + 'open_texture_editor|close_texture_editor|import_texture_layer|save_as|undo|redo|'
        + 'preview_expression|replace_part|save_custom_item|preserve_attached_unsaved|enter_vrm_export)$');
    const TEXTURE_OPERATION = new RegExp('^(list_texture_|export_texture_|export_renderer_texture|'
        + 'inspect_texture_|capture_texture_|open_texture_|close_texture_|import_texture_)');

    function dressUpActive() {
        return wear.operations.get_wear_status().active;
    }

    function requireOrdinaryEditing(name, args) {
        if (TEXTURE_OPERATION.test(name) && dressUpActive()) {
            throw Error('DRESS_UP_ACTIVE: texture tools require ordinary model editing');
        }
        if (name === 'list_shoe_templates' && dressUpActive()) {
            throw Error('DRESS_UP_ACTIVE: restart into ordinary editing');
        }
        const edits = EDIT_OPERATION.test(name)
            || (name === 'set_parameters' && args.domain !== 'photo');
        if (edits && dressUpActive()) {
            throw Error('DRESS_UP_ACTIVE: use wear tools or restart into ordinary editing');
        }
        const captureInAssembly = ['capture_body_reference', 'capture_framing_reference'].includes(name)
            || (name === 'screenshot' && parseCaptureView(args.view || 'front').regional);
        if (captureInAssembly && dressUpActive()) {
            throw Error('DRESS_UP_ACTIVE: use wear capture/reference tools for assemblies');
        }
        if (edits && modelContext().root.field('obsoleteLegacyPhotoBoothViewModel').value
            .method('get_IsActive').invoke()) {
            throw Error('RETURN_TO_EDIT_MODE_FIRST');
        }
    }

    return {
        dispatch(name, args = {}) {
            if (!Object.hasOwn(operations, name)) throw Error('UNKNOWN_OPERATION');
            if (state.pngDecoder.fatal && !['status', 'native_png_status'].includes(name))
                throw Error('NATIVE_PNG_DECODER_FAILED: ' + state.pngDecoder.fatal);
            attachedState.guard(name);
            requireOrdinaryEditing(name, args);
            return operations[name](args);
        },
    };
})();
