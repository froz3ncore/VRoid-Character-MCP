// Main-thread bridge for the disposable VRoid copy.
//
// Managed objects may only be touched from Unity's main thread, so every call
// from Python is queued and executed from the frame callback. This file owns
// that queue, the GC handles that keep native objects alive, and the two rpc
// entry points the Python side uses.
//
// Contract (consumed by vroid_mcp/runtime.py):
//   rpc.health()            -> {ready, error, pid, frame}
//   rpc.call(name, args)    -> whatever the dispatched operation returns
//   events: ready / init-error / background-scope-error

'use strict';

const bridge = {
    ready: false,
    error: null,
    mainThread: 0,
    frame: 0,
    modelUpdates: 0,
    retained: new Map(),
    hooks: [],
    backlog: [],
    executing: false,
    background: null,
    backgroundScope: null,
    backgroundHook: null,
    pumpHooks: [],
    lastExec: 0,
    postThreadMessage: null,
};

const QUEUE_LIMIT = 32;
const JOB_TIMEOUT_MS = 12000;

function nativeClass(assembly, name) {
    return Il2Cpp.domain.assembly(assembly).image.class(name);
}

// Compatibility surface for the modules that have not been rewritten yet
// (operations, parameters, wear, textures, ...). They address `cls`, `retain`
// and `state` directly because the previous bridge published them as globals.
// Keeping the aliases in one place lets those modules be replaced one at a time
// without changing a hundred call sites; delete this block with the last one.
const cls = nativeClass;
const retain = function (object) { return keep(object); };
const state = {
    refs: {},
    get frame() { return bridge.frame; },
    get mainThread() { return bridge.mainThread; },
};

// Unity 6 hands out pointer-sized GC handles while the bridge typedefs them as
// 32-bit. Verify the round trip so a future bridge cannot silently truncate.
function createHandleKeeper() {
    const gcNew = new NativeFunction(Il2Cpp.module.getExportByName('il2cpp_gchandle_new'),
                                     'pointer', ['pointer', 'bool']);
    const gcGet = new NativeFunction(Il2Cpp.module.getExportByName('il2cpp_gchandle_get_target'),
                                     'pointer', ['pointer']);
    const gcFree = new NativeFunction(Il2Cpp.module.getExportByName('il2cpp_gchandle_free'),
                                      'void', ['pointer']);
    return function keep(object) {
        const handle = gcNew(object.handle, 0);
        if (!gcGet(handle).equals(object.handle)) throw new Error('GC_HANDLE_ABI_MISMATCH');
        let released = false;
        return {
            handle: handle,
            free() {
                if (released) return;
                released = true;
                gcFree(handle);
            },
        };
    };
}

let keep = null;

function schedule(work, wake = false) {
    if (!bridge.ready) return Promise.reject(new Error(bridge.error || 'BRIDGE_NOT_READY'));
    if (bridge.backlog.length >= QUEUE_LIMIT) return Promise.reject(new Error('QUEUE_FULL'));
    return new Promise(function (resolve, reject) {
        const job = {
            work: work,
            resolve: resolve,
            reject: reject,
            expiresAt: Date.now() + JOB_TIMEOUT_MS,
            wake: wake,
        };
        job.timer = setTimeout(function () {
            const index = bridge.backlog.indexOf(job);
            if (index < 0) return;
            bridge.backlog.splice(index, 1);
            reject(new Error('MAIN_THREAD_TIMEOUT: not executed'));
        }, JOB_TIMEOUT_MS);
        bridge.backlog.push(job);
        const wakeUp = function () {
            if (!bridge.backlog.includes(job) || !bridge.postThreadMessage) return;
            bridge.postThreadMessage(bridge.mainThread, 0, NULL, NULL);
            setTimeout(wakeUp, 100);
        };
        if (wake) wakeUp();
    });
}

// One job per frame keeps a slow operation from stalling the editor, and the
// re-entrancy flag stops a job that pumps the frame callback from nesting.
function drainOne() {
    if (Process.getCurrentThreadId() !== bridge.mainThread || bridge.executing) return;
    bridge.frame += 1;
    bridge.lastExec = Date.now();
    drainJob();
}

function drainJob() {
    const job = bridge.backlog.shift();
    if (!job) return;
    clearTimeout(job.timer);
    bridge.executing = true;
    try {
        if (Date.now() > job.expiresAt) throw new Error('MAIN_THREAD_TIMEOUT: not executed');
        if (Il2Cpp.currentThread === null || Il2Cpp.currentThread.id !== bridge.mainThread) {
            throw new Error('UNREGISTERED_THREAD');
        }
        const result = job.work();
        if (result instanceof Promise) throw new Error('ASYNC_MANAGED_CALL_FORBIDDEN');
        job.resolve(result);
    } catch (error) {
        job.reject(error);
    } finally {
        bridge.executing = false;
    }
}

// Late attachment cannot rely on constructors that already ran. These helpers
// adapt the approach in Karylcode/VRoid-MCP baaa94e (MIT; see licenses/).
function unityWindowThread() {
    const user32 = Process.getModuleByName('user32.dll');
    const find = new NativeFunction(user32.getExportByName('FindWindowExW'), 'pointer', ['pointer','pointer','pointer','pointer']);
    const ownerThread = new NativeFunction(user32.getExportByName('GetWindowThreadProcessId'), 'uint32', ['pointer','pointer']);
    const name = Memory.allocUtf16String('UnityWndClass'), owner = Memory.alloc(4);
    for (let window = find(NULL, NULL, name, NULL); !window.isNull(); window = find(NULL, window, name, NULL)) {
        const thread = ownerThread(window, owner);
        if (owner.readU32() === Process.id) return thread;
    }
    throw Error('UNITY_WINDOW_NOT_FOUND');
}

function pumpAttached() {
    if (Process.getCurrentThreadId() !== bridge.mainThread || bridge.executing ||
        Date.now() - bridge.lastExec < 250 || !bridge.backlog[0]?.wake) return;
    drainJob();
}

function installPump() {
    const user32 = Process.getModuleByName('user32.dll');
    bridge.postThreadMessage = new NativeFunction(user32.getExportByName('PostThreadMessageW'), 'bool', ['uint32','uint32','pointer','pointer']);
    for (const name of ['PeekMessageW','PeekMessageA','GetMessageW','GetMessageA']) {
        const address = user32.findExportByName(name);
        if (address) bridge.pumpHooks.push(Interceptor.attach(address, {onLeave: pumpAttached}));
    }
}

function rememberSingleton(name, instance) {
    const previous = bridge.retained.get(name);
    if (previous) previous.free();
    bridge.retained.set(name, keep(instance));
    state.refs[name] = instance.handle.toString();
}

function adoptRunning() {
    const find = name => {
        const type = nativeClass('VRoid.Studio', name);
        return Il2Cpp.gc.choose(type).filter(o => o.class.handle.equals(type.handle));
    };
    const mainName = 'VRoid.Studio.MainViewModel', rootName = 'VRoid.Studio.EditRootScreen.ViewModel';
    const mains = find(mainName);
    if (mains.length !== 1) throw Error('MAIN_VIEW_MODEL_NOT_FOUND: ' + mains.length);
    rememberSingleton(mainName, mains[0]);
    const file = mains[0].field('_mainModel').value.field('currentFile').value;
    const engine = file.handle.isNull() ? null : file.field('engine').value;
    const root = engine && find(rootName).find(o => o.field('_engineModel').value.handle.equals(engine.handle));
    if (root) rememberSingleton(rootName, root);
    const navigation = mains[0].method('get_GlobalBus').invoke().method('get_ScreenNavigation').invoke();
    const screen = navigation.method('get_ActiveScreen').invoke();
    if (screen.class.type.name === 'VRoid.Studio.XWear.Edit.ViewModel') {
        rememberSingleton('VRoid.Studio.XWear.Edit.ViewModel', screen);
    }
    const utility = nativeClass('VRoid.UI', 'VRoid.UI.Util.RunInBackgroundUtil');
    const binding = Il2Cpp.exports.resolveInternalCall(Memory.allocUtf8String('UnityEngine.Application::set_runInBackground'));
    if (binding.isNull()) throw Error('BACKGROUND_BINDING_MISSING');
    const scope = utility.method('EnableRunInBackgroundScoped').invoke();
    bridge.backgroundScope = scope;
    bridge.background = keep(scope);
    bridge.backgroundHook = Interceptor.attach(binding, {onEnter(args) { args[0] = ptr(1); }});
    for (const hook of bridge.pumpHooks) hook.detach();
    bridge.pumpHooks = [];
    return {main_view_model: true, edit_root: !!root, wear_active: screen.class.type.name === 'VRoid.Studio.XWear.Edit.ViewModel'};
}

function releaseAttached() {
    if (bridge.backgroundHook) bridge.backgroundHook.detach();
    bridge.backgroundHook = null;
    if (bridge.backgroundScope) {
        const scope = bridge.backgroundScope;
        bridge.backgroundScope = null;
        try { (scope.tryMethod('Dispose') ?? scope.method('System.IDisposable.Dispose')).invoke(); }
        finally { if (bridge.background) bridge.background.free(); bridge.background = null; }
    }
    for (const handle of bridge.retained.values()) handle.free();
    bridge.retained.clear();
    state.refs = {};
    return {released: true};
}

// The editor singletons are recreated whenever a file is opened. Retaining each
// instance as it is constructed is cheaper and safer than searching for it.
function retainEditorSingletons() {
    const wanted = [
        'VRoid.Studio.MainViewModel',
        'VRoid.Studio.EditRootScreen.ViewModel',
        'VRoid.Studio.XWear.Edit.ViewModel',
    ];
    for (const className of wanted) {
        const type = nativeClass('VRoid.Studio', className);
        const constructors = type.methods.filter(function (method) {
            return method.name === '.ctor' && !method.virtualAddress.isNull();
        });
        for (const ctor of constructors) {
            bridge.hooks.push(Interceptor.attach(ctor.virtualAddress, {
                onEnter(args) { this.self = args[0]; },
                onLeave() {
                    if (Process.getCurrentThreadId() !== bridge.mainThread) return;
                    const instance = new Il2Cpp.Object(this.self);
                    if (!instance.class.handle.equals(type.handle)) return;
                    rememberSingleton(className, instance);
                },
            }));
        }
    }
}

// VRoid pauses itself when the window loses focus. A background job that stops
// running mid-task would leave the caller waiting, so hold the flag on.
function holdRunInBackground() {
    const utility = nativeClass('VRoid.UI', 'VRoid.UI.Util.RunInBackgroundUtil');
    const binding = Il2Cpp.exports.resolveInternalCall(
        Memory.allocUtf8String('UnityEngine.Application::set_runInBackground'));
    if (binding.isNull()) throw new Error('BACKGROUND_BINDING_MISSING');
    bridge.hooks.push(Interceptor.attach(utility.method('Initialize').virtualAddress, {
        onLeave() {
            if (Process.getCurrentThreadId() !== bridge.mainThread) return;
            // The native binding is hooked rather than the managed property:
            // IL2CPP may inline the property wrapper away.
            bridge.hooks.push(Interceptor.attach(binding, {
                onEnter(args) { args[0] = ptr(1); },
            }));
            try {
                const scope = utility.method('EnableRunInBackgroundScoped').invoke();
                bridge.background = keep(scope);
            } catch (error) {
                send({ event: 'background-scope-error', error: String(error) });
            }
        },
    }));
}

function countModelUpdates() {
    bridge.hooks.push(Interceptor.attach(
        nativeClass('VRoid.Studio', 'VRoid.Studio.Engine.Model').method('OnModelUpdateComplete').virtualAddress,
        { onLeave() { bridge.modelUpdates += 1; } }));
}

Il2Cpp.perform(function () {
    if (Il2Cpp.unityVersion !== '6000.0.62f1') {
        throw new Error('UNTESTED_UNITY_VERSION: ' + Il2Cpp.unityVersion);
    }
    bridge.mainThread = ATTACHED ? unityWindowThread() : Process.getCurrentThreadId();
    keep = createHandleKeeper();
    // Frames arrive through the synchronization context; attaching on leave
    // means the queue drains after the frame's own work, not in the middle.
    bridge.hooks.push(Interceptor.attach(
        nativeClass('UnityEngine.CoreModule', 'UnityEngine.UnitySynchronizationContext')
            .method('Exec').virtualAddress,
        { onLeave: drainOne }));
    retainEditorSingletons();
    if (ATTACHED) installPump(); else holdRunInBackground();
    countModelUpdates();
    bridge.ready = true;
    send({ event: 'ready', pid: Process.id, unity: Il2Cpp.unityVersion, main_thread: bridge.mainThread });
}, ATTACHED ? 'free' : 'main').catch(function (error) {
    bridge.error = String(error);
    send({ event: 'init-error', error: String(error) });
});

rpc.exports = {
    health() {
        return { ready: bridge.ready, error: bridge.error, pid: Process.id, frame: bridge.frame };
    },
    call(name, args) {
        return schedule(function () { return vroid.dispatch(name, args || {}); });
    },
    adopt() { return schedule(adoptRunning, true); },
    release() { if (ATTACHED && bridge.pumpHooks.length === 0) installPump(); return schedule(releaseAttached, true); },
};
