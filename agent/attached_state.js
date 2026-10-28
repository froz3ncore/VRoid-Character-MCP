function createAttachedState({main, text, state}) {
    let historyRevision = 0;
    let commandRevision = 0;
    if (ATTACHED) bridge.hooks.push(Interceptor.attach(
        cls('VRoid.Studio', 'VRoid.Studio.Engine.Model').method('OnHistoryStatusUpdated').virtualAddress,
        {onLeave() { historyRevision++; }}));
    if (ATTACHED) for (const method of cls('VRoidCore', 'VRoidCore.Editing.Context').methods.filter(
        m => /^(Execute.*Command|Undo|Redo)/.test(m.name) && !m.virtualAddress.isNull())) {
        bridge.hooks.push(Interceptor.attach(method.virtualAddress, {onEnter() { historyRevision++; commandRevision++; }}));
    }
    const kernel = Process.getModuleByName('kernel32.dll');
    const getEnv = new NativeFunction(kernel.getExportByName('GetEnvironmentVariableW'), 'uint32', ['pointer','pointer','uint32']);
    const setEnv = new NativeFunction(kernel.getExportByName('SetEnvironmentVariableW'), 'bool', ['pointer','pointer']);
    const receiptKey = Memory.allocUtf16String('VROID_CHARACTER_MCP_PENDING_EDIT_V1');
    let review = null;
    function receipt() {
        const p = Memory.alloc(16384), n = getEnv(receiptKey, p, 8192);
        if (n >= 8192) throw Error('ATTACHED_EDIT_RECEIPT_TOO_LARGE');
        return n ? JSON.parse(p.readUtf16String(n)) : null;
    }
    function writeReceipt(value) {
        if (!setEnv(receiptKey, value ? Memory.allocUtf16String(JSON.stringify(value)) : NULL))
            throw Error('ATTACHED_EDIT_RECEIPT_WRITE_FAILED');
    }
    function snapshot() {
        const vm = main(), bus = vm.method('get_GlobalBus').invoke();
        const dialogs = vm.method('get_DialogProviderViewModel').invoke();
        const dialog = dialogs.method('get_Dialog').invoke();
        const notification = dialogs.method('get_ActiveNotificationDialog').invoke();
        const file = vm.field('_mainModel').value.field('currentFile').value;
        const screen = bus.method('get_ScreenNavigation').invoke().method('get_ActiveScreen').invoke();
        return {active_screen: screen.handle.isNull() ? null : screen.class.type.name,
            dialog: dialog.handle.isNull() ? null : dialog.class.type.name,
            notification: notification.handle.isNull() ? null : notification.class.type.name,
            progress_locked: vm.method('get_ProgressProviderViewModel').invoke().method('get_IsLocking').invoke(),
            popup_blocked: vm.method('get_PopupProviderViewModel').invoke().method('get_IsActiveBlocker').invoke(),
            file_path: file.handle.isNull() ? null : text(file.field('path').value),
            unsaved: vm.method('get_ActionHandler').invoke().method('get_IsUnSaved').invoke(),
            history_revision: historyRevision, command_revision: commandRevision, pending_edit: receipt()};
    }
    const readOnly = name => /^(status|native_png_status|task_status|get_|list_|inspect_|search_|custom_item_state|vrm_export_state|vrm_export_status|export_texture_|export_renderer_texture|attached_review)/.test(name);
    function guard(name) {
        if (!ATTACHED || readOnly(name) || name === 'attached_edit_finish') return;
        const s = snapshot();
        if (!s.active_screen || s.dialog || s.notification || s.progress_locked || s.popup_blocked)
            throw Error('ATTACHED_UI_BLOCKED: close the dialog or finish the manual operation in VRoid first');
        if (s.active_screen === 'VRoid.Studio.TextureEditorScreen.ViewModel' && !name.startsWith('attached_')
            && !/^(close_texture_editor|open_texture_editor|import_texture_layer|set_texture_layer_state|undo|redo|capture_texture_|pick_texture_)/.test(name))
            throw Error('CLOSE_TEXTURE_EDITOR_FIRST: finish the active canvas before changing model or screen');
        if (!name.startsWith('attached_')) review = null;
        const r = receipt();
        if (r && !name.startsWith('attached_')) {
            if (r.owner !== ATTACHED_OWNER_PID) throw Error('ATTACHED_EDIT_NEEDS_REVIEW');
            r.dispatches++; writeReceipt(r);
        }
    }
    function fingerprint() {
        const s = snapshot();
        const png = state.pngDecoder;
        const file = main().field('_mainModel').value.field('currentFile').value;
        const engine = file.handle.isNull() ? null : file.field('engine').value;
        const model = !engine || engine.handle.isNull() ? null : engine.method('get_Context').invoke().method('get_ActiveModel').invoke();
        return {state: s, file_identity: file.handle.toString(),
            engine_identity: engine ? engine.handle.toString() : null,
            model_identity: model ? model.handle.toString() : null, png_pending: png.pending,
            png_fatal: png.fatal, model_updates: bridge.modelUpdates};
    }
    function requireIdle() {
        const f = fingerprint(), s = f.state;
        if (!s.active_screen || s.dialog || s.notification || s.progress_locked || s.popup_blocked || f.png_pending || f.png_fatal)
            throw Error('ATTACHED_STATE_NOT_IDLE: finish the active operation before review');
        if (!main().field('_mainModel').value.field('currentFile').value.handle.isNull()) {
            const engine = main().field('_mainModel').value.field('currentFile').value.field('engine').value;
            if (!engine.handle.isNull() && !engine.method('get_Context').invoke().method('get_IsCommandExecutable').invoke())
                throw Error('ATTACHED_STATE_NOT_IDLE');
            if (main().field('_editModelTransform').value.method('get_IsUpdatingModel').invoke())
                throw Error('ATTACHED_STATE_NOT_IDLE');
        }
        return f;
    }
    return {snapshot, guard, operations: {
        attached_edit_begin(args) {
            if (!ATTACHED) throw Error('ATTACHED_ONLY');
            if (receipt()) throw Error('ATTACHED_EDIT_NEEDS_REVIEW: inspect get_attached_state before acknowledgment');
            const r = {id: Date.now().toString(36) + Math.random().toString(36).slice(2),
                owner: ATTACHED_OWNER_PID, tool: args.tool, started: new Date().toISOString(), dispatches: 0};
            writeReceipt(r); return r;
        },
        attached_edit_finish(args) {
            const r = receipt();
            if (!r || r.owner !== ATTACHED_OWNER_PID || r.id !== args.id) throw Error('ATTACHED_EDIT_RECEIPT_CHANGED');
            if (args.success || (!r.dispatches && !args.uncertain)) writeReceipt(null);
            return {needs_review: !!receipt()};
        },
        attached_review() {
            const f = requireIdle();
            const token = Date.now().toString(36) + Math.random().toString(36).slice(2);
            review = {token, fingerprint: JSON.stringify(f)};
            return {...f, recovery_token: token,
                instruction: 'Inspect pending tool, model, layers and created files. Acknowledgment only unblocks edits; it never retries, undoes or certifies the interrupted operation.'};
        },
        attached_acknowledge(args) {
            const f = requireIdle();
            if (!review || args.recovery_token !== review.token || JSON.stringify(f) !== review.fingerprint)
                throw Error('STALE_ATTACHED_REVIEW: inspect get_attached_state again');
            const prior = receipt(); writeReceipt(null); review = null;
            return {acknowledged: true, interrupted_edit: prior, replayed: false};
        },
    }};
}
