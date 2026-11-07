'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

// Execute the shipped adapter. Only the external managed operations are doubled.
const source = fs.readFileSync('agent/operations.js','utf8');
const start = source.indexOf('    function history(args, method)');
const end = source.indexOf('    function newModel(args)',start);
assert(start > 0 && end > start);
let permitted = true, calls = 0, guards = 0, loseReply = false;
const ctx = {
    state:{frame:15}, requireOrdinaryEditing:() => {},
    modelContext(token) {
        if (token !== 'fresh') throw Error('STALE_MODEL');
        return {engine:{}, context:{tryMethod:name => {
            assert.equal(name, 'get_CanUndo');
            return {invoke:() => permitted};
        }}};
    },
    attachedState:{guard() { guards++; }},
    invokeManaged() {
        calls++;
        if (loseReply) throw Error('STALE_MODEL');
        return {};
    },
    rememberTask:() => ({task_id:'one'}),
};
vm.runInNewContext(source.slice(start,end),ctx);
const run = token => ctx.history({expected_model:token},'UndoAsync');
const stale = run('expired');
assert.equal(stale.dispatched,false);
assert.match(stale.error,/STALE_MODEL/);
assert.equal(calls,0);
permitted = false;
assert.equal(run('fresh').available,false);
assert.equal(guards,0);
permitted = true;
assert.equal(run('fresh').task_id,'one');
loseReply = true;
assert.throws(() => run('fresh'),/STALE_MODEL/);
assert.equal(calls,2);
console.log('native history boundaries: stale, exhausted, confirmed and post-invocation loss passed');
