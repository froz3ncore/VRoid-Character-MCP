// Native raster-layer commands. Never mutate a saved protobuf or a live tree by hand.
globalThis.textureLayerMetadata = row => Object.fromEntries(
    ['layer_id', 'Name', 'Opacity', 'Visibility', 'CompositionMode', 'AlphaLocked']
        .map(key => [key, row[key] ?? null]));
globalThis.validateTextureLayerOrder = (current, requested) => {
    if (!Array.isArray(requested) || requested.length !== current.length || !current.length
        || new Set(requested).size !== requested.length || requested.some(id => !current.includes(id)))
        throw Error('LAYER_ORDER_MUST_BE_COMPLETE_PERMUTATION');
    return current.every((id, i) => id === requested[i]);
};

globalThis.createLayerManagementApi = H => {
    const {identity, region, imagePaths, layerRows, pathKey, nativeFieldOfType,
        stringProp, cls, invokeManaged, seq} = H;
    function requireFlatImage(m, image) {
        const active = m.context.method('get_ActiveModel').invoke();
        const root = active.method('GetEditableImage').invoke(image).method('get_RootLayerGroup').invoke();
        const children = seq(root.method('get_Children').invoke());
        if (children.some(child => String(child.method('get_LayerTreeType').invoke()) !== 'RasterLayer'))
            throw Error('NATIVE_LAYER_GROUP_UNSUPPORTED: preserve this image; folder editing is not implemented');
    }
    function modes() {
        return [...cls('VRoid.Studio', 'VRoid.Studio.TextureEditor.Layer.ViewModel.RasterLayerViewModel')
            .method('get_CompositionModeItems').invoke()].map(item => {
                const value = item.method('get_Mode').invoke();
                return {id: String(value), label: item.method('get_TranslatedDisplayName').invoke().content, value};
            });
    }
    function describeModes() { return modes().map(({id, label}) => ({id, label})); }
    function canvas(m, r) {
        const screen = m.main.method('get_GlobalBus').invoke().method('get_ScreenNavigation').invoke()
            .method('get_ActiveScreen').invoke();
        if (screen.handle.isNull() || screen.class.type.name !== 'VRoid.Studio.TextureEditorScreen.ViewModel')
            throw Error('OPEN_MATCHING_TEXTURE_EDITOR_FIRST');
        const editor = screen.method('get_TextureEditor').invoke();
        if (stringProp(editor, 'CurrentTransferableGroupType') !== stringProp(r.value, 'TypeId'))
            throw Error('TEXTURE_EDITOR_REGION_MISMATCH');
        return nativeFieldOfType(editor, 'VRoid.Studio.TextureEditor.ActionHandler');
    }
    function execute(m, command) {
        const hold = retain(command);
        try { invokeManaged(m.context, 'ExecuteSyncCommand', [command.handle]); }
        catch (error) { throw Error('LAYER_EDIT_UNCERTAIN: inspect before retrying: ' + error); }
        finally { hold.free(); }
    }
    function command(name, values) {
        const cmd = cls('VRoidCore', 'VRoidCore.Editing.History.Command.' + name).alloc();
        const hold = retain(cmd);
        try { invokeManaged(cmd, '.ctor', values); return {cmd, hold}; }
        catch (error) { hold.free(); throw error; }
    }
    function checked(args) {
        const m = identity(args), r = region(m, args.region_id), actions = canvas(m, r);
        const rows = layerRows(m, r), row = rows.find(x => x.data.layer_id === args.layer_id);
        if (!row) throw Error('UNKNOWN_TEXTURE_LAYER');
        requireFlatImage(m, row.path.method('get_EditableImagePath').invoke());
        if (!args.expected_layer || JSON.stringify(textureLayerMetadata(row.data)) !==
            JSON.stringify(textureLayerMetadata(args.expected_layer))) throw Error('STALE_LAYER_METADATA');
        return {m, r, actions, rows, row};
    }
    function checkStack(rows, expected) {
        if (!Array.isArray(expected) || JSON.stringify(rows.map(x => textureLayerMetadata(x.data))) !==
            JSON.stringify(expected.map(textureLayerMetadata))) throw Error('STALE_LAYER_STACK');
    }
    function result(m, r, rows, before, count) {
        return {model_token: m.token, region_id: r.key, before_layer: before,
            layers: rows.map(x => x.data), history_command_count: count, changed: count > 0,
            saved: false, frame: state.frame};
    }
    return {describeModes, operations: {
        rename_texture_layer(args) {
            if (typeof args.name !== 'string' || !args.name.trim() || args.name.length > 80
                || /[\x00-\x1f\x7f]/.test(args.name)) throw Error('INVALID_LAYER_NAME');
            const {m, r, row} = checked(args), before = row.data;
            const changed = before.Name !== args.name;
            if (changed) execute(m, cls('VRoid.Studio', 'VRoid.Studio.TextureEditor.ActionHandler')
                .method('CreateModifyNameCommand').invoke(row.path, Il2Cpp.string(args.name)));
            const rows = layerRows(m, r), after = rows.find(x => x.data.layer_id === args.layer_id);
            if (!after || after.data.Name !== args.name) throw Error('LAYER_NAME_READBACK_MISMATCH');
            return {...result(m, r, rows, before, Number(changed)), layer: after.data};
        },
        delete_texture_layer(args) {
            const {m, r, row, rows, actions} = checked(args);
            const stack = rows.filter(x => pathKey(x.path.method('get_EditableImagePath').invoke()) ===
                pathKey(row.path.method('get_EditableImagePath').invoke()));
            checkStack(stack, args.expected_stack);
            if (stack.length <= 1) throw Error('LAST_RASTER_LAYER_REFUSED');
            try { invokeManaged(actions, 'RemoveLayer', [row.path.handle]); }
            catch (error) { throw Error('LAYER_EDIT_UNCERTAIN: inspect before retrying: ' + error); }
            const after = layerRows(m, r);
            const wanted = rows.filter(x => x.data.layer_id !== args.layer_id).map(x => x.data);
            if (JSON.stringify(after.map(x => x.data)) !== JSON.stringify(wanted))
                throw Error('LAYER_DELETE_READBACK_MISMATCH');
            return {...result(m, r, after, row.data, 1), deleted_layer_id: args.layer_id};
        },
        reorder_texture_layers(args) {
            const m = identity(args), r = region(m, args.region_id); canvas(m, r);
            const image = imagePaths(m, r).find(p => pathKey(p) === args.image_id);
            if (!image) throw Error('UNKNOWN_EDITABLE_IMAGE');
            requireFlatImage(m, image);
            const rows = layerRows(m, r).filter(x => pathKey(x.path.method('get_EditableImagePath').invoke()) === args.image_id);
            checkStack(rows, args.expected_stack);
            const unchanged = validateTextureLayerOrder(rows.map(x => x.data.layer_id), args.layer_ids);
            if (!unchanged) {
                const pathHolds = rows.map(x => retain(x.path));
                const pathType = cls('VRoidCore', 'VRoidCore.Common.SpecificTypes.EditableImageRasterLayerPath');
                const paths = Il2Cpp.corlib.class('System.Collections.Generic.List`1').inflate(pathType).new();
                const hold = retain(paths);
                try {
                    for (const id of args.layer_ids) invokeManaged(paths, 'Add',
                        [rows.find(x => x.data.layer_id === id).path.handle]);
                    const built = command('SetEditableImageRasterLayerOrderCommand', [image.handle, paths.handle]);
                    try { execute(m, built.cmd); } finally { built.hold.free(); }
                } finally { hold.free(); for (const handle of pathHolds) handle.free(); }
            }
            const all = layerRows(m, r), after = all.filter(x => pathKey(x.path.method('get_EditableImagePath').invoke()) === args.image_id);
            if (JSON.stringify(after.map(x => x.data.layer_id)) !== JSON.stringify(args.layer_ids))
                throw Error('LAYER_ORDER_READBACK_MISMATCH');
            return {...result(m, r, all, null, Number(!unchanged)), image_id: args.image_id};
        },
        set_texture_layer_blend(args) {
            const {m, r, row} = checked(args), before = row.data;
            const mode = modes().find(x => x.id === args.composition_mode);
            if (!mode) throw Error('UNSUPPORTED_LAYER_COMPOSITION_MODE');
            const changed = before.CompositionMode !== mode.id;
            if (changed) execute(m, cls('VRoid.Studio', 'VRoid.Studio.TextureEditor.Layer.ViewModel.RasterLayerViewModel')
                .method('CreateModifyCompositionModeCommand').invoke(row.path, mode.value));
            const rows = layerRows(m, r), after = rows.find(x => x.data.layer_id === args.layer_id);
            if (!after || after.data.CompositionMode !== mode.id) throw Error('LAYER_BLEND_READBACK_MISMATCH');
            return {...result(m, r, rows, before, Number(changed)), layer: after.data};
        },
    }};
};
