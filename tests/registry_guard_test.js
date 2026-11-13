const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
const callbacks = new Map(), events = [];
const context = {Set, Error, ptr: x => x,
    Memory: {allocUtf8String: text => ({text})},
    Interceptor: {attach(address, hooks) { callbacks.set(address.toString(), hooks); return hooks; }}};
vm.createContext(context);
vm.runInContext(fs.readFileSync('agent/registry_guard.js', 'utf8'), context);
const key = 'Software\\VRoidFaceMCP\\test';
for (const path of ['Software\\Classes\\vroid.closet', 'VROID.CLOSET\\shell\\open\\command']) {
    const target = context.copyRegistryTarget(path, key);
    assert.equal(target.kind, 'isolated-protocol');
    assert.ok(target.path.startsWith(key + '\\Protocol\\'));
}
assert.equal(context.copyRegistryTarget('Software\\pixiv\\VRoid Studio\\prefs', key).path, key+'\\prefs');
for (const path of ['Software\\Classes', 'vroid.closet.other', 'Software\\Other', 'vroid.closet-malicious'])
    assert.equal(context.copyRegistryTarget(path, key), null);
const moduleApi = {findExportByName: name => ({toString: () => name})};
context.installCopyRegistryGuard({modules:[moduleApi,moduleApi], registryKey:key,
    report:(...event)=>events.push(event), replaceArgument:(_self,args,index,value)=>args[index]={text:value}});
assert.equal(callbacks.size, 18); // Duplicate exports across DLLs are hooked once.
for (const [name, callback] of callbacks) {
    const string = {isNull:()=>false, readUtf16String:()=> 'vroid.closet\\shell', readCString:()=> 'vroid.closet\\shell'};
    const args = ['real HKCR / real parent handle',string];
    callback.onEnter.call({}, args);
    assert.equal(args[0], '0xffffffff80000001');
    assert.equal(args[1].text, key+'\\Protocol\\vroid.closet\\shell');
    const otherArgs=['original root', {isNull:()=>false,readUtf16String:()=> 'Other',readCString:()=> 'Other'}];
    callback.onEnter.call({},otherArgs);
    assert.equal(otherArgs[0], 'original root');
}
assert.throws(()=>context.installCopyRegistryGuard({modules:[{findExportByName:()=>null}],registryKey:key}),
    /COPY_REGISTRY_ISOLATION_UNAVAILABLE/);
assert.equal(events.length, 18);
console.log('Registry routing, root handles, ANSI/Unicode, alias deduplication and missing-hook refusal passed');
