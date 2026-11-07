// Native group/query/history adapters adapted from mcjo79/vroid-mcp 0dc7d5e
// VRoidApi.cs, ClothingSliders.cs, AdvancedEdit.cs, Presets.cs, CustomItems.cs,
// Catalog.cs and mcp_server/vroid_mcp.py (MIT). See licenses/mcjo79-0dc7d5e.txt.
// All calls run on the existing Unity main-thread queue. Never wait here.
function certifySituationMembers(root,inventory,read){
    const members=[],visiting=new Set(),visited=new Set();
    function visit(id,depth){
        if(depth>32||visited.size>=512||visiting.has(id)||visited.has(id))throw Error('SITUATION_MEMBER_GRAPH_LIMIT_OR_CYCLE');
        visiting.add(id);
        const matches=inventory.filter(g=>g.id===id);
        if(matches.length!==1)throw Error('SITUATION_MEMBER_NOT_UNIQUELY_ACTIVE');
        const info=matches[0],node=read(id);
        if(!node||['id','type','resource_name','revision'].some(k=>node[k]!==info[k])||!info.revision
            ||node.updated_since_last_revision!==false)
            throw Error('SITUATION_MEMBER_IDENTITY_MISMATCH');
        if(id===root.id&&['id','type','resource_name','revision'].some(k=>info[k]!==root[k]))throw Error('SITUATION_ROOT_IDENTITY_MISMATCH');
        if(!Array.isArray(node.entries)||node.entries.length>4096)throw Error('SITUATION_MEMBER_ENTRY_LIMIT');
        members.push({...info,updated_since_last_revision:false});
        for(const entry of node.entries){
            if(entry.type==='Transferable')continue;
            if(entry.type!=='TransferableGroup'||typeof entry.id!=='string'||!entry.id)throw Error('SITUATION_MEMBER_EDGE_UNPROVEN');
            visit(entry.id,depth+1);
        }
        visiting.delete(id);visited.add(id);
    }
    visit(root.id,0);
    return {verified:true,revision_verified:true,root:members.find(g=>g.id===root.id),members,
        policy:'exact active/stored clean revisions; direct TransferableGroup entries only; Transferable entries are leaf content'};
}
function createGroupApi(H) {
    const {model, cls, text, invokeManaged, entries, details, state, ordinary, presetEntries} = H;
    const pathNamespace = 'VRoidCore.Common.TransferableTypes.Path.';
    const requests = new Map();
    let nextRequest = 0;
    const alive = o => o != null && (!o.handle || !o.handle.isNull());
    const str = o => typeof o === 'string' ? o : text(o);
    function prop(o, name) {
        if (!alive(o)) throw Error('NULL_NATIVE_PROPERTY: ' + name);
        const getter = o.tryMethod('get_' + name, 0);
        if (getter) return getter.invoke();
        // Use actual declared native field metadata, never C# proxy spellings
        // assumed to exist in IL2CPP. The recognized backing layout is explicit.
        for (const candidate of [name, '<' + name + '>k__BackingField']) {
            const field = o.tryField(candidate);
            if (field) return field.value;
        }
        throw Error('NATIVE_PROPERTY_UNAVAILABLE: ' + name);
    }
    function optional(o, name) { try { return prop(o, name); } catch (_) { return null; } }
    function sequence(o, limit=Infinity) {
        if (!alive(o)) return [];
        if (Array.isArray(o)) {if(o.length>limit)throw Error('NATIVE_ENUMERATION_LIMIT');return o;}
        if (typeof o[Symbol.iterator] === 'function') {
            const out=[];for(const item of o){if(out.length>=limit)throw Error('NATIVE_ENUMERATION_LIMIT');out.push(item);}return out;
        }
        const array = o.tryField('array');
        if (array) return sequence(array.value,limit);
        const bound = (object,name) => {
            const direct = object.tryMethod(name);
            if (direct) return direct;
            const metadata = object.class.methods.find(m=>m.name.endsWith('.' + name));
            return metadata ? object.method(metadata.name) : null;
        };
        const get = bound(o,'GetEnumerator');
        if (!get) throw Error('NATIVE_ENUMERATOR_UNAVAILABLE');
        const it = get.invoke(), out = [];
        const method = name => bound(it,name);
        const move = method('MoveNext'), current = method('get_Current');
        if (!move || !current) throw Error('NATIVE_ENUMERATOR_LAYOUT_UNSUPPORTED');
        try { while (move.invoke()) {if(out.length>=limit)throw Error('NATIVE_ENUMERATION_LIMIT');out.push(current.invoke());} }
        finally { const dispose = method('Dispose'); if (dispose) dispose.invoke(); }
        return out;
    }
    const pairs = d => sequence(d).map(e => [str(prop(e, 'Key')), prop(e, 'Value')]);
    function requireModel(args) {
        if (typeof args.expected_model !== 'string' || !args.expected_model) throw Error('EXPECTED_MODEL_REQUIRED');
        return model(args.expected_model);
    }
    const active = m => m.context.method('get_ActiveModel').invoke();
    function nativeQuery(m, name, args) {
        const query = cls('VRoidCore', 'VRoidCore.Editing.Query.' + name).alloc();
        invokeManaged(query, '.ctor', args);
        return invokeManaged(query, 'Execute', [active(m).handle]);
    }
    function pathDescriptor(path) {
        const type = path.class.name;
        if (/^Template(BlendShapeTransform|Color)Path$/.test(type)) {
            const wrapped = object => {
                const value = optional(object,'Value') ?? optional(object,'Key');
                const key = str(value);
                if (!key) throw Error('TEMPLATE_WRAPPER_KEY_UNAVAILABLE');
                return key;
            };
            return {path_type: type, template_key: wrapped(prop(path,'templatePath')),
                element_key: wrapped(prop(path,'editableElementPath'))};
        }
        if (!['BlendShapeTransformPath', 'BoneTransformPath', 'ColorPath'].includes(type))
            throw Error('UNSUPPORTED_EXACT_PATH_TYPE: ' + type);
        return {path_type: type, template_key: null, element_key: str(prop(path, 'Key'))};
    }
    function bindingIdentity(group, descriptor) {
        return JSON.stringify([group, descriptor.path_type, descriptor.template_key, descriptor.element_key]);
    }
    const fingerprint = g => JSON.stringify([g.id, g.type, g.resource_name, g.revision]);
    function clearType(entry) {
        if (entry.native_group_type) return entry.native_group_type;
        for (const owner of [entry.p, optional(entry.p, '_model')]) {
            const type = optional(owner, 'TransferableGroupType') || optional(owner, '_transferableGroupType');
            if (alive(type)) return str(type);
        }
        return null;
    }
    function groupInventory(m, removalCapabilities=true) {
        const found = new Map(), errors = [];
        const completeness = {active:false,active_leaf:false,stored:false};let coherent=true;
        function merge(id, object, flags, nativeInfo=false) {
            const row = found.get(id) || {id, type: null, resource_name: null, revision: null,
                active: false, active_leaf: false, stored: false, errors: []};
            Object.assign(row, flags);
            if(flags.active||nativeInfo)try{
                const nativeId=str(prop(object,'Id'));
                if(typeof nativeId!=='string'||!nativeId||nativeId!==id)throw Error('NATIVE_INFO_ID_KEY_MISMATCH');
            }catch(error){
                coherent=false;errors.push({source:'native_info_identity',id,error:String(error)});
                row.errors.push(String(error));
            }
            for (const [name, native] of [['type', 'Type'], ['resource_name', 'ResourceName'], ['revision', 'Revision']]) {
                try { const value = str(prop(object, native)); if (value != null){
                    if(row[name]!=null&&row[name]!==value){coherent=false;errors.push({source:'identity_conflict',id,field:name});}
                    row[name] = value;
                } }
                catch (error) { row.errors.push(String(error)); }
            }
            found.set(id, row);
        }
        try {
            for (const [id, group] of pairs(active(m).method('GetActiveTransferableGroups').invoke()))
                merge(id, group, {active: true});
            completeness.active = true;
        } catch (error) { errors.push({source: 'active', error: String(error)}); }
        try {
            for (const [id,leaf] of pairs(m.context.method('GetActiveLeafTransferableGroups').invoke())) {
                merge(id,leaf,{active:true,active_leaf:true});
                const info = m.context.method('GetActiveTransferableGroupInfo').invoke(Il2Cpp.string(id));
                merge(id, info, {active: true, active_leaf: true});
            }
            completeness.active_leaf = true;
        } catch (error) { errors.push({source: 'active_leaf', error: String(error)}); }
        try {
            for (const [id, group] of pairs(prop(active(m), 'TransferableGroups'))) {
                const info = m.context.method('GetActiveTransferableGroupInfo').invoke(Il2Cpp.string(id));
                merge(id, alive(info) ? info : group, {stored: true}, alive(info));
                try{
                    const header=prop(group,'Header'),custom=prop(header,'Custom'),row=found.get(id);
                    const stored={id:str(prop(header,'Id')),type:str(prop(group,'TypeId')),
                        resource_name:str(prop(header,'ResourceName')),revision:str(prop(custom,'Revision'))};
                    if(row.active&&['id','type','resource_name','revision'].some(k=>row[k]!==stored[k])){
                        coherent=false;errors.push({source:'stored_identity_conflict',id});
                    }
                    if(!row.active)Object.assign(row,stored);
                    row.updated_since_last_revision=prop(custom,'UpdatedSinceLastRevision');
                }
                catch(_){found.get(id).updated_since_last_revision=null;}
                const elements = optional(group, 'EditableElements');
                found.get(id).editable_element_count = alive(elements) ? prop(elements, 'Count') : null;
            }
            completeness.stored = true;
        } catch (error) { errors.push({source: 'stored', error: String(error)}); }
        const clears = [];
        for (const area of removalCapabilities ? ['face', 'body', 'hair', 'clothing'] : []) {
            try { clears.push(...presetEntries(m, area).filter(e => e.clear).map(e => ({type: clearType(e), id: e.id}))); }
            catch (error) { errors.push({source: 'removal_capability/' + area, error: String(error)}); }
        }
        const groups = [...found.values()].sort((a,b) => a.id.localeCompare(b.id));
            const complete = coherent&&Object.values(completeness).every(value=>value);
        for (const g of groups) {
            g.fingerprint = fingerprint(g);
            g.removal_evidence = clears.filter(c => c.type && c.type === g.type);
            // A native clear option tied to this full native type is required.
            g.removable = complete && g.active_leaf && g.removal_evidence.length === 1;
            g.removal_reason = g.removable ? 'exact native clear option type binding' : 'mandatory or native removal capability not established';
        }
        const topology = JSON.stringify(groups.map(g => g.fingerprint));
        return {model_token: m.token, groups, errors, topology_fingerprint: topology,
            membership_complete:complete,source_completeness:completeness};
    }
    function exactGroup(m, id) {
        const inventory = groupInventory(m), rows = inventory.groups.filter(g => g.id === id);
        if (rows.length !== 1) throw Error('UNKNOWN_OR_STALE_GROUP: relist groups');
        if (!rows[0].revision || !rows[0].type) throw Error('GROUP_IDENTITY_UNAVAILABLE');
        return {inventory, group: rows[0]};
    }
    function situationDefinitions(m){
        const dictionary=prop(active(m),'TransferableGroups'),table=new Map();
        for(const item of sequence(dictionary,20000)){
            const key=str(prop(item,'Key'));if(table.has(key))throw Error('SITUATION_DUPLICATE_GROUP_ID');
            table.set(key,prop(item,'Value'));
        }
        const enumType=cls('VRoidCore','VRoidCore.Common.TransferableTypes.TransferableGroupEntryType');
        function discriminator(value) {
            const owner = value?.type?.class;
            if (enumType.handle && (!owner?.isEnum || !enumType.handle.equals(owner.handle)))
                throw Error('SITUATION_ENTRY_ENUM_TYPE_MISMATCH');
            // Literal field reads and managed return values own different
            // ValueType storage even when they represent the same named enum.
            const number = owner?.isEnum ? value.field('value__').value : value;
            if (!Number.isInteger(number)) throw Error('SITUATION_ENTRY_ENUM_VALUE_INVALID');
            return number;
        }
        const types=new Map(['TransferableGroup','Transferable','Clear','ClearByResourceName','RecommendedTransferableGroup']
            .map(name=>[discriminator(enumType.field(name).value),name]));
        if (types.size !== 5) throw Error('SITUATION_ENTRY_ENUM_AMBIGUOUS');
        const read=id=>{
            const group=table.get(id);if(!group)throw Error('SITUATION_MEMBER_DEFINITION_UNAVAILABLE');
            const header=prop(group,'Header'),custom=prop(header,'Custom');
            return {id:str(prop(header,'Id')),resource_name:str(prop(header,'ResourceName')),type:str(prop(group,'TypeId')),
                revision:str(prop(custom,'Revision')),updated_since_last_revision:prop(custom,'UpdatedSinceLastRevision'),
                entries:sequence(prop(group,'Entries'),4096).map(entry=>{
                    const type=types.get(discriminator(prop(entry,'Type')));
                    return {type,id:type==='TransferableGroup'?str(prop(entry,'TransferableGroupId')):null};
                })};
        };return {read,table};
    }
    function situationMembership(m,root,inventory){
        if(!root||!['id','type','resource_name','revision'].every(k=>typeof root[k]==='string'&&root[k])
            ||inventory.membership_complete!==true)throw Error('INVALID_OR_INCOMPLETE_SITUATION_ROOT');
        const {read}=situationDefinitions(m);
        const result=certifySituationMembers(root,inventory.groups.filter(g=>g.active),read);
        for(const member of result.members){
            const row=inventory.groups.find(g=>g.id===member.id);
            if(!row||!row.stored||!row.active)throw Error('SITUATION_MEMBER_VIEW_INCOHERENT');
        }
        return result;
    }
    function situationCandidate(m,candidate){
        if(!candidate||!['id','resource_name'].every(k=>typeof candidate[k]==='string'&&candidate[k]))throw Error('INVALID_SITUATION_CANDIDATE');
        const restoration=prop(m.context,'RestorationInfo'),storage=prop(restoration,'AssetStorage'),catalog=prop(storage,'AssetCatalog');
        const entry=catalog.method('GetTransferableGroupByName').invoke(Il2Cpp.string(candidate.resource_name));
        if(!alive(entry)||str(prop(entry,'id'))!==candidate.id||str(prop(entry,'resourceName'))!==candidate.resource_name)
            throw Error('SITUATION_CATALOG_BINDING_CHANGED');
        const root={...candidate,type:str(prop(entry,'transferableGroupType'))};
        if(!root.type)throw Error('SITUATION_CATALOG_TYPE_UNAVAILABLE');
        const {read,table}=situationDefinitions(m);
        if(!table.has(root.id))return {verified:true,root,revision_verified:false,members:null};
        const infos=[],visiting=new Set();
        function collect(id,depth){
            if(depth>32||infos.length>=512||visiting.has(id))throw Error('SITUATION_DEFINITION_GRAPH_LIMIT');
            visiting.add(id);const node=read(id);
            infos.push({id:node.id,type:node.type,resource_name:node.resource_name,revision:node.revision});
            for(const e of node.entries)if(e.type==='TransferableGroup')collect(e.id,depth+1);
        }
        try{
            collect(root.id,0);
            const stored=infos.find(g=>g.id===root.id);
            if(['id','type','resource_name'].some(k=>stored[k]!==root[k]))throw Error('SITUATION_STORED_CATALOG_BINDING_CHANGED');
            return certifySituationMembers(stored,infos,read);
        }catch(error){return {verified:true,root,revision_verified:false,members:null,version_error:String(error)};}
    }
    function rowId(m, group, topology, binding) {
        return 'group/' + encodeURIComponent(JSON.stringify([m.token, group.fingerprint, topology, binding]));
    }
    function typedRows(m, group, inventory, errors) {
        const rows = [];
        let clothingTarget;
        for (const area of ['face', 'body', 'clothing']) {
            try {
                for (const entry of entries(m, area)) {
                    const d = details(entry);
                    if (area === 'clothing') {
                        const owner = entry.id.slice('clothing/'.length,entry.id.lastIndexOf('/'));
                        if (owner !== group.id) {
                            const sibling = inventory.groups.find(g=>g.id===owner);
                            if (d.semantic_group===group.type || sibling?.type===group.type
                                || (!sibling?.type && !d.semantic_group))
                                errors.push({source:'typed/'+area,error:'CLOTHING_VM_SIBLING_OWNER_UNPROVEN'});
                            continue;
                        }
                        if (d.semantic_group !== group.type) {
                            errors.push({source:'typed/'+area,error:'CLOTHING_VM_GROUP_TYPE_UNPROVEN'});
                            continue;
                        }
                    } else if (!d.semantic_group) {
                        errors.push({source:'typed/'+area,error:'TYPED_VM_GROUP_UNPROVEN'});
                        continue;
                    }
                    if (d.semantic_group !== group.type) continue;
                    if (d.semantic_status !== 'complete') {
                        errors.push({source:'typed/'+area,error:'TYPED_VM_BINDINGS_INCOMPLETE'});
                        continue;
                    }
                    if (!inventory.membership_complete || !group.active) continue;
                    const sameType = inventory.groups.filter(g => g.active && g.type === group.type);
                    if (sameType.length !== 1 || sameType[0].id !== group.id
                            || inventory.groups.some(g=>g.active && !g.type)) {
                        errors.push({source:'typed/'+area,error:'TYPED_VM_OWNER_AMBIGUOUS'});
                        continue;
                    }
                    if (area === 'clothing') {
                        // The VM resolves the type on its current model. Its
                        // containing editor instance alone cannot bind the setter.
                        if (clothingTarget === undefined)
                            clothingTarget = str(active(m).method('GetTransferableGroupIdOfType',1).invoke(Il2Cpp.string(group.type)));
                        if (clothingTarget !== group.id) {
                            errors.push({source:'typed/'+area,error:'CLOTHING_VM_RESOLVED_OWNER_MISMATCH'});
                            continue;
                        }
                    }
                    const native = d.semantic_bindings.map(b => {
                        // Existing semantic metadata captures concrete path and
                        // template identity. Re-read exact native path below.
                        const fields = {single: ['_path'], combined: entry.p.class.name.includes('Bone')
                            ? ['_pathNegative','_pathPositive'] : ['_negativeBlendShapePath','_positiveBlendShapePath']};
                        const names = fields[d.semantic_kind];
                        return pathDescriptor(entry.p.field(names[d.semantic_bindings.indexOf(b)]).value);
                    });
                    const kind = entry.p.class.name.includes('Bone') ? 'bone' : 'blendshape';
                    rows.push({data: {...d, id: rowId(m, group, inventory.topology_fingerprint, ['typed', entry.id]),
                        target_binding_id: entry.id, native_bindings: native, kind, type: 'float', units: 'native_vm',
                        binding_keys: native.map(p => bindingIdentity(group.id, p)), source: 'exact_native_vm',
                        group_id: group.id, group_fingerprint: group.fingerprint}, entry,
                        write(value) {
                            const storage = Memory.alloc(4); storage.writeFloat(value);
                            invokeManaged(entry.p, entry.p.tryMethod('set_CombinedValue') ? 'set_CombinedValue' : 'set_ModelValue', [storage]);
                        }});
                }
            } catch (error) { errors.push({source: 'typed/' + area, error: String(error)}); }
        }
        return rows;
    }
    function enumName(value) {
        if (typeof value === 'string') return value;
        const c = value.class || value.type?.class;
        if (!c || !c.isEnum) return 'unknown';
        const number = value.field('value__').value;
        const names = c.fields.filter(f => f.isStatic && f.type.name === c.type.name && f.value.field('value__').value === number);
        return names.length === 1 ? names[0].name : 'unknown';
    }
    function rawRows(m, group, inventory, typed, errors) {
        const rows = [];
        const add = (kind, value, descriptor, extra = {}) => {
            const key = bindingIdentity(group.id, descriptor);
            const equivalents = typed.filter(row => row.data.binding_keys.includes(key));
            // Raw halves covered by paired VMs stay visible but must use the
            // combined control, which owns opposing-half zeroing/readback.
            const color = kind === 'color';
            const d = {id: rowId(m, group, inventory.topology_fingerprint, ['raw', key]),
                native_bindings: [descriptor], binding_keys: [key], group_id: group.id,
                group_fingerprint: group.fingerprint, kind, type: color ? 'color' : 'float',
                value, min: color ? 0 : null, max: color ? 1 : null,
                units: color ? 'native_rgba' : 'native_float_unknown_range',
                editable: color && equivalents.length === 0,
                source: 'native_raw_query', target_binding_ids: equivalents.map(r => r.data.target_binding_id),
                unsupported_reason: color && !equivalents.length ? null
                    : equivalents.length ? 'Use exact typed control; paired/alias half writes refused'
                    : 'Native scalar range/history contract not established', ...extra};
            const row = {data:d};
            if (d.editable) row.prepare = value => prepareHistory(m,group.id,kind,descriptor,value);
            rows.push(row);
            return row;
        };
        try {
            for (const [dictionaryKey, p] of pairs(m.context.method('GetParametersForTransferableGroup').invoke(Il2Cpp.string(group.id)))) {
                const key = str(prop(p, 'Key'));
                let recognized = false;
                for (const [native, kind, path, member] of [
                    ['blendShapeTransform','blendshape','BlendShapeTransformPath','Value'],
                    ['boneTransform','bone','BoneTransformPath','Value'], ['color','color','ColorPath','Color']]) {
                    const wrapper = optional(p, native);
                    if (!alive(wrapper)) continue;
                    const raw = prop(wrapper, member);
                    const value = kind === 'color' ? ['r','g','b','a'].map(c => raw.field(c).value) : raw;
                    add(kind, value, {path_type: path, template_key: null, element_key: key}, {native_dictionary_key: dictionaryKey});
                    recognized = true; break;
                }
                if (!recognized) {
                    const kind = enumName(optional(p, 'Type'));
                    rows.push({data: {id: rowId(m, group, inventory.topology_fingerprint, ['unsupported',dictionaryKey,key]),
                        native_dictionary_key: dictionaryKey, native_key: key, kind, type: kind.toLowerCase(),
                        value: null, units: 'native_unknown', editable: false,
                        unsupported_reason: 'No source-proven raw value/history contract for this native enum type',
                        binding_keys: [], native_bindings: [], source: 'native_raw_query'}});
                }
            }
        } catch (error) { errors.push({source: 'GetParametersForTransferableGroup', error: String(error)}); }
        // Preserve observations from partial queries. Only grant writes after
        // every potentially overlapping source has completed.
        const candidates = new Map();
        try {
            const leaves = pairs(m.context.method('GetActiveLeafTransferables').invoke())
                .map(([id,t]) => ({id,group:str(prop(t,'GroupId'))}));
            if (leaves.some(t=>!t.id||!t.group) || new Set(leaves.map(t=>t.id)).size !== leaves.length)
                throw Error('ITEM_TRANSFERABLE_OWNER_UNPROVEN');
            const transferables = leaves.filter(t=>t.group===group.id).map(t=>t.id);
            for (const id of transferables.length ? transferables : [null]) {
                const result = nativeQuery(m, 'GetTransferableGroupBlendShapesQuery',
                    [Il2Cpp.string(group.id).handle, id === null ? NULL : Il2Cpp.string(id).handle]);
                for (const item of sequence(prop(result, 'blendShapes'))) {
                    const path = prop(item, 'path'), descriptor = pathDescriptor(path);
                    const identity = bindingIdentity(group.id, descriptor);
                    const value = active(m).method('GetBlendShapeTransformParameter').invoke(Il2Cpp.string(group.id), path);
                    const matches = rows.filter(r=>r.data.binding_keys.includes(identity));
                    if (!matches.length) matches.push(add('blendshape',value,descriptor));
                    for (const row of matches) row.data.item_slider = true;
                    const row = matches[0];
                    const exactPath = ['BlendShapeTransformPath','TemplateBlendShapeTransformPath'].includes(descriptor.path_type)
                        && path.class.type?.name === pathNamespace + descriptor.path_type && !!descriptor.element_key;
                    const eligible = id && exactPath && !candidates.has(identity) && matches.length === 1
                        && row.data.kind === 'blendshape' && !row.data.target_binding_ids.length
                        && row.data.value === value && Number.isFinite(value) && value >= 0 && value <= 100;
                    candidates.set(identity, eligible ? {row,id,descriptor} : null);
                }
            }
        } catch (error) { errors.push({source: 'GetTransferableGroupBlendShapesQuery', error: String(error)}); }
        if (H.buildProfile?.ordinaryItemSlider && inventory.membership_complete && group.active_leaf && group.stored
                && group.resource_name && sectionFor(group.type)==='Outfit' && !group.type.endsWith('.ClothingSet')
                && !errors.some(e=>e.source.startsWith('typed/') || ['GetParametersForTransferableGroup',
                    'GetTransferableGroupBlendShapesQuery'].includes(e.source))) {
            for (const [key,candidate] of candidates) {
                if (!candidate) continue;
                const {row,id,descriptor} = candidate;
                Object.assign(row.data,{id:rowId(m,group,inventory.topology_fingerprint,['item',id,key]),
                    item_transferable_id:id,min:0,max:100,units:'native_item_blendshape',editable:true,unsupported_reason:null});
                row.prepare = value=>prepareHistory(m,group.id,'blendshape',descriptor,value);
            }
        }
        return rows;
    }
    function wornColors(m, group, inventory, errors) {
        const rows = [], seen = new Set();
        try {
            const result = nativeQuery(m, 'AdvancedEdit.GetClothingQuery', [Il2Cpp.string(group.type).handle]);
            function walk(section) {
                const name = section.class.name;
                if (['TopCategory','ClothingTemplate'].includes(name)) {
                    for (const child of sequence(prop(section,'childSections'))) walk(child);
                } else if (['ColorGroup','ColorSubGroup'].includes(name)) {
                    for (const child of sequence(prop(section,'colors'))) walk(child);
                } else if (name === 'CommonColor') {
                    const owner = str(prop(section,'transferableGroupId'));
                    const path = prop(section,'elementKey'), descriptor = pathDescriptor(path);
                    const nativeKey = bindingIdentity(owner, descriptor);
                    if (seen.has(nativeKey)) return;
                    seen.add(nativeKey);
                    const ownerGroup = inventory.groups.find(g => g.id === owner);
                    const value = m.context.method('GetColorParameter').invoke(Il2Cpp.string(owner), path);
                    rows.push({data: {id: rowId(m, group, inventory.topology_fingerprint, ['worn', nativeKey]),
                        kind: 'color', type: 'color', units: 'native_rgba', min: 0, max: 1,
                        value: ['r','g','b','a'].map(c => value.field(c).value), editable: !!ownerGroup?.revision,
                        group_id: owner, group_fingerprint: ownerGroup?.fingerprint,
                        native_bindings: [descriptor], binding_keys: [nativeKey], source: 'worn_color_query',
                        shared_binding_identity: nativeKey, material_identity: null,
                        material_identity_status: 'not established by color query'},
                        prepare: value => prepareHistory(m,owner,'color',descriptor,value)});
                }
            }
            for (const section of sequence(prop(result,'sections'))) walk(section);
        } catch (error) { errors.push({source: 'GetClothingQuery', error: String(error)}); }
        return rows;
    }
    function collect(m, id) {
        const {inventory, group} = exactGroup(m,id), errors = [...inventory.errors];
        const typed = typedRows(m,group,inventory,errors);
        const rows = [...typed, ...rawRows(m,group,inventory,typed,errors), ...wornColors(m,group,inventory,errors)];
        for (const row of rows) {
            const aliases = rows.filter(other => other !== row && JSON.stringify(other.data.binding_keys) === JSON.stringify(row.data.binding_keys));
            row.data.alias_ids = aliases.map(other => other.data.id);
        }
        return {rows, group, errors, model_token:m.token};
    }
    function validate(rows, changes) {
        if (!Array.isArray(changes) || changes.length < 1 || changes.length > 64) throw Error('BATCH_SIZE: 1..64');
        const seen = new Set();
        const validated = changes.map(change => {
            if (!change || Object.keys(change).length !== 4 ||
                !['id','type','units','value'].every(key=>Object.hasOwn(change,key)))
                throw Error('INVALID_GROUP_CHANGE_FIELDS');
            const matches = rows.filter(r => r.data.id === change.id);
            if (matches.length !== 1) throw Error('UNKNOWN_OR_STALE_BINDING');
            const row = matches[0], d = row.data, value = change.value;
            if (!d.editable || !(row.write || row.prepare)) throw Error('BINDING_UNSUPPORTED: ' + d.unsupported_reason);
            if (change.type !== d.type || change.units !== d.units) throw Error('BINDING_TYPE_OR_UNITS_MISMATCH');
            if (d.binding_keys.some(k => seen.has(k))) throw Error('OVERLAPPING_BINDINGS');
            d.binding_keys.forEach(k => seen.add(k));
            const scalar = typeof value === 'number' && Number.isFinite(value);
            const valid = d.type === 'color' ? Array.isArray(value) && value.length === 4
                && value.every(v => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 1)
                : d.type === 'bool' ? typeof value === 'boolean'
                : d.type === 'float' && scalar && Number.isFinite(d.min) && Number.isFinite(d.max) && value >= d.min && value <= d.max;
            if (!valid) throw Error('INVALID_TYPED_NATIVE_VALUE');
            return {row, value};
        });
        const prepared = [];
        try {
            for (const change of validated) {
                const native = change.row.prepare ? change.row.prepare(change.value) : null;
                prepared.push({...change,native});
            }
        } catch (error) {
            prepared.forEach(change=>change.native?.release());
            throw error;
        }
        return prepared;
    }
    function makePath(descriptor, pin) {
        const key = value=>pin(Il2Cpp.string(value)).handle;
        const create = (name, args) => {
            const object = pin(cls('VRoidCore',pathNamespace + name).alloc());
            invokeManaged(object,'.ctor',args); return object;
        };
        if (descriptor.template_key !== null) {
            const template = create('TemplatePath',[key(descriptor.template_key)]);
            const plain = create(descriptor.path_type.replace('Template',''), [key(descriptor.element_key)]);
            return create(descriptor.path_type,[template.handle,plain.handle]);
        }
        return create(descriptor.path_type,[key(descriptor.element_key)]);
    }
    function prepareHistory(m, group, kind, descriptor, value) {
        const suffix = {blendshape:'BlendShapeTransform',color:'Color'}[kind];
        if (!suffix) throw Error('RAW_HISTORY_WRITER_UNSUPPORTED');
        const pathClass = cls('VRoidCore',pathNamespace + 'I' + suffix + 'Path');
        const valueClass = kind === 'color' ? cls('UnityEngine.CoreModule','UnityEngine.Color') : Il2Cpp.corlib.class('System.Single');
        const commandClass = cls('VRoidCore','VRoidCore.Editing.History.Command.Set' + suffix + 'ParameterCommand');
        const constructors = commandClass.methods.filter(method => method.name === '.ctor' && method.parameters.length === 3
            && method.parameters[0].type.name === 'System.String' && method.parameters[2].type.name === 'System.Boolean'
            && method.parameters[1].type.name.includes('IEnumerable') && method.parameters[1].type.name.includes(pathClass.name)
            && method.parameters[1].type.name.includes(valueClass.type.name));
        if (constructors.length !== 1) throw Error('RAW_HISTORY_CONSTRUCTOR_UNSUPPORTED');
        const handles = [], pin = object => { handles.push(retain(object)); return object; };
        const release = () => handles.splice(0).forEach(handle=>handle.free());
        try {
            const dictionaryClass = Il2Cpp.corlib.class('System.Collections.Generic.Dictionary`2').inflate(pathClass,valueClass);
            const dictionary = pin(dictionaryClass.alloc()), path = makePath(descriptor,pin);
            const add = dictionary.method('Add',2);
            if (add.parameters[0].type.name !== pathClass.type.name || add.parameters[1].type.name !== valueClass.type.name)
                throw Error('RAW_DICTIONARY_ABI_UNSUPPORTED');
            invokeManaged(dictionary,'.ctor',[]);
            const storage = Memory.alloc(kind === 'color' ? 16 : 4);
            if (kind === 'color') value.forEach((v,i) => storage.add(i*4).writeFloat(v));
            else storage.writeFloat(value);
            invokeManaged(dictionary,'Add',[path.handle,storage]);
            const command = pin(commandClass.alloc()), flag = Memory.alloc(1); flag.writeU8(1);
            invokeManaged(command,'.ctor',[Il2Cpp.string(group).handle,dictionary.handle,flag]);
            return {run:()=>invokeManaged(m.context,'ExecuteSyncCommand',[command.handle]),release};
        } catch (error) { release(); throw error; }
    }
    function executeHistory(m,group,kind,descriptor,value) {
        const command = prepareHistory(m,group,kind,descriptor,value);
        try { command.run(); } finally { command.release(); }
    }
    const sections = {
        Face:['FaceSkin','Eye','Eyes','Iris','Eyeball','Eyebrow','Eyelash','Eyeline','Mouth','Nose','Ear','Ears','Cheek','Highlight','Shadow'],
        Hairstyle:['AllHair','HairFront','HairBack','HairTied','HairSideburns','HairHanege','HairAhoge','BaseHair'],
        Body:['Arm','Chest','Hand','Head','Leg','Neck','Shoulder','Torso','Waist','WholeBody'],
        Outfit:['Tops','Bottoms','Onepiece','Shoes','Socks','InnerTop','InnerBottom','ClothingSet'],
        Accessories:['AccessoryNeck','AccessoryArm','Attachment']};
    function sectionFor(type) {
        // Full native namespace required. A matching suffix in an unrelated
        // enum namespace or a resource substring never authorizes a group.
        const prefix = 'TransferableGroupType.N00.Level1.';
        if (!type?.startsWith(prefix)) return null;
        const key = type.slice(prefix.length);
        return Object.keys(sections).find(section => sections[section].includes(key)) || null;
    }
    function categoryView(m, section) {
        const inventory = groupInventory(m), categories = new Map(), unknown = [];
        if (section != null && !Object.hasOwn(sections, section)) throw Error('UNKNOWN_SECTION');
        for (const group of inventory.groups.filter(g => g.active_leaf)) {
            const s = sectionFor(group.type);
            if (!s) { unknown.push(group); continue; }
            if (section && section !== s) continue;
            if (!categories.has(group.type)) categories.set(group.type, {id:group.type, category:group.type,
                section:s, label:group.type.split('.').pop(), group_ids:[]});
            categories.get(group.type).group_ids.push(group.id);
        }
        return {model_token:m.token,categories:[...categories.values()],unclassified_groups:unknown,
            errors:inventory.errors,ui_navigation:false,scope:'active leaf group discovery facade'};
    }
    function catalogRows(m,selectable) {
        const byId=new Map(),byResource=new Map();
        for(const entry of selectable){
            if(entry.clear)continue;
            const id=str(entry.p.method('get_TransferableGroupId').invoke()),list=byId.get(id)||[];
            if(entry.transferable_id!=null&&entry.transferable_id!==id)throw Error('CATALOG_OPTION_IDENTITY_CONFLICT');
            const identity=byResource.get(entry.resource_name);
            if(identity&&identity!==id)throw Error('CATALOG_OPTION_RESOURCE_CONFLICT');
            byResource.set(entry.resource_name,id);
            list.push(entry);byId.set(id,list);
        }
        const mainModel=prop(m.main,'_mainModel'),user=prop(mainModel,'playFabUser');
        const dictionary=user.method('GetTransferableGroupIdToPresetModel').invoke();
        if(!alive(dictionary))throw Error('CATALOG_DICTIONARY_UNAVAILABLE');
        const count=Array.isArray(dictionary)?dictionary.length:dictionary.method('get_Count').invoke();
        if(!Number.isInteger(count)||count<0||count>20000)throw Error('CATALOG_METADATA_LIMIT');
        const catalogPairs=sequence(dictionary,20000);
        if(catalogPairs.length!==count)throw Error('CATALOG_METADATA_INCOMPLETE');
        const ids=new Set();
        const result=catalogPairs.map(pair=>{
            const id=str(prop(pair,'Key')),p=prop(pair,'Value');
            if(!id||ids.has(id))throw Error('CATALOG_DUPLICATE_METADATA_ID');ids.add(id);
            const declared=str(prop(p,'transferableGroupId'));
            if(declared!==id)throw Error('CATALOG_METADATA_ID_MISMATCH');
            const resource=str(prop(p,'resourceName')),price=prop(p,'priceInCoin'),owned=prop(p,'isOwned');
            if(typeof owned!=='boolean'||!Number.isFinite(price)||!resource)throw Error('CATALOG_METADATA_INVALID');
            const options=byId.get(id)||[],segments=resource.split('/'),n=segments.indexOf('N00');
            if(options.some(e=>e.resource_name!==resource)||byResource.has(resource)&&byResource.get(resource)!==id)
                throw Error('CATALOG_CROSS_INVENTORY_IDENTITY_CONFLICT');
            return {id,resource_name:resource,owned,usable:owned||price===0,locked:!owned&&price!==0,
                price_in_coin:price,is_set_item:prop(p,'isSetItem'),catalog_only:options.length===0,
                selectable:options.some(e=>e.owned),selectable_preset_ids:options.map(e=>e.id),
                catalog_category:n>=2?segments.slice(n-2,n).join('/'):null,
                category_identity_status:'resource segments only; not a native section identity'};
        });
        if(!Array.isArray(dictionary)&&dictionary.method('get_Count').invoke()!==count)throw Error('CATALOG_METADATA_CHANGED');
        return result;
    }
    function catalogPage(m,args,selectable) {
        const offset = args.offset ?? 0, limit = args.limit ?? 100;
        if (!Number.isInteger(offset) || offset < 0 || !Number.isInteger(limit) || limit < 1 || limit > 200)
            throw Error('INVALID_PAGINATION');
        try {
            const all = catalogRows(m,selectable);
            const search = (args.search || '').toLowerCase();
            const matching = all.filter(row=>(args.owned_only===false || row.usable)
                && (!search || row.id.toLowerCase().includes(search) || (row.resource_name || '').toLowerCase().includes(search)))
                .sort((a,b)=>(a.resource_name || '').localeCompare(b.resource_name || '') || a.id.localeCompare(b.id));
            const next = offset+limit < matching.length ? offset+limit : null;
            return {available:true,source:'PlayFabUser.GetTransferableGroupIdToPresetModel',
                scope:'all native catalog categories; resource inference does not filter or authorize application',
                native_total:all.length,total:matching.length,offset,limit,next_offset:next,
                complete:offset===0 && next===null,page_complete:true,
                presets:matching.slice(offset,offset+limit),application_policy:'only fresh owned selectable_preset_ids may be applied'};
        } catch (error) {
            return {available:false,complete:false,page_complete:false,presets:[],error:String(error),offset,limit,next_offset:null};
        }
    }
    function registryMatch(m, expected) {
        const registry = m.root.field('_customItemRegistry').value;
        const matches = sequence(registry.field('_pathToFileCustomItemModels').value.method('get_Values').invoke())
            .filter(f => str(prop(f,'FilePath')).toLowerCase() === expected.path.toLowerCase());
        if (matches.length !== 1) throw Error('CUSTOM_ITEM_REGISTRY_PATH_STALE');
        const item = matches[0], custom = prop(item,'CustomItemId');
        const actual = {id:str(prop(item,'TransferableGroupId')),group_type:str(prop(item,'TransferableGroupTypeId')),
            path:str(prop(item,'FilePath')),resource_name:str(prop(item,'TransferableGroupResourceName')),
            revision:str(prop(item,'TransferableGroupRevision')),custom_resource_name:str(prop(custom,'ResourceName')),
            custom_revision:str(prop(custom,'Revision'))};
        if (Object.entries(actual).some(([k,v]) => expected[k] !== v)) throw Error('CUSTOM_ITEM_REGISTRY_IDENTITY_STALE');
        if (!registry.method('CheckIfIsRegisteredInAssetStorage').invoke(Il2Cpp.string(actual.resource_name)))
            throw Error('CUSTOM_ITEM_RESOURCE_STALE');
        return item;
    }
    function request(args, kind) {
        const m = requireModel(args), r = requests.get(args.request_id);
        if (!r || r.kind !== kind || r.token !== m.token) throw Error('UNKNOWN_OR_STALE_REQUEST');
        return {m,r};
    }
    function customLifetime(r) {
        if (!r.task || !r.task.method('get_IsCompleted').invoke())
            return {terminal:false,application_settled:false,reason:'native custom load has no terminal receipt'};
        if (!r.application_dispatched) return {terminal:true,application_settled:true};
        const s = H.teardownState();
        const ui = s.attached_state;
        const quiet = s.model_ready === true && s.model_token === r.token
            && ['command_busy','updating','presets_loading','photo_updating'].every(key=>s[key]===false)
            && s.png_decoder?.pending === 0 && !s.png_decoder.fatal
            && (!ui || (!ui.dialog && !ui.notification && ui.progress_locked===false && ui.popup_blocked===false));
        if (!quiet) {
            r.quiet = null;
            return {terminal:true,application_settled:false,reason:'native application is busy or model identity changed'};
        }
        const inventory = groupInventory(model(r.token));
        const matches = inventory.groups.filter(g=>g.active && g.id===r.item.id
            && g.type===r.item.group_type && g.resource_name===r.item.resource_name && g.revision===r.item.revision);
        if (!inventory.membership_complete || matches.length!==1) {
            r.quiet = null;
            return {terminal:true,application_settled:false,reason:'complete applied group identity not confirmed',
                discovery_errors:inventory.errors,source_completeness:inventory.source_completeness};
        }
        const signature = JSON.stringify([s.model_token,inventory.topology_fingerprint,ui?.history_revision,
            ui?.command_revision,ui?.file_path,ui?.unsaved]);
        if (!Number.isInteger(s.frame) || s.frame <= r.application_frame) {
            r.quiet = null;
            return {terminal:true,application_settled:false,reason:'no fresh post-dispatch frame observed'};
        }
        if (!r.quiet || r.quiet.signature!==signature) r.quiet = {signature,frame:s.frame,count:1};
        else if (s.frame!==r.quiet.frame) { r.quiet.frame=s.frame; r.quiet.count++; }
        return {terminal:true,application_settled:r.quiet.count>=3,quiet_frames:r.quiet.count,
            reason:r.quiet.count>=3?null:'awaiting consecutive distinct quiet native observations'};
    }
    function prepareTeardown() {
        const pending = [], ready = [];
        for (const [id,r] of requests) {
            if (r.kind!=='custom') continue;
            try {
                const evidence = customLifetime(r);
                if (!evidence.terminal || !evidence.application_settled) pending.push({request_id:id,...evidence});
                else ready.push([id,r]);
            } catch (error) { pending.push({request_id:id,error:String(error),terminal:false,application_settled:false}); }
        }
        if (pending.length) return {safe:false,pending_work:pending};
        // Do not sever any request's lifetime until every pending reader/apply
        // has terminal and settled evidence. Model replacement alone is not it.
        for (const [id,r] of ready) { r.handles.forEach(handle=>handle.free()); requests.delete(id); }
        return {safe:true,custom_requests_released:ready.length,pending_work:[]};
    }
    const sameValue = (a,b) => Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((v,i) => Math.abs(v-b[i]) < 1e-5);
    function colorSnapshot(m) {
        const inventory = groupInventory(m), rows = [], errors = [...inventory.errors];
        for (const group of inventory.groups.filter(g => g.active)) {
            const all = collect(m,group.id);
            for (const row of all.rows.filter(r => r.data.kind === 'color' && r.data.editable)) {
                const d = row.data, owner = inventory.groups.find(g => g.id === d.group_id);
                if (owner && d.native_bindings.length === 1 && !rows.some(r => r.key === d.binding_keys[0]))
                    rows.push({key:d.binding_keys[0],owner,descriptor:d.native_bindings[0],value:d.value});
            }
            errors.push(...all.errors);
        }
        return {rows,errors};
    }
    function preservationOutcomes(m,r,restore) {
        const after = colorSnapshot(m), outcomes = [];
        for (const previous of r.snapshot.rows) {
            // Owner resource and revision must remain exact, otherwise a same
            // semantic key in a new material is explicitly incompatible.
            const current = after.rows.find(row => row.key === previous.key);
            const outcome = {binding:previous.key,before:previous.value,original_identity:previous.owner,
                current_identity:current?.owner || null};
            if (!current || current.owner.fingerprint !== previous.owner.fingerprint) {
                outcomes.push({...outcome,status:'incompatible',reason:'exact owner/resource/revision/path identity changed'}); continue;
            }
            if (sameValue(previous.value,current.value)) {
                outcomes.push({...outcome,status:r.restored?.has(previous.key) ? 'restored' : 'preserved',after:current.value}); continue;
            }
            if (restore) {
                try {
                    executeHistory(m,current.owner.id,'color',current.descriptor,previous.value);
                    r.restored.add(previous.key);
                    outcomes.push({...outcome,status:'restoration_pending'});
                } catch (error) { outcomes.push({...outcome,status:'restoration_failed',error:String(error)}); }
            } else outcomes.push({...outcome,status:'restoration_failed',after:current.value,reason:'settled readback differs'});
        }
        outcomes.push({status:'unverified',reason:'texture/raster/material channel identities are outside established color-query coverage'});
        return {outcomes,discovery_errors:after.errors,frame:state.frame};
    }
    return {prepareTeardown,helpers:{prop,sequence,pathDescriptor,validate,sectionFor,catalogPage,catalogRows,groupInventory,
        membershipInventory:m=>groupInventory(m,false)},operations:{
        list_groups(args) {
            const m=requireModel(args),result=groupInventory(m);
            if(args.situation_root)try{result.situation_membership=situationMembership(m,args.situation_root,result);}
            catch(error){result.situation_membership={verified:false,error:String(error),root:args.situation_root};}
            if(args.situation_candidate)try{result.situation_definition=situationCandidate(m,args.situation_candidate);}
            catch(error){result.situation_definition={verified:false,error:String(error),root:args.situation_candidate};}
            return result;
        },
        list_group_parameters(args) {
            const result = collect(requireModel(args),args.group_id);
            if (args.kind != null && !['bone','blendshape','color','Bool','Float','Image','Template','unknown'].includes(args.kind)) throw Error('UNKNOWN_PARAMETER_KIND');
            return {...result,rows:undefined,parameters:result.rows.map(r=>r.data).filter(d=>!args.kind || d.kind === args.kind)};
        },
        set_group_parameters(args) {
            const m = requireModel(args), result = collect(m,args.group_id);
            const prepared = validate(result.rows,args.changes), applied = [];
            let attempted = 0;
            const count = () => prepared.slice(0,attempted).every(c=>!!c.native) ? attempted : null;
            try {
                for (const {row,value,native} of prepared) {
                    attempted++;
                    try { if (native) native.run(); else row.write(value);
                        applied.push({id:row.data.id,before:row.data.value,requested:value}); }
                    catch (error) { return {model_token:m.token,ok:false,partial:true,applied,error:String(error),frame:state.frame,
                        command_count:null,confirmed_raw_command_count:prepared.slice(0,applied.length).filter(c=>c.native).length,
                        attempted_binding_writes:attempted,
                        command_count_scope:'one raw history command per raw write; VM internal command count unknown',
                        history_policy:'native history; multiple commands/undo steps possible'}; }
                }
            } finally { prepared.forEach(c=>c.native?.release()); }
            return {model_token:m.token,ok:true,applied,command_count:count(),attempted_binding_writes:attempted,frame:state.frame,
                command_count_scope:'one raw history command per raw write; VM internal command count unknown',
                history_policy:'native history; multiple commands/undo steps possible'};
        },
        list_sections(args) {
            const result = categoryView(requireModel(args));
            return {...result,sections:Object.keys(sections).map(id=>({id,label:id,
                categories:result.categories.filter(c=>c.section===id)})).filter(s=>s.categories.length)};
        },
        list_categories(args) { return categoryView(requireModel(args),args.section); },
        enter_category(args) {
            const m = requireModel(args), result = categoryView(m,args.section);
            const matches = result.categories.filter(c=>c.id === args.category);
            if (matches.length !== 1) throw Error('UNKNOWN_CATEGORY: use exact native category ID');
            if (matches[0].group_ids.length !== 1) return {...result,ambiguous:true,group_ids:matches[0].group_ids,parameters:[]};
            return {...this.list_group_parameters({...args,group_id:matches[0].group_ids[0]}),ui_navigation:false};
        },
        remove_group(args) {
            const m = requireModel(args), {group} = exactGroup(m,args.group_id);
            if (!group.removable || group.fingerprint !== args.group_fingerprint) throw Error('NONREMOVABLE_OR_STALE_GROUP');
            const {ok,fail} = ordinary.managedCallbacks();
            invokeManaged(m.context,'RemoveTransferableGroupAndChildren',[Il2Cpp.string(group.id).handle,ok.handle,fail.handle]);
            return {model_token:m.token,frame:state.frame,expected_removed_ids:[group.id]};
        },
        custom_item_validate_begin(args) {
            const m = requireModel(args), item = registryMatch(m,args.registered_item);
            const id = String(++nextRequest);
            const r = {kind:'custom',token:m.token,task:null,handles:[retain(item)],fileModel:item,item:args.registered_item,
                metadata:args.metadata,completed:false};
            requests.set(id,r);
            r.task = item.method('LoadCustomItemContents').invoke();
            r.handles.push(retain(r.task));
            return {model_token:m.token,request_id:id,completed:false};
        },
        custom_item_validate_poll(args) {
            const {m,r} = request(args,'custom');
            if (r.completed) return r.result;
            if (!r.task.method('get_IsCompleted').invoke()) return {model_token:m.token,completed:false};
            r.completed = true;
            try {
                if (r.task.method('get_IsFaulted').invoke() || r.task.method('get_IsCanceled').invoke()) throw Error('NATIVE_CUSTOM_ITEM_LOAD_FAILED');
                const contents = r.task.method('get_Result').invoke();
                r.handles.push(retain(contents));
                const object = cls('VRoid.Studio','VRoid.Studio.ModelPresetsSelector.CustomItemSerializationUtil')
                    .method('DeserializeCustomItem').invoke(contents);
                r.handles.push(retain(object));
                if (object.method('IsNecessarilyMigrateBodySuitsCustomItemV2').invoke()) throw Error('CUSTOM_ITEM_MIGRATION_REQUIRED');
                const meta = prop(object,'customItemMetaData');
                for (const [field,key] of [['rootTransferableGroupId','id'],['rootTransferableGroupTypeId','group_type'],
                    ['rootTransferableGroupResourceName','resource_name'],['rootTransferableGroupRevision','revision']]) {
                    if (str(prop(meta,field)) !== r.item[key]
                        || (Object.hasOwn(r.metadata,field) && r.metadata[field] !== r.item[key]))
                        throw Error('NATIVE_CUSTOM_ITEM_ROOT_MISMATCH');
                }
                if (!r.metadata.rootTransferableGroupId || !r.metadata.rootTransferableGroupTypeId)
                    throw Error('NATIVE_CUSTOM_ITEM_ROOT_MISMATCH');
                const roots = sequence(prop(object,'transferableGroups')).filter(g=>str(prop(prop(g,'Header'),'Id'))===r.item.id);
                if (roots.length !== 1) throw Error('NATIVE_CUSTOM_ITEM_ROOT_NOT_UNIQUE');
                const header = prop(roots[0],'Header');
                if (str(prop(roots[0],'TypeId')) !== r.item.group_type || str(prop(header,'ResourceName')) !== r.item.resource_name
                    || str(prop(prop(header,'Custom'),'Revision')) !== r.item.revision) throw Error('NATIVE_CUSTOM_ITEM_TYPE_OR_REVISION_MISMATCH');
                if (!registryMatch(m,r.item).handle.equals(r.fileModel.handle)) throw Error('CUSTOM_ITEM_REGISTERED_MODEL_STALE');
                r.compatible = true;
                r.result = {model_token:m.token,completed:true,compatible:true,
                    evidence:'native LoadCustomItemContents + DeserializeCustomItem, root/type/revision and no required migration'};
            } catch (error) { r.result = {model_token:m.token,completed:true,compatible:false,error:String(error)}; }
            return r.result;
        },
        apply_registered_custom_item(args) {
            const {m,r} = request(args,'custom');
            if (!r.completed || !r.compatible || JSON.stringify(args.registered_item) !== JSON.stringify(r.item)) throw Error('CUSTOM_ITEM_NOT_VALIDATED');
            const registered = registryMatch(m,r.item);
            if (!registered.handle.equals(r.fileModel.handle)) throw Error('CUSTOM_ITEM_REGISTERED_MODEL_STALE');
            // Exact registered option, including file/resource/revision identity.
            // This route preserves the target's native custom-selection behavior.
            const c = cls('VRoid.Studio','VRoid.Studio.ModelPresetsSelector.CustomItemOptionViewModel');
            const options = Il2Cpp.gc.choose(c).filter(o=> {
                const context = o.field('_context').value, item = o.field('_model').value;
                return alive(context) && context.handle.equals(m.context.handle) && alive(item)
                    && item.handle.equals(registered.handle);
            });
            if (options.length !== 1) throw Error('CUSTOM_ITEM_OPTION_NOT_READY_OR_AMBIGUOUS');
            const enabled = Memory.alloc(1); enabled.writeU8(1);
            r.application_dispatched = true;
            r.application_frame = state.frame;
            invokeManaged(options[0],'set_IsSelected',[enabled]);
            return {model_token:m.token,frame:state.frame};
        },
        custom_item_validate_release(args) {
            const {r} = request(args,'custom');
            const evidence = customLifetime(r);
            if (!evidence.terminal || !evidence.application_settled) throw Error('CUSTOM_ITEM_NATIVE_WORK_PENDING: ' + JSON.stringify(evidence));
            r.handles.forEach(handle=>handle.free());
            requests.delete(args.request_id); return {released:true};
        },
        custom_item_application_state(args) {
            const {m,r} = request(args,'custom'), evidence = customLifetime(r);
            return {model_token:m.token,completed:evidence.terminal && evidence.application_settled,...evidence};
        },
        apply_preserving_preset(args) {
            const m = requireModel(args), matches = presetEntries(m,args.area).filter(e=>e.id===args.preset_id);
            if (matches.length !== 1 || !matches[0].owned) throw Error('UNKNOWN_OR_LOCKED_PRESET');
            const entry = matches[0];
            if (entry.clear || entry.resource_name?.startsWith('user/') || entry.is_set_item !== false)
                throw Error('PRESERVE_MODE_UNSUPPORTED: simple built-in preset with proven non-set metadata required');
            const partId = str(entry.p.method('get_TransferableGroupId').invoke());
            const registry = m.root.field('_customItemRegistry').value;
            if (!registry.field('_assetCatalog').value.method('ContainsId').invoke(Il2Cpp.string(partId))) throw Error('UNKNOWN_PART_ID');
            const snapshot = colorSnapshot(m), id = String(++nextRequest), before = groupInventory(m);
            requests.set(id,{kind:'preserve',token:m.token,snapshot,entry,partId,before,restored:new Set()});
            const {ok,fail} = ordinary.managedCallbacks(), flag = Memory.alloc(1); flag.writeU8(1);
            invokeManaged(m.context,'LoadAndReplaceTransferableGroup',[Il2Cpp.string(partId).handle,ok.handle,fail.handle,flag]);
            return {model_token:m.token,request_id:id,frame:state.frame};
        },
        preserving_preset_state(args) {
            const {m,r} = request(args,'preserve'), current = groupInventory(m);
            return {model_token:m.token,completed:current.groups.some(g=>g.active&&g.id===r.partId),groups:current.groups};
        },
        restore_preset_materials(args) {
            const {m,r} = request(args,'preserve');
            r.restoration = preservationOutcomes(m,r,true);
            return r.restoration;
        },
        preserved_preset_readback(args) {
            const {m,r} = request(args,'preserve'), result = preservationOutcomes(m,r,false);
            const failed = result.outcomes.some(o=>o.status==='restoration_failed');
            requests.delete(args.request_id);
            return {...result,ok:!failed,partial:failed,before_discovery_errors:r.snapshot.errors};
        }
    }};
}
