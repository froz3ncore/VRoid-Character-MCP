// Keep native texture storage alive for the whole PNG decode. The 2.14 async
// decoder retains a NativeArray view into Texture2D storage across a worker job.
// It can write through that view after native asset cleanup invalidates it.
function createNativePngQueue(api) {
    const jobs = [], stats = {decoded: 0, delivered: 0, failed: 0, fatal: null};
    let pumping = false;
    return {
        request(request) {
            const release = api.holdRequest(request);
            jobs.push({request, release, frame: api.frame() + 1});
        },
        pump() {
            if (pumping || stats.fatal) return;
            pumping = true;
            // Snapshot the ready batch: callbacks may enqueue more native loads.
            const ready = [];
            while (ready.length < 4 && jobs.length && jobs[0].frame <= api.frame()) ready.push(jobs.shift());
            while (ready.length) {
                const job = ready.shift();
                let releaseValue = null;
                try {
                    const result = api.decode(job.request);
                    stats.decoded++;
                    if (result.failed) stats.failed++;
                    releaseValue = api.holdValue(result.value);
                    api.deliver(job.request, result);
                    stats.delivered++;
                } catch (error) {
                    stats.fatal = String(error);
                    jobs.unshift(...ready.splice(0));
                } finally {
                    if (releaseValue) releaseValue();
                    job.release();
                }
                if (stats.fatal) break;
            }
            pumping = false;
        },
        status() { return {installed: true, mode: 'native_sync_deferred_callbacks',
            pending: jobs.length, ...stats}; },
    };
}

function installNativePngDecoder({cls, retain, frame, mainThread}) {
    const png = cls('VRoidCore', 'VRoidCore.Common.PNGUtil');
    const sync = png.method('LoadPNGToRGBATexture2D');
    const async = png.method('LoadPNGToRGBATexture2DAsync');
    if (sync.returnType.name !== 'UnityEngine.Texture2D' || sync.parameters.length !== 4 ||
        async.returnType.name !== 'System.Void' || async.parameters.length !== 6)
        throw Error('UNSUPPORTED_NATIVE_PNG_SIGNATURE');
    const invoke = new NativeFunction(Il2Cpp.module.getExportByName('il2cpp_runtime_invoke'),
        'pointer', ['pointer','pointer','pointer','pointer'], {exceptions:'propagate'});
    function hold(objects) {
        const handles = [];
        try {
            for (const object of objects) if (!object.handle.isNull()) handles.push(retain(object));
        } catch (error) { handles.forEach(h => h.free()); throw error; }
        return () => handles.forEach(h => h.free());
    }
    const queue = createNativePngQueue({frame,
        holdRequest: r => hold([r.bytes, r.ok, r.fail]),
        holdValue: value => hold([value]),
        decode(request) {
            if (Process.getCurrentThreadId() !== mainThread()) throw Error('PNG_DECODE_NOT_ON_MAIN_THREAD');
            const flags = [request.mip, request.linear, request.unreadable].map(value => {
                const slot = Memory.alloc(1); slot.writeU8(value ? 1 : 0); return slot;
            });
            const args = Memory.alloc(4 * Process.pointerSize), exception = Memory.alloc(Process.pointerSize);
            exception.writePointer(NULL);
            [request.bytes.handle, ...flags].forEach((p,i) => args.add(i * Process.pointerSize).writePointer(p));
            const texture = invoke(sync.handle, NULL, args, exception);
            const failed = !exception.readPointer().isNull();
            const value = new Il2Cpp.Object(failed ? exception.readPointer() : texture);
            if (value.handle.isNull()) throw Error('PNG_DECODE_RETURNED_NULL_WITHOUT_EXCEPTION');
            return {failed, value};
        },
        deliver(request, result) {
            const callback = result.failed ? request.fail : request.ok;
            if (callback.handle.isNull()) throw Error('PNG_NATIVE_CALLBACK_MISSING');
            const args = Memory.alloc(Process.pointerSize), exception = Memory.alloc(Process.pointerSize);
            args.writePointer(result.value.handle); exception.writePointer(NULL);
            invoke(callback.method('Invoke', 1).handle, callback.handle, args, exception);
            if (!exception.readPointer().isNull())
                throw Error('PNG_NATIVE_CALLBACK_FAILED: ' + new Il2Cpp.Object(exception.readPointer()).method('ToString').invoke().content);
        },
    });
    // This remains asynchronous to its caller, but never exposes a Unity
    // texture's raw storage to a background decoder. No image is resampled.
    async.implementation = function (bytes, mip, linear, unreadable, ok, fail) {
        queue.request({bytes, mip, linear, unreadable, ok, fail});
    };
    return queue;
}
