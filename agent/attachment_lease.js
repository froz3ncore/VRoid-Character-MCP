// Process-local attachment lease. No model/profile files are used for recovery.
function createAttachmentLease(api) {
    let owned = null;
    function decode(raw) {
        const lease = JSON.parse(raw);
        if (lease.version !== 1 || lease.target !== api.target ||
            !Number.isSafeInteger(lease.owner) || lease.owner <= 0 ||
            typeof lease.background !== 'boolean' ||
            typeof lease.handle !== 'string' || !/^0x[0-9a-f]+$/i.test(lease.handle))
            throw Error('ATTACHMENT_LEASE_INVALID');
        return lease;
    }
    function restore(lease) {
        api.setBackground(lease.background);
        // Clear before closing: a crash here can leak a handle but cannot cause
        // a later connection to mistake a recycled Windows handle for its owner.
        api.write(null);
        api.closeOwner(lease.handle);
    }
    return {
        acquire() {
            let recovered = false;
            const raw = api.read();
            if (raw) {
                const previous = decode(raw), state = api.ownerState(previous.handle, previous.owner);
                if (state === 'alive') throw Error('ATTACHMENT_ALREADY_OWNED: another MCP host is connected');
                if (state !== 'dead') throw Error('ATTACHMENT_LEASE_OWNER_UNVERIFIED');
                restore(previous);
                recovered = true;
            }
            const lease = {version: 1, target: api.target, owner: api.owner,
                background: api.getBackground(), handle: api.openOwner()};
            if (!lease.handle || lease.handle === '0x0') throw Error('ATTACHMENT_OWNER_HANDLE_UNAVAILABLE');
            try { api.write(JSON.stringify(lease)); }
            catch (error) { api.closeOwner(lease.handle); throw error; }
            owned = lease;
            // Persist ownership before changing native state so abrupt host exit
            // remains recoverable even while attachment is being initialized.
            api.setBackground(true);
            return {recovered_previous_host: recovered, original_background: lease.background,
                    owner_pid: api.owner};
        },
        release() {
            if (!owned) return;
            const raw = api.read();
            if (!raw || JSON.stringify(decode(raw)) !== JSON.stringify(owned))
                throw Error('ATTACHMENT_LEASE_CHANGED: refusing to restore another owner');
            restore(owned);
            owned = null;
        },
    };
}
