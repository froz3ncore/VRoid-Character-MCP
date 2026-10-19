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

function schedule(work) {
    if (!bridge.ready) return Promise.reject(new Error(bridge.error || 'BRIDGE_NOT_READY'));
    if (bridge.backlog.length >= QUEUE_LIMIT) return Promise.reject(new Error('QUEUE_FULL'));
    return new Promise(function (resolve, reject) {
        const job = {
            work: work,
            resolve: resolve,
            reject: reject,
            expiresAt: Date.now() + JOB_TIMEOUT_MS,
        };
        job.timer = setTimeout(function () {
            const index = bridge.backlog.indexOf(job);
            if (index < 0) return;
            bridge.backlog.splice(index, 1);
            reject(new Error('MAIN_THREAD_TIMEOUT: not executed'));
        }, JOB_TIMEOUT_MS);
        bridge.backlog.push(job);
    });
}

// One job per frame keeps a slow operation from stalling the editor, and the
// re-entrancy flag stops a job that pumps the frame callback from nesting.
function drainOne() {
    if (Process.getCurrentThreadId() !== bridge.mainThread || bridge.executing) return;
    bridge.frame += 1;
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
                    const previous = bridge.retained.get(className);
                    if (previous) previous.free();
                    bridge.retained.set(className, keep(instance));
                    state.refs[className] = instance.handle.toString();
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
    bridge.mainThread = Process.getCurrentThreadId();
    keep = createHandleKeeper();
    // Frames arrive through the synchronization context; attaching on leave
    // means the queue drains after the frame's own work, not in the middle.
    bridge.hooks.push(Interceptor.attach(
        nativeClass('UnityEngine.CoreModule', 'UnityEngine.UnitySynchronizationContext')
            .method('Exec').virtualAddress,
        { onLeave: drainOne }));
    retainEditorSingletons();
    holdRunInBackground();
    countModelUpdates();
    bridge.ready = true;
    send({ event: 'ready', pid: Process.id, unity: Il2Cpp.unityVersion, main_thread: bridge.mainThread });
}, 'main').catch(function (error) {
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
};
