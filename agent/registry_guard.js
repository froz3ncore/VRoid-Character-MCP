// Copy mode redirects VRoid settings and protocol registrations per process.
// Real installations keep their URL association, including an installed 2.16.
function copyRegistryTarget(path, registryKey) {
    if (/^software\\pixiv\\vroid studio(?:\\|$)/i.test(path))
        return {path: path.replace(/^software\\pixiv\\vroid studio/i, registryKey), kind: 'isolated-registry'};
    if (/^(software\\classes\\)?vroid\.closet(?:\\|$)/i.test(path))
        return {path: registryKey + '\\Protocol\\' + path.replace(/^software\\classes\\/i, ''),
                kind: 'isolated-protocol'};
    return null;
}

function installCopyRegistryGuard({modules, registryKey, report, replaceArgument}) {
    const addresses = new Set(), hooks = [], required = new Set(['RegOpenKeyExW', 'RegCreateKeyExW']);
    const names = ['RegOpenKeyEx', 'RegCreateKeyEx', 'RegOpenKey', 'RegCreateKey',
                   'RegDeleteKey', 'RegDeleteKeyEx', 'RegDeleteTree', 'RegGetValue', 'RegSetKeyValue'];
    for (const api of names) for (const suffix of ['W', 'A']) for (const module of modules) {
        const name = api + suffix, address = module.findExportByName(name);
        if (!address) continue;
        required.delete(name);
        if (addresses.has(address.toString())) continue;
        addresses.add(address.toString());
        hooks.push(Interceptor.attach(address, {
            onEnter(args) {
                if (args[1].isNull()) return;
                const before = suffix === 'W' ? args[1].readUtf16String() : args[1].readCString();
                const target = copyRegistryTarget(before, registryKey);
                if (!target) return;
                // HKCR and handles to real Software\Classes are also valid
                // callers. Always use HKCU, not a path relative to that handle.
                args[0] = ptr('0xffffffff80000001');
                report(target.kind, target.path);
                if (suffix === 'W') replaceArgument(this, args, 1, target.path);
                else {
                    const path = Memory.allocUtf8String(target.path);
                    this.registryPath = path;
                    args[1] = path;
                }
            },
        }));
    }
    if (required.size) throw Error('COPY_REGISTRY_ISOLATION_UNAVAILABLE: ' + [...required].join(','));
    return hooks;
}
