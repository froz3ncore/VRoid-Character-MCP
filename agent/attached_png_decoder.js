// Late attachment must leave every submitted completion owned by Unity, even
// when the host is terminated. Never enqueue these callbacks in a JS array.
function installAttachedPngDecoder({cls, retain, mainThread}) {
    const png = cls('VRoidCore', 'VRoidCore.Common.PNGUtil');
    const sync = png.method('LoadPNGToRGBATexture2D');
    const async = png.method('LoadPNGToRGBATexture2DAsync');
    const closureType = Il2Cpp.domain.assembly('VRoidCore').image.classes.find(
        c => c.type.name === 'VRoidCore.Common.PNGUtil.<>c__DisplayClass7_0');
    if (!closureType || async.parameters.length !== 6 || async.returnType.name !== 'System.Void'
        || sync.parameters.length !== 4) throw Error('UNSUPPORTED_ATTACHED_PNG_SIGNATURE');
    const invoke = new NativeFunction(Il2Cpp.module.getExportByName('il2cpp_runtime_invoke'),
        'pointer', ['pointer','pointer','pointer','pointer'], {exceptions:'propagate'});
    const setReference = new NativeFunction(Il2Cpp.module.getExportByName('il2cpp_field_set_value_object'),
        'void', ['pointer','pointer','pointer']);
    function assign(object, name, value) {
        // The bridge's instance field setter is a raw memory write. Use the
        // IL2CPP setter so Unity's incremental GC sees these managed references.
        setReference(object.handle, object.field(name).handle, value.handle);
    }
    const pending = new Set(), stats = {decoded: 0, delivered: 0, failed: 0, fatal: null};
    // Workers already started before attachment still use the original decoder.
    // Pin and wait for those Tasks; replacing the entry point cannot cancel them.
    const legacy = Il2Cpp.gc.choose(Il2Cpp.corlib.class('System.Threading.Tasks.Task')).filter(task => {
        if (task.method('get_IsCompleted').invoke()) return false;
        const action = task.field('m_action').value;
        if (action.handle.isNull()) return false;
        const target = action.method('get_Target').invoke();
        return !target.handle.isNull() && target.class.handle.equals(closureType.handle);
    }).map(task => ({task, hold: retain(task)}));
    const completion = Interceptor.attach(closureType.method('<LoadPNGToRGBATexture2DAsync>b__1').virtualAddress, {
        onEnter(args) { this.key = args[0].toString(); },
        onLeave() { if (pending.delete(this.key)) stats.delivered++; },
    });
    function nativeCall(method, self, values) {
        const argv = Memory.alloc(Math.max(1, values.length) * Process.pointerSize);
        const exception = Memory.alloc(Process.pointerSize); exception.writePointer(NULL);
        values.forEach((p,i) => argv.add(i * Process.pointerSize).writePointer(p));
        const result = invoke(method.handle, self, argv, exception);
        return {result, exception: exception.readPointer()};
    }
    async.implementation = function(bytes, mip, linear, unreadable, ok, fail) {
        const holds = [];
        try {
            if (Process.getCurrentThreadId() !== mainThread()) throw Error('PNG_DECODE_NOT_ON_MAIN_THREAD');
            for (const obj of [bytes, ok, fail]) if (!obj.handle.isNull()) holds.push(retain(obj));
            // b__1 performs the final Apply with the caller's readability flag.
            const flags = [mip, linear, false].map(value => {
                const p = Memory.alloc(1); p.writeU8(value ? 1 : 0); return p;
            });
            const decoded = nativeCall(sync, NULL, [bytes.handle, ...flags]);
            stats.decoded++;
            if (!decoded.exception.isNull()) {
                stats.failed++;
                if (fail.handle.isNull()) throw Error('PNG_NATIVE_ERROR_CALLBACK_MISSING');
                const notified = nativeCall(fail.method('Invoke', 1), fail.handle, [decoded.exception]);
                if (!notified.exception.isNull()) throw Error('PNG_NATIVE_ERROR_CALLBACK_FAILED');
                return;
            }
            if (decoded.result.isNull()) throw Error('PNG_DECODE_RETURNED_NULL');
            const texture = new Il2Cpp.Object(decoded.result); holds.push(retain(texture));
            const closure = closureType.new(); holds.push(retain(closure));
            assign(closure, 'texture2D', texture);
            closure.field('mipChain').value = mip;
            closure.field('makeNoLongerReadable').value = unreadable;
            assign(closure, 'onSuccess', ok);
            assign(closure, 'onError', fail);
            const callback = Il2Cpp.corlib.class('System.Delegate').method('CreateDelegate')
                .overload('System.Type','System.Object','System.Reflection.MethodInfo').invoke(
                    Il2Cpp.corlib.class('System.Threading.SendOrPostCallback').type.object,
                    closure, closureType.method('<LoadPNGToRGBATexture2DAsync>b__1').object);
            holds.push(retain(callback));
            const context = Il2Cpp.corlib.class('System.Threading.SynchronizationContext').method('get_Current').invoke();
            if (context.handle.isNull()) throw Error('UNITY_SYNCHRONIZATION_CONTEXT_MISSING');
            pending.add(closure.handle.toString());
            context.method('Post').invoke(callback, NULL);
        } catch (error) {
            stats.fatal = String(error);
            send({event: 'attached-png-error', error: String(error)});
        } finally { for (const handle of holds) handle.free(); }
    };
    return {
        pump() {},
        status() {
            for (let i = legacy.length - 1; i >= 0; i--) {
                if (legacy[i].task.method('get_IsCompleted').invoke()) {
                    legacy[i].hold.free(); legacy.splice(i, 1);
                }
            }
            return {installed: true, mode: 'unity_owned_callbacks', pending: pending.size + legacy.length,
                legacy_workers: legacy.length, ...stats};
        },
        release() {
            // Managed Post owns the texture/delegate until completion. Unloading
            // the agent removes only the hook and future entry-point replacement.
            async.revert(); completion.detach();
            for (const job of legacy) job.hold.free(); legacy.length = 0;
        },
    };
}
