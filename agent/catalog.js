// Catalog synchronization adapted from mcjo79 Catalog.cs/preset_cache.py (MIT).
// See licenses/mcjo79-0dc7d5e.txt. Existing Python/Frida ownership remains in use.
function createPresetCatalogJobs({model,subscribe,queueUpdate,snapshot,sameOwner=(a,b)=>a===b,now=()=>Date.now(),ttl=10000}) {
    const jobs=new Map();let next=0;
    function cleanup(job){if(job.cancel){job.cancel();job.cancel=null;}if(job.timer){clearTimeout(job.timer);job.timer=null;}}
    function dispose(){for(const job of jobs.values())cleanup(job);jobs.clear();}
    function expire(job){
        if(!job.completed&&now()>=job.deadline){cleanup(job);job.completed=true;job.observed=false;
            job.error='CUSTOM_REGISTRY_OBSERVATION_TIMEOUT';job.retireAt=now()+ttl;}
        else if(job.completed&&now()>=job.retireAt){cleanup(job);jobs.delete(job.id);}
    }
    function begin(args){
        for(const job of jobs.values())expire(job);
        if(jobs.size)throw Error('CATALOG_SCAN_PENDING');
        if(typeof args.expected_model!=='string'||!args.expected_model)throw Error('EXPECTED_MODEL_REQUIRED');
        const owner=model(args.expected_model),job={id:'catalog-'+(++next),owner,token:owner.token,deadline:now()+ttl,completed:false,observed:false};
        jobs.set(job.id,job);
        try{
            job.cancel=subscribe(owner,()=>{job.observed=true;job.completed=true;job.retireAt=now()+ttl;cleanup(job);
                job.timer=setTimeout(()=>expire(job),ttl+1);});
            queueUpdate(owner); // One explicit registry refresh, never a guessed observer layout.
        }catch(error){cleanup(job);job.completed=true;job.retireAt=now()+ttl;job.error=String(error);}
        if(!job.timer)job.timer=setTimeout(()=>{expire(job);if(jobs.has(job.id))job.timer=setTimeout(()=>expire(job),ttl+1);},ttl+1);
        return {request_id:job.id};
    }
    function find(args){
        const job=jobs.get(args.request_id);if(!job)throw Error('UNKNOWN_CATALOG_SCAN');
        try{if(args.expected_model!==job.token||!sameOwner(model(args.expected_model),job.owner))throw Error('CATALOG_OWNER_CHANGED');}
        catch(error){cleanup(job);jobs.delete(job.id);throw error;}
        return job;
    }
    function poll(args){
        const job=find(args);expire(job);
        if(!job.completed)return {completed:false};
        if(!job.result){job.result=snapshot(job.owner,job.observed);
            if(job.error){job.result.custom_complete=false;job.result.errors??=[];job.result.errors.push(job.error);}}
        return {...job.result,completed:true};
    }
    function release(args){const job=find(args);cleanup(job);jobs.delete(job.id);return {released:true};}
    return {begin,poll,release,dispose};
}

function createPresetCatalogSnapshot({presetEntries,catalogRows,customSnapshot,build}){
    return (m,observed)=>{
        const areas=['face','body','hair','clothing'],options=[],byResource=new Map(),byId=new Map(),byNative=new Map();
        for(const area of areas){
            const entries=presetEntries(m,area);
            if(!Array.isArray(entries)||entries.length>20000)throw Error('CATALOG_OPTION_LIMIT');
            for(const entry of entries){
                if(entry.clear)continue;
                if(typeof entry.resource_name!=='string'||!entry.resource_name)throw Error('CATALOG_OPTION_RESOURCE_UNAVAILABLE');
                if(byId.has(entry.id))throw Error('CATALOG_DUPLICATE_OPTION_ID');
                const native=entry.transferable_id??entry.p.method('get_TransferableGroupId').invoke();
                const nativeId=typeof native==='string'?native:native?.content;
                if(typeof nativeId!=='string'||!nativeId)throw Error('CATALOG_OPTION_IDENTITY_UNAVAILABLE');
                const row={...entry,transferable_id:nativeId,area};delete row.p;options.push(entry);byId.set(entry.id,row);
                const list=byResource.get(entry.resource_name)||[];list.push(row);byResource.set(entry.resource_name,list);
                if(list[0].transferable_id!==nativeId)throw Error('CATALOG_OPTION_RESOURCE_CONFLICT');
                const nativeOptions=byNative.get(nativeId)||[];
                if(nativeOptions.length&&nativeOptions[0].resource_name!==entry.resource_name)throw Error('CATALOG_OPTION_IDENTITY_CONFLICT');
                nativeOptions.push(row);byNative.set(nativeId,nativeOptions);
                if(options.length>20000)throw Error('CATALOG_OPTION_LIMIT');
            }
        }
        const catalog=catalogRows(m,options),resources=new Set(),ids=new Set(),rows=[];
        if(!Array.isArray(catalog)||catalog.length>20000)throw Error('CATALOG_METADATA_LIMIT');
        for(const entry of catalog){
            if(!entry.resource_name||resources.has(entry.resource_name)||ids.has(entry.id))throw Error('CATALOG_DUPLICATE_METADATA');
            resources.add(entry.resource_name);ids.add(entry.id);
            const resourceOptions=byResource.get(entry.resource_name)||[],options=byNative.get(entry.id)||[];
            if(resourceOptions.some(o=>o.transferable_id!==entry.id)||options.some(o=>o.resource_name!==entry.resource_name))
                throw Error('CATALOG_CROSS_INVENTORY_IDENTITY_CONFLICT');
            const option=options.find(o=>o.owned)||options[0];
            rows.push({kind:'builtin',id:entry.id,resource:entry.resource_name,
                category:entry.catalog_category||'VRoid/Unclassified',name:option?.label||entry.resource_name,
                owned:entry.owned,usable:entry.usable,selectable:options.some(o=>o.owned),
                selectable_preset_ids:options.filter(o=>o.owned).map(o=>o.id),area:option?.area||null,
                price_in_coin:entry.price_in_coin,is_set_item:entry.is_set_item,catalog_only:options.length===0});
        }
        // A selectable item absent from PlayFab is still observed, never lost in the metadata tail.
        for(const [resource,options] of byResource){
            if(resources.has(resource))continue;
            const option=options.find(o=>o.owned)||options[0];
            rows.push({kind:'builtin',id:option.transferable_id,resource,category:option.area[0].toUpperCase()+option.area.slice(1)+'/'+option.category,
                name:option.label,owned:option.owned,usable:option.owned,selectable:options.some(o=>o.owned),
                selectable_preset_ids:options.filter(o=>o.owned).map(o=>o.id),area:option.area,catalog_only:false});
        }
        const custom=customSnapshot(m);
        if(rows.length+custom.rows.length>20000)throw Error('CATALOG_ROW_LIMIT');
        return {model_token:m.token,build,areas,rows:rows.concat(custom.rows),builtin_complete:true,
            custom_complete:observed&&custom.complete,errors:custom.errors,
            scope:'registered collection after observed OnUpdate; not all files on disk'};
    };
}

function createNativePresetCatalog({model,presetEntries,helpers,text,build,retain}){
    const {prop}=helpers;
    const str=o=>typeof o==='string'?o:text(o);
    const registry=m=>m.root.field('_customItemRegistry').value;
    // Counts plus bounded enumeration refuse null, silent empties and truncated registries.
    function values(dictionary){
        if(!dictionary||dictionary.handle.isNull())throw Error('CUSTOM_REGISTRY_DICTIONARY_UNAVAILABLE');
        const count=dictionary.method('get_Count').invoke();
        if(!Number.isInteger(count)||count<0||count>20000)throw Error('CUSTOM_REGISTRY_COUNT_LIMIT');
        const it=dictionary.method('get_Values').invoke().method('GetEnumerator').invoke(),result=[];
        try{while(it.method('MoveNext').invoke()){
            if(result.length>=count)throw Error('CUSTOM_REGISTRY_ENUMERATION_INCONSISTENT');
            result.push(it.method('get_Current').invoke());
        }}finally{it.method('Dispose').invoke();}
        if(result.length!==count||dictionary.method('get_Count').invoke()!==count)throw Error('CUSTOM_REGISTRY_ENUMERATION_INCOMPLETE');
        return result;
    }
    function customRead(m){
        const r=registry(m),files=values(r.field('_pathToFileCustomItemModels').value),
            failures=values(r.field('_pathToObservationFailureItems').value),rows=[],errors=[];
        for(const failure of failures)errors.push('CUSTOM_OBSERVATION_FAILED: '+str(prop(failure,'CustomItemPath')));
        const paths=new Set();
        for(const f of files){
            try{
                const custom=prop(f,'CustomItemId'),path=str(prop(f,'FilePath'));
                if(!path||paths.has(path.toLowerCase()))throw Error('CUSTOM_REGISTRY_DUPLICATE_PATH');paths.add(path.toLowerCase());
                const type=str(prop(f,'TransferableGroupTypeId')),resource=str(prop(custom,'ResourceName')),
                    revision=str(prop(f,'TransferableGroupRevision')),customRevision=str(prop(custom,'Revision'));
                if(!resource||!revision||!customRevision)throw Error('CUSTOM_REGISTRY_IDENTITY_UNAVAILABLE');
                const slot=type.split('.').pop();
                rows.push({kind:'custom',id:str(prop(f,'TransferableGroupId')),resource,path,revision,
                    custom_revision:customRevision,group_type:type,name:str(prop(f,'DisplayName')),
                    resource_name:str(prop(f,'TransferableGroupResourceName')),category:'Custom/'+slot,
                    registered:r.method('CheckIfIsRegisteredInAssetStorage').invoke(prop(f,'TransferableGroupResourceName')),
                    owned:true,usable:true,selectable:true});
            }catch(error){errors.push(String(error));}
        }
        return {rows,complete:errors.length===0,errors};
    }
    function customSnapshot(m){
        try{
            const first=customRead(m),second=customRead(m);
            const canonical=value=>JSON.stringify(value.rows.slice().sort((a,b)=>a.path.localeCompare(b.path)));
            if(canonical(first)!==canonical(second))throw Error('CUSTOM_REGISTRY_CHANGED_DURING_SCAN');
            return {...second,complete:first.complete&&second.complete,errors:[...first.errors,...second.errors]};
        }catch(error){return {rows:[],complete:false,errors:[String(error)]};}
    }
    function subscribe(m,completed){
        if(!nativeBuildProfile(build)?.registryObservation)throw Error('CUSTOM_OBSERVATION_BUILD_UNSUPPORTED');
        const element='VRoid.Studio.ModelPresetsSelector.',generic='System.Collections.Generic.';
        const r=registry(m);
        if(r.class.type.name!==element+'CustomItemRegistry')throw Error('CUSTOM_OBSERVATION_REGISTRY_TYPE');
        const update=r.method('OnUpdate',2),notify=r.method('NotifyUpdateFiles',1),queue=r.method('QueueUpdate',0);
        const observed=element+'ObservedCustomItem',failure=element+'CustomItemObservationFailureItem';
        function matches(method,arguments_){
            return !method.isStatic&&method.returnType.name==='System.Void'&&!method.virtualAddress.isNull()&&
                method.parameters.length===arguments_.length&&arguments_.every((type,i)=>
                    method.parameters[i].type.name.replace('`1<','<')===generic+type);
        }
        if(!matches(update,['IReadOnlyCollection<'+observed+'>','IReadOnlyCollection<'+failure+'>'])||
            !matches(notify,['List<'+failure+'>'])||!matches(queue,[]))throw Error('CUSTOM_OBSERVATION_SIGNATURE_UNSUPPORTED');
        const pin=retain(r),threads=new Map();let updateHook=null,notifyHook=null,done=false;
        function dispose(){if(done)return;done=true;if(updateHook)updateHook.detach();if(notifyHook)notifyHook.detach();threads.clear();pin.free();}
        try{
            updateHook=Interceptor.attach(update.virtualAddress,{
                onEnter(args){this.match=args[0].equals(r.handle);if(this.match)threads.set(Process.getCurrentThreadId(),{notified:false});},
                onLeave(){if(!this.match)return;const item=threads.get(Process.getCurrentThreadId());threads.delete(Process.getCurrentThreadId());
                    if(item?.notified&&!done)completed();}
            });
            notifyHook=Interceptor.attach(notify.virtualAddress,{onEnter(args){
                const item=threads.get(Process.getCurrentThreadId());if(item&&args[0].equals(r.handle))item.notified=true;
            }});
            return dispose;
        }catch(error){dispose();throw error;}
    }
    const scanModel=expected=>{const m=model(expected);return {...m,catalog_registry:registry(m).handle};};
    const jobs=createPresetCatalogJobs({model:scanModel,subscribe,
        sameOwner:(a,b)=>a.token===b.token&&a.engine.handle.equals(b.engine.handle)&&a.root.handle.equals(b.root.handle)
            &&a.catalog_registry.equals(b.catalog_registry),
        queueUpdate:m=>registry(m).method('QueueUpdate',0).invoke(),
        snapshot:createPresetCatalogSnapshot({presetEntries,catalogRows:helpers.catalogRows,customSnapshot,build})});
    return {dispose:jobs.dispose,operations:{preset_catalog_begin:jobs.begin,preset_catalog_poll:jobs.poll,preset_catalog_release:jobs.release}};
}
