// Active-screen receipts are separate from edit-model tokens. Keep the observed
// screen alive while its token is valid so object-address reuse cannot match it.
function createSessionWorkflows({main, model, ui, retain, sessionTag, invalidateModel,
                                  nativeProfile, invoke, newModel, openFile, windowIdentity, png, guard, navigationRevision}) {
    const home = 'VRoid.Studio.StartScreen.ViewModel', edit = 'VRoid.Studio.EditRootScreen.ViewModel';
    let menu = null, generation = 0;
    function clearMenu() {
        if (menu) menu.pin.free();
        menu = null;
    }
    function inspect() {
        const vm = main();
        const screen = vm.method('get_GlobalBus').invoke().method('get_ScreenNavigation').invoke()
            .method('get_ActiveScreen').invoke();
        const file = vm.field('_mainModel').value.field('currentFile').value;
        const s = ui();
        const active = screen.handle.isNull() ? null : screen.class.type.name;
        const blocked = !active || s.dialog || s.notification || s.progress_locked || s.popup_blocked;
        let window = null, startMode = null;
        if (active === home && !blocked && file.handle.isNull() && nativeProfile()?.session &&
                screen.method('get_MainViewModel').invoke().handle.equals(vm.handle)) {
            const mode = screen.method('get_StartScreenMode').invoke();
            const value=mode.field('value__').value, type=mode.class || mode.type.class;
            startMode=type.fields?.find(f=>f.isStatic && (typeof f.value==='number'?f.value:f.value.field('value__').value)===value)?.name || String(value);
            const selection = (mode.class || mode.type.class).field('ModelSelection').value;
            if (mode.field('value__').value === selection.field('value__').value) window = windowIdentity();
        }
        const rev = navigationRevision();
        if (!window || menu && (!menu.screen.handle.equals(screen.handle) || menu.window !== window || menu.rev !== rev))
            clearMenu();
        if (window && !menu) {
            invalidateModel();
            menu = {window, screen, rev, pin:retain(screen), token:sessionTag + ':menu:' + ++generation};
        }
        return {vm, screen, file, s, active, blocked, startMode};
    }
    function view() {
        const {file, s, active, screen, startMode} = inspect();
        let rootActive = false;
        if (active === edit) {
            try { rootActive = model().root.handle.equals(screen.handle); }
            catch (_) { rootActive = null; }
        }
        return {active_screen:active, model_open:!file.handle.isNull(), file_path:s.file_path,
            edit_root_active:rootActive,
            dirty:file.handle.isNull() ? null : s.unsaved, menu_token:menu?.token || null,
            menu_ready:!!menu, start_screen_mode:startMode};
    }
    function verify(name, args, dispatching) {
        if (!nativeProfile()?.session) throw Error('UNVERIFIED_SESSION_CALLBACKS');
        const {vm, screen, s, active, blocked} = inspect();
        const window = windowIdentity();
        if (!window || window !== String(args.window) || blocked) throw Error('SESSION_WINDOW_BLOCKED_OR_CHANGED');
        const decoder = png();
        if (!decoder.installed || decoder.pending !== 0 || decoder.fatal) throw Error('SESSION_NATIVE_WORK_PENDING');
        if (ATTACHED && (dispatching
                ? !s.pending_edit || s.pending_edit.owner !== ATTACHED_OWNER_PID ||
                    s.pending_edit.tool !== name || !args.receipt_id || s.pending_edit.id !== args.receipt_id
                : s.pending_edit)) throw Error('ATTACHED_EDIT_NEEDS_REVIEW');
        if (name === 'create_from_menu' || name === 'open_from_menu') {
            if (active !== home || !menu || !args.expected_menu || menu.token !== args.expected_menu)
                throw Error('STALE_MENU: request current status');
            if (ATTACHED && args.confirm_attached !== true) throw Error('CONFIRM_ATTACHED_REQUIRED');
            if (name === 'create_from_menu' && !['F00','M00'].includes(args.variant)) throw Error('UNSUPPORTED_VARIANT');
            return {vm};
        }
        if (active !== edit || !args.expected_model) throw Error('SESSION_EDIT_ROOT_REQUIRED');
        const m = model(args.expected_model);
        if (!m.root.handle.equals(screen.handle) || m.root.field('obsoleteLegacyPhotoBoothViewModel').value.method('get_IsActive').invoke())
            throw Error('SESSION_EDIT_ROOT_CHANGED');
        if (!m.context.method('get_IsCommandExecutable').invoke() ||
                vm.field('_editModelTransform').value.method('get_IsUpdatingModel').invoke())
            throw Error('SESSION_MODEL_BUSY');
        if (s.unsaved !== true && s.unsaved !== false) throw Error('UNKNOWN_DIRTY_STATE');
        if (s.unsaved && args.discard_unsaved !== true) throw Error('EXPLICIT_DISCARD_REQUIRED');
        if (name === 'exit_vroid' && ATTACHED && args.close_attached !== true) throw Error('CLOSE_ATTACHED_REQUIRED');
        return {vm, m};
    }
    function perform(name, args) {
        let owner;
        try { owner = verify(name, args, true); }
        catch (error) { return {rejected:true, error:String(error)}; }
        try { guard(name); }
        catch (error) {
            if (error.attached_guard_prewrite) return {rejected:true, error:String(error)};
            throw error;
        }
        if (name === 'return_to_main_menu') {
            invoke(owner.m.root, '<BackToModelSelect>g__BackToStartScreen|103_0');
            invalidateModel();
        } else if (name === 'exit_vroid') {
            invoke(owner.vm, '<WantsToQuitHandler>g__Quit|61_0');
        } else {
            clearMenu();
            if (name === 'create_from_menu') return newModel(args);
            return openFile(args);
        }
        return {requested:true};
    }
    return {view, clearMenu, operations:{
        get_session_preflight(args) { verify(args.operation, args); return {verified:true}; },
        return_to_main_menu: args => perform('return_to_main_menu', args),
        exit_vroid: args => perform('exit_vroid', args),
        create_from_menu: args => perform('create_from_menu', args),
        open_from_menu: args => perform('open_from_menu', args),
    }};
}

function sessionModelVariant(context, text) {
    let object = context;
    for (const getter of ['get_ActiveModel','get_BaseCollection','get_Global',
                          'get_BlendShapeSynthesisParameters','get_BlendShapeSynthesisType']) {
        if (!object || object.handle.isNull()) return null;
        object = object.tryMethod(getter)?.invoke();
    }
    return text(object);
}

function sessionModelFields(context, text, profile) {
    function observed(read) {
        try { return read() ?? null; }
        catch (_) { return null; }  // Optional status fields cannot hide existing model readiness.
    }
    return {
        model_type:observed(() => text(context.method('get_ModelType').invoke())),
        model_variant:profile?.session ? observed(() => sessionModelVariant(context,text)) : null,
        is_editing:observed(() => context.method('get_IsEditing').invoke()),
        can_undo:observed(() => context.method('get_CanUndo').invoke()),
        can_redo:observed(() => context.method('get_CanRedo').invoke()),
    };
}

function sessionWindowIdentity() {
    const user = Process.getModuleByName('user32.dll');
    const fn = (name, result, args) => new NativeFunction(user.getExportByName(name), result, args);
    const find = fn('FindWindowExW','pointer',['pointer','pointer','pointer','pointer']);
    const owner = fn('GetWindowThreadProcessId','uint32',['pointer','pointer']);
    const enabled = fn('IsWindowEnabled','bool',['pointer']);
    const popup = fn('GetLastActivePopup','pointer',['pointer']);
    const pid = Memory.alloc(4), name = Memory.allocUtf16String('UnityWndClass');
    let match = null;
    for (let h = find(NULL,NULL,name,NULL); !h.isNull(); h = find(NULL,h,name,NULL)) {
        const thread = owner(h,pid);
        if (pid.readU32() !== Process.id) continue;
        if (match || thread !== state.mainThread || !enabled(h) || !popup(h).equals(h)) return null;
        match = h.toString();
    }
    return match;
}
