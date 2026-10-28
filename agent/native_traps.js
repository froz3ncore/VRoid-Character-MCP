// Adapted from Karylcode/VRoid-MCP baaa94e (MIT; see licenses/).
// Managed NativeFunction calls must run the filesystem Interceptor listeners.
(() => {
    const Native = NativeFunction;
    globalThis.NativeFunction = function (address, result, args, options) {
        const supplied = typeof options === 'string' ? {abi: options} : (options || {});
        return new Native(address, result, args, Object.assign({traps: 'all'}, supplied));
    };
})();
