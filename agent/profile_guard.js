// Profile and filesystem guard for the disposable VRoid copy.
//
// This process must behave as if %USERPROFILE% were the lab directory and as if
// nothing outside that directory existed. VRoid, Unity and the platform layer
// all resolve absolute paths early and cache them, so the guard works at the
// Win32 boundary instead of in managed code.
//
// Three rules decide every call:
//   1. paths under the machine profile are remapped into the lab profile;
//   2. writes, renames, deletes and copies that still point outside the lab are
//      sent to a non-existent placeholder so the call fails cleanly;
//   3. anything that could escape the copy (a child process, a model file read
//      from the real profile, the VRoid registry hive) is refused and reported.
//
// This is a process-local guard, not an operating-system sandbox: it protects
// the user's own installation from being touched by mistake, nothing more.

'use strict';

const probe = PROBE;
const sep = '\\';

function toComparable(value) {
    return value.replace(/^\\\\\?\\/, '').replace(/\//g, sep).toLowerCase();
}

const labRoot = toComparable(probe.root);
const profileRoot = toComparable(probe.originalProfile);
const deniedPath = probe.root + sep + 'blocked-outside-workspace' + sep + 'denied';
const keptHooks = [];
const reported = new Set();

function inLab(value) {
    const comparable = toComparable(value);
    return comparable === labRoot || comparable.startsWith(labRoot + sep);
}

// Unity caches %USERPROFILE% before the managed layer starts. Anything that
// still refers to the machine profile is served from the lab profile instead.
function remapProfile(value) {
    if (!value) return value;
    const plain = value.replace(/^\\\\\?\\/, '').replace(/\//g, sep);
    if (inLab(plain)) return plain;
    const comparable = toComparable(plain);
    if (comparable === profileRoot || comparable.startsWith(profileRoot + sep)) {
        return probe.root + sep + 'profile' + plain.slice(probe.originalProfile.length);
    }
    return plain;
}

function report(kind, path) {
    const key = kind + '|' + path;
    if (reported.has(key)) return;
    reported.add(key);
    send({ kind: kind, path: path });
}

function isDevicePath(value) {
    return value.startsWith('\\\\.\\');
}

function replaceArgument(context, args, index, value) {
    context.allocated = context.allocated || [];
    const buffer = Memory.allocUtf16String(value);
    context.allocated.push(buffer);
    args[index] = buffer;
}

function readArgument(args, index) {
    return args[index].isNull() ? '' : args[index].readUtf16String();
}

// A path is remapped first and then judged: a location that only looked outside
// the lab because of the profile prefix is not a violation.
function guardPathArgument(context, args, index, options) {
    const original = readArgument(args, index);
    let value = remapProfile(original);
    if (value !== original) replaceArgument(context, args, index, value);
    if (!value || inLab(value) || isDevicePath(value)) return value;
    if (options.blockExternalModel && /\.vroid(?:$|[.\\])/i.test(value)) {
        report('blocked-external-model', value);
        replaceArgument(context, args, index, deniedPath);
        return deniedPath;
    }
    if (options.blockWrites) {
        report('redirected-outside-write', value);
        replaceArgument(context, args, index, deniedPath);
        return deniedPath;
    }
    return value;
}

const kernel32 = Process.getModuleByName('kernel32.dll');

// ---------------------------------------------------------------- child spawn
// A relaunch or helper process would escape this guard, and this copy never
// needs one. Replace instead of attach: the call must fail, not succeed quietly.
for (const name of ['CreateProcessW', 'CreateProcessA']) {
    const address = kernel32.findExportByName(name);
    if (!address) continue;
    const refusal = new NativeCallback(function () {
        this.lastError = 5;
        report('blocked-child-process', name);
        return 0;
    }, 'bool', ['pointer', 'pointer', 'pointer', 'pointer', 'bool', 'uint32',
                'pointer', 'pointer', 'pointer', 'pointer']);
    keptHooks.push(refusal);
    Interceptor.replace(address, refusal);
}

// --------------------------------------------------------------- file writes
// CreateFileW carries the access mask and the disposition, so intent has to be
// read from the arguments rather than assumed from the API name.
const createFile = kernel32.findExportByName('CreateFileW');
if (createFile) {
    keptHooks.push(Interceptor.attach(createFile, {
        onEnter(args) {
            const original = readArgument(args, 0);
            const mapped = remapProfile(original);
            if (mapped !== original) replaceArgument(this, args, 0, mapped);
            if (!mapped || inLab(mapped) || isDevicePath(mapped)) return;
            const requestsWrite = (args[1].toUInt32() & 0x400d0116) !== 0;
            const creates = args[4].toUInt32() !== 3;
            if (requestsWrite || creates || /\.vroid(?:$|[.\\])/i.test(mapped)) {
                report(requestsWrite || creates ? 'redirected-outside-write' : 'blocked-external-model', mapped);
                replaceArgument(this, args, 0, deniedPath);
            }
        }
    }));
}

for (const name of ['DeleteFileW', 'CreateDirectoryW', 'RemoveDirectoryW']) {
    const address = kernel32.findExportByName(name);
    if (!address) continue;
    keptHooks.push(Interceptor.attach(address, {
        onEnter(args) {
            guardPathArgument(this, args, 0, { blockWrites: true });
        }
    }));
}

const renameApis = ['MoveFileW', 'MoveFileExW', 'ReplaceFileW'];
for (const name of renameApis) {
    const address = kernel32.findExportByName(name);
    if (!address) continue;
    keptHooks.push(Interceptor.attach(address, {
        onEnter(args) {
            guardPathArgument(this, args, 0, { blockWrites: true });
            guardPathArgument(this, args, 1, { blockWrites: true });
        }
    }));
}

// ------------------------------------------------ profile redirection (reads)
// Reads are not violations, but they must not see the machine profile either:
// a cached absolute path would otherwise load the user's own files.
for (const name of ['GetFileAttributesW', 'GetFileAttributesExW', 'FindFirstFileW', 'FindFirstFileExW']) {
    const address = kernel32.findExportByName(name);
    if (!address) continue;
    keptHooks.push(Interceptor.attach(address, {
        onEnter(args) {
            if (args[0].isNull()) return;
            const original = readArgument(args, 0);
            const mapped = remapProfile(original);
            if (mapped !== original) replaceArgument(this, args, 0, mapped);
        }
    }));
}

// XRoid import copies the converted base and the wearables through CopyFile*,
// which never passes through CreateFileW; the destination is enforced here.
for (const name of ['CopyFileW', 'CopyFileExW', 'CopyFile2']) {
    const address = kernel32.findExportByName(name);
    if (!address) continue;
    keptHooks.push(Interceptor.attach(address, {
        onEnter(args) {
            const source = readArgument(args, 0);
            const mappedSource = remapProfile(source);
            if (mappedSource !== source) replaceArgument(this, args, 0, mappedSource);
            const destination = readArgument(args, 1);
            const mappedDestination = remapProfile(destination);
            if (mappedDestination !== destination) replaceArgument(this, args, 1, mappedDestination);
            if (!inLab(mappedDestination) && !isDevicePath(mappedDestination)) {
                report('blocked-outside-copy', mappedDestination);
                replaceArgument(this, args, 1, deniedPath);
            }
        }
    }));
}

// ---------------------------------------------------------- known folders
// Shell lookups return a fresh string; the guard has to replace the allocation,
// not the argument, and release the original with the same allocator.
const shell32 = Module.load('shell32.dll');
const ole32 = Module.load('ole32.dll');
const allocate = new NativeFunction(ole32.getExportByName('CoTaskMemAlloc'), 'pointer', ['size_t']);
const release = new NativeFunction(ole32.getExportByName('CoTaskMemFree'), 'void', ['pointer']);

// CoTaskMemAlloc'd result: swap the pointer and free the original allocation.
function adoptAllocated(outSlot) {
    const previous = outSlot.readPointer();
    if (previous.isNull()) return;
    const before = previous.readUtf16String();
    const after = remapProfile(before);
    if (after === before) return;
    const replacement = allocate((after.length + 1) * 2);
    replacement.writeUtf16String(after);
    outSlot.writePointer(replacement);
    release(previous);
    report('isolated-known-folder', after);
}

// Caller-owned fixed buffer: overwrite in place, but only while it still fits
// the MAX_PATH buffer the older API promises.
function adoptInPlace(outSlot) {
    const before = outSlot.readUtf16String();
    const after = remapProfile(before);
    const fitsPathBuffer = after.length < 260;
    if (after === before || !fitsPathBuffer) return;
    outSlot.writeUtf16String(after);
    report('isolated-folder', after);
}

const knownFolderCalls = [
    { exportName: 'SHGetKnownFolderPath', slotIndex: 3, adopt: adoptAllocated },
    { exportName: 'SHGetFolderPathW', slotIndex: 4, adopt: adoptInPlace },
];
for (const call of knownFolderCalls) {
    const address = shell32.getExportByName(call.exportName);
    keptHooks.push(Interceptor.attach(address, {
        onEnter(args) { this.outSlot = args[call.slotIndex]; },
        onLeave(retval) {
            const failed = retval.toInt32() !== 0;
            if (failed || this.outSlot.isNull()) return;
            call.adopt(this.outSlot);
        },
    }));
}

// ------------------------------------------------------------------ registry
// VRoid keeps its settings under one hive. Giving this process its own key
// means the real installation keeps its own preferences untouched.
const advapi32 = Module.load('advapi32.dll');
const vroidHive = /^software\\pixiv\\vroid studio(?:\\|$)/i;
const registryOpenApis = ['RegCreateKeyExW', 'RegOpenKeyExW'];
for (const name of registryOpenApis) {
    keptHooks.push(Interceptor.attach(advapi32.getExportByName(name), {
        onEnter(args) {
            if (args[1].isNull()) return;
            const before = args[1].readUtf16String();
            if (!vroidHive.test(before)) return;
            const after = before.replace(/^software\\pixiv\\vroid studio/i, probe.registryKey);
            report('isolated-registry', after);
            replaceArgument(this, args, 1, after);
        }
    }));
}

// Compatibility surface for modules that are not rewritten yet. `wear.js`
// remaps the XRoid save cache itself and addresses the old guard helpers by
// name; these aliases keep that call working until wear.js is replaced. Delete
// them together with that call site.
const norm = toComparable;
const within = inLab;
const remapFolder = remapProfile;

// --------------------------------------------------------------- entry check
if (toComparable(Process.mainModule.path) !== toComparable(probe.exe)
    || probe.excludedPids.indexOf(Process.id) !== -1) {
    throw new Error('This agent attaches only to the disposable VRoid copy it was started for');
}

send({ kind: 'isolation-ready', pid: Process.id, executable: Process.mainModule.path });
