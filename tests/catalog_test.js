const assert=require('assert'),fs=require('fs'),vm=require('vm');
const context=vm.createContext({console,Map,Set,Date,JSON,Number,Error,setTimeout,clearTimeout});
vm.runInContext(fs.readFileSync('agent/catalog.js','utf8'),context);
let now=0,owner={token:'live'},notify=null,queues=0,detaches=0,reads=0;
const H={model:token=>{if(token!=='live')throw Error('STALE_MODEL');return owner;},now:()=>now,ttl:10,
    subscribe:(m,fn)=>{notify=fn;return {dispose(){detaches++;notify=null;}};},queueUpdate:()=>{queues++;},
    snapshot:m=>{reads++;return {model_token:m.token,builtin_complete:true,custom_complete:true,rows:[]};}};
const api=context.createPresetCatalogJobs(H);
let started=api.begin({expected_model:'live'});
assert.equal(queues,1);assert.equal(api.poll({expected_model:'live',request_id:started.request_id}).completed,false);
notify();assert.equal(api.poll({expected_model:'live',request_id:started.request_id}).custom_complete,true);
assert.equal(reads,1);assert.equal(detaches,1);
api.release({expected_model:'live',request_id:started.request_id});
started=api.begin({expected_model:'live'});now=20;
const timed=api.poll({expected_model:'live',request_id:started.request_id});
assert.equal(timed.custom_complete,false);assert.match(timed.errors.join(' '),/TIMEOUT/);assert.equal(detaches,2);
api.release({expected_model:'live',request_id:started.request_id});
started=api.begin({expected_model:'live'});owner={token:'live'};
assert.throws(()=>api.poll({expected_model:'live',request_id:started.request_id}),/OWNER_CHANGED/);
assert.equal(detaches,3);
api.dispose();

// A failed Unity-thread read must release native hooks immediately and still
// allow the host's finally block to release the receipt without masking it.
let failures=0;
const broken=context.createPresetCatalogJobs({...H,snapshot(){failures++;throw Error('SNAPSHOT_FAILED');}});
started=broken.begin({expected_model:'live'});notify();
assert.throws(()=>broken.poll({expected_model:'live',...started}),/SNAPSHOT_FAILED/);
assert.equal(notify,null);
assert.throws(()=>broken.poll({expected_model:'live',...started}),/SNAPSHOT_FAILED/);
assert.equal(failures,1);assert.equal(broken.release({expected_model:'live',...started}).released,true);
started=api.begin({expected_model:'live'});notify();
assert.equal(api.release({expected_model:'live',...started}).released,true);assert.equal(notify,null);
started=api.begin({expected_model:'live'});notify();now+=11;
assert.throws(()=>api.poll({expected_model:'live',...started}),/UNKNOWN_CATALOG_SCAN/);assert.equal(notify,null);

// Plain-data snapshot consumes each selectable area once and global metadata once.
let optionReads=0,catalogReads=0,areas=[];
const rows=Array.from({length:617},(_,i)=>({id:'id'+i,resource_name:'Clothing/Tops/N00/'+i,
    catalog_category:'Clothing/Tops',owned:i<600,usable:i<600,selectable:i<600,
    selectable_preset_ids:i<600?['clothing/Tops/id'+i]:[]}));
const snapshot=context.createPresetCatalogSnapshot({build:'a'.repeat(64),
    presetEntries:(m,area)=>{areas.push(area);return area==='clothing'?rows.slice(0,600).map((r,i)=>{
        optionReads++;return {id:r.selectable_preset_ids[0],transferable_id:r.id,resource_name:r.resource_name,
            category:'Tops',owned:true,label:'top',p:{}};}):[];},
    catalogRows:(m,options)=>{catalogReads++;assert.equal(options.length,600);return rows;},
    customSnapshot:()=>({rows:[],complete:true,errors:[]})});
const result=snapshot({token:'live'},true);
assert.equal(result.rows.length,617);assert.equal(optionReads,600);assert.equal(catalogReads,1);
assert.equal(areas.join(','),'face,body,hair,clothing');
assert.equal(result.rows[616].selectable,false);
console.log('catalog jobs, bounded full streams, locked tail and cleanup passed');
