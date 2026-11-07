// Whole-group geometry adapted from mcjo79/vroid-mcp 0dc7d5e HairShape.cs (MIT).
// Copyright (c) 2026 mcjo79 and vroid-mcp contributors.
// Full notice: licenses/mcjo79-0dc7d5e.txt. No JS-owned managed callback enters history.
globalThis.createHairGroupNative = H => {
    const {model,cls,text,invokeManaged,retain,helpers,inventory,state}=H;
    const {seq,boxArgument,readPoint}=helpers, prop=H.groupHelpers.prop;
    const type=p=>p.class.type.name;
    const kind=p=>type(p)==='VRoidCore.Common.SpecificTypes.BrushHairGroupPath'?'brush'
        :type(p)==='VRoidCore.Common.SpecificTypes.ProceduralHairGroupPath'?'procedural':'unknown';
    function descriptor(p){
        const out={native_type:type(p)};
        for(const [name,key] of [['TransferableId','transferable_id'],['HairGroupId','group_id'],
            ['HairGroupletId','grouplet_id'],['HairStrandId','strand_id']])
            if(p.tryMethod('get_'+name))out[key]=text(prop(p,name));
        if(!out.transferable_id||!out.group_id)throw Error('HAIR_PATH_IDENTITY_UNAVAILABLE');
        if(type(p)==='VRoidCore.Common.SpecificTypes.BrushHairStrandPath'&&(!out.grouplet_id||!out.strand_id))
            throw Error('HAIR_FULL_BRUSH_PATH_REQUIRED');
        return out;
    }
    const scope=d=>[d.transferable_id,d.group_id,d.grouplet_id,d.strand_id].filter(x=>x!=null).join('/');
    const sameOwner=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
    function pin(s,o){if(o?.handle&&!o.handle.isNull())s.holds.push(retain(o));return o;}
    function release(s,mark){while(s.holds.length>mark)s.holds.pop().free();}
    function temporary(s,work){const mark=s.holds.length;try{return work();}finally{release(s,mark);}}
    function query(s,name,args){
        if(++s.queryCount>40000)throw Error('HAIR_TOTAL_QUERY_LIMIT');
        const q=pin(s,cls('VRoidCore','VRoidCore.Editing.Query.'+name).alloc());
        invokeManaged(q,'.ctor',args);
        return pin(s,invokeManaged(q,'Execute',[pin(s,prop(s.m.context,'ActiveModel')).handle]));
    }
    function identity(s){if(model(s.token).token!==s.token)throw Error('STALE_MODEL');}
    function pairs(raw){const rows=H.groupHelpers.sequence(raw);
        if(rows.length>1024)throw Error('HAIR_ACTIVE_LEAF_LIMIT');
        return rows.map(p=>Array.isArray(p)?p:[text(prop(p,'Key')),prop(p,'Value')]);}
    function leaves(s){return temporary(s,()=>pairs(pin(s,s.m.context.method('GetActiveLeafTransferables').invoke()))
        .map(([id,t])=>({transferable_id:id,owner_id:text(prop(t,'GroupId')),type:text(prop(t,'Type'))})));}
    function leafFor(s,id){
        const raw=pin(s,s.m.context.method('GetActiveLeafTransferables').invoke());
        const lookup=raw.tryMethod?.('get_Item',1);
        if(lookup?.parameters?.[0]?.type.name==='System.String'){const value=pin(s,lookup.invoke(Il2Cpp.string(id)));
            return {transferable_id:id,owner_id:text(prop(value,'GroupId')),type:text(prop(value,'Type'))};}
        const rows=pairs(raw).filter(([key])=>key===id);
        if(rows.length!==1)throw Error('HAIR_OWNERSHIP_AMBIGUOUS');
        return {transferable_id:id,owner_id:text(prop(rows[0][1],'GroupId')),type:text(prop(rows[0][1],'Type'))};
    }
    function activeOwner(s,id){
        const raw=pin(s,s.m.context.method('GetActiveLeafTransferableGroups').invoke());
        const contains=raw.tryMethod?.('ContainsKey',1);
        if(contains?.parameters?.[0]?.type.name==='System.String')return contains.invoke(Il2Cpp.string(id))===true;
        const lookup=raw.tryMethod?.('get_Item',1);
        if(lookup?.parameters?.[0]?.type.name==='System.String'){const value=pin(s,lookup.invoke(Il2Cpp.string(id)));return !!value&&!value.handle.isNull();}
        return pairs(raw).some(([key])=>key===id);
    }
    function owned(s,d,captured){
        identity(s);
        return temporary(s,()=>{
            const leaf=leafFor(s,d.transferable_id);
            if(d.transferable_type&&leaf.type!==d.transferable_type)throw Error('HAIR_OWNERSHIP_CHANGED');
            const owner=s.owners.get(leaf.owner_id);
            if(!owner?.active)throw Error('HAIR_OWNERSHIP_UNCONFIRMED');
            const current={id:owner.id,type:owner.type,resource_name:owner.resource_name,revision:owner.revision};
            if(captured){
                if(JSON.stringify(current)!==JSON.stringify(captured))throw Error('HAIR_OWNERSHIP_CHANGED');
                if(!activeOwner(s,captured.id))throw Error('HAIR_OWNERSHIP_CHANGED');
                const info=pin(s,s.m.context.method('GetActiveTransferableGroupInfo').invoke(Il2Cpp.string(captured.id)));
                if(!info||info.handle.isNull()||text(prop(info,'Type'))!==captured.type||
                    text(prop(info,'Revision'))!==captured.revision)throw Error('HAIR_OWNERSHIP_CHANGED');
                if(captured.resource_name!==undefined&&text(prop(info,'ResourceName'))!==captured.resource_name)
                    throw Error('HAIR_OWNERSHIP_CHANGED');
            }
            return current;
        });
    }
    function list(s,category,source){
        identity(s);
        const bindings=helpers.hairCategoryBindings(s.m),out=[],seen=new Set(),nativeRows=new Map();
        for(const leaf of leaves(s)){
            const matches=bindings.filter(b=>b.types.includes(leaf.type));
            if(!matches.length)continue;
            if(matches.length!==1)throw Error('HAIR_CATEGORY_BINDING_AMBIGUOUS');
            const cat=matches[0].category;
            if((category&&cat!==category)||(source&&leaf.transferable_id!==source.transferable_id))continue;
            const activeOwner=s.owners.get(leaf.owner_id);
            if(!activeOwner?.active)throw Error('HAIR_OWNERSHIP_UNCONFIRMED');
            const owner={id:activeOwner.id,type:activeOwner.type,resource_name:activeOwner.resource_name,revision:activeOwner.revision};
            if(source&&!sameOwner(owner,source.owner))throw Error('HAIR_OWNERSHIP_CHANGED');
            const paths=query(s,'GetHairGroupListQuery',[Il2Cpp.string(leaf.transferable_id).handle]);
            for(const p of seq(paths)){
                pin(s,p);const d=descriptor(p),id=scope(d);
                if(d.transferable_id!==leaf.transferable_id||d.strand_id||seen.has(id))throw Error('HAIR_GROUP_IDENTITY_AMBIGUOUS');
                seen.add(id);if(seen.size>128)throw Error('HAIR_GROUP_BATCH_LIMIT');
                const row={scope:id,category:cat,type:kind(p),...d,transferable_type:leaf.type,owner};
                out.push(row);nativeRows.set(id,{...row,path:p});
            }
        }
        s.groups=nativeRows;s.readMark=s.holds.length;
        return out;
    }
    function group(s,category,id,resolved){
        if(!resolved)list(s,category);
        const row=s.groups.get(id);
        if(!row)throw Error('UNKNOWN_OR_STALE_HAIR_GROUP');
        if(resolved&&(row.transferable_id!==resolved.transferable_id||JSON.stringify(row.owner)!==JSON.stringify(resolved.owner)))
            throw Error('HAIR_GROUP_IDENTITY_CHANGED');
        return row;
    }
    function material(s,path,strand){
        const ps=query(s,strand?'GetBrushHairStrandParameterSetQuery':'GetBrushHairGroupParameterSetQuery',[path.handle]);
        const ref=pin(s,prop(ps,'HairMaterialReference'));
        if(ref.handle.isNull())return null;
        const discriminator=prop(ref,'Type').field('value__').value;
        if(discriminator!==0&&discriminator!==1)throw Error('UNKNOWN_HAIR_MATERIAL_REFERENCE_TYPE');
        return {type:discriminator,id:text(prop(ref,discriminator===0?'SharedHairMaterialId':'TransferableMaterialId'))};
    }
    function configured(s,path){const ps=query(s,'GetProceduralHairGroupParameterSetQuery',[path.handle]);
        const form=pin(s,prop(ps,'ProceduralFormParameterSet'));return {length:prop(form,'Length'),hair_count:prop(form,'HairCount')};}
    function procedural(s,category,id){
        if(H.assemblySha256!=='ed65ebbc1e806db635566347a9022b9577f6b3d373db128ea23f0e862e005296')
            throw Error('PROCEDURAL_DESCRIPTOR_UNVERIFIED_BUILD: no property was created or written');
        const g=group(s,category,id);
        if(g.type!=='procedural')throw Error('NOT_A_PROCEDURAL_HAIR_GROUP');
        let property,fallbackReason;
        try{property=pin(s,helpers.existingHairGroupProperty(s.m,g.path));}
        catch(error){if(!String(error).includes('PROCEDURAL_EXISTING_PROPERTY_REQUIRED'))throw error;fallbackReason=String(error);}
        const current=configured(s,g.path);
        const controls=property?createProceduralHairBindings({assemblySha256:H.assemblySha256,prop,seq,text,
            pin:o=>pin(s,o),invokeManaged,boxArgument})({property,path:g.path,engine:s.m.engine})
            :createProceduralHairFallback({assemblySha256:H.assemblySha256,cls,prop,invokeManaged,boxArgument,
                boxMethodInfo(method){const storage=Memory.alloc(Process.pointerSize);storage.writePointer(method.handle);return storage;},
                pin:o=>pin(s,o),validate(){
                    owned(s,g,g.owner);
                    const valid=query(s,'GetIsPathValidQuery',[g.path.handle]).unbox().field('m_value').value;
                    if(valid!==true)throw Error('PROCEDURAL_PATH_INVALID');
                },execute:command=>invokeManaged(s.m.context,'ExecuteSyncCommand',[command.handle])})({path:g.path,configured:current});
        return {configured:current,fallback_reason:fallbackReason,
            identity:{scope:g.scope,transferable_id:g.transferable_id,group_id:g.group_id,owner:g.owner},
            controls:controls.map(c=>({...c,write(value,onInvoke){owned(s,g,g.owner);c.write(value,onInvoke);}}))};
    }
    function snapshot(s,category,id,resolved){
        const g=group(s,category,id,resolved),path=g.path;
        const children=seq(query(s,'GetHairGroupChildrenQuery',[path.handle]));
        if(children.length>256)throw Error('HAIR_BATCH_LIMIT');
        let total=0;const ids=new Set();
        const strands=children.map(p=>{
            pin(s,p);const d=descriptor(p),sid=scope(d);
            if(d.transferable_id!==g.transferable_id||d.group_id!==g.group_id||!d.strand_id)
                throw Error('HAIR_CHILD_PATH_IDENTITY_MISMATCH');
            if(ids.has(sid))throw Error('DUPLICATE_HAIR_STRAND_IDENTITY');ids.add(sid);
            const count=query(s,'GetHairStrandControlPointCountQuery',[p.handle]).unbox().field('m_value').value;
            if(!Number.isInteger(count)||count<0||count>512)throw Error('UNEXPECTED_CONTROL_POINT_COUNT');
            total+=count;s.pointReads+=count;
            if(total>4096||s.pointReads>32768)throw Error('HAIR_TOTAL_POINT_LIMIT');
            if(resolved?.point_budget!=null&&total>resolved.point_budget)throw Error('HAIR_AGGREGATE_POINT_LIMIT');
            const points=[];
            for(let index=0;index<count;index++){
                const boxed=query(s,'GetHairStrandControlPointQuery',[p.handle,boxArgument('int',index)]);
                s.points.set(JSON.stringify([sid,index]),{boxed,path:p,group:id,
                    descriptor:{...d,transferable_type:g.transferable_type},owner:g.owner});
                points.push(readPoint(boxed));
            }
            const brush=type(p)==='VRoidCore.Common.SpecificTypes.BrushHairStrandPath';
            return {id:sid,...d,type:brush?'brush':type(p)==='VRoidCore.Common.SpecificTypes.ProceduralHairStrandPath'?'procedural':'unknown',
                material:brush?material(s,p,true):null,points};
        });
        const transform=query(s,'GetGuideOriginTransformQuery',[path.handle]).unbox(),guide={};
        for(const [field,channels] of [['Position',['x','y','z']],['Rotation',['x','y','z','w']],['Scale',['x','y','z']]])
            guide[field]=channels.map(k=>transform.field(field).value.field(k).value);
        const {path:unused,...row}=g;
        return {...row,strands,...(g.type==='procedural'?{configured:configured(s,path),procedural_length_units:'native_procedural_parameter'}:{}),
            material:g.type==='brush'?material(s,path,false):null,guide};
    }
    return {
        begin(args){
            const m=model(args.expected_model),screen=prop(prop(prop(m.main,'GlobalBus'),'ScreenNavigation'),'ActiveScreen');
            if(screen.class.type.name!=='VRoid.Studio.EditRootScreen.ViewModel')throw Error('ORDINARY_EDIT_SCREEN_REQUIRED');
            const membership=inventory(m);
            if(membership.membership_complete!==true)throw Error('HAIR_OWNERSHIP_INCOMPLETE');
            if(membership.groups.length>1024)throw Error('HAIR_MEMBERSHIP_LIMIT');
            const owners=new Map(membership.groups.map(g=>[g.id,g]));
            if(owners.size!==membership.groups.length)throw Error('HAIR_OWNERSHIP_AMBIGUOUS');
            return {m,token:m.token,frame:state.frame,inventory:membership,owners,holds:[],points:new Map(),groups:new Map(),queryCount:0,pointReads:0,readMark:0};
        },
        end(s){release(s,0);s.points.clear();},identity,list,snapshot,procedural,
        releaseRead(s){release(s,s.readMark);s.points.clear();},
        move(s,id,strand,index,point,onInvoke){
            const cp=s.points.get(JSON.stringify([strand,index]));
            if(!cp||cp.group!==id)throw Error('STALE_HAIR_POINT_SNAPSHOT');
            owned(s,cp.descriptor,cp.owner);
            return temporary(s,()=>{
                const value=cp.boxed.unbox(),v=value.field('<Point>k__BackingField').value;
                ['x','y','z'].forEach((k,i)=>{v.field(k).value=Math.fround(point.point[i]);});
                const command=pin(s,cls('VRoidCore','VRoidCore.Editing.History.Command.MoveBrushHairStrandControlPointCommand').alloc());
                invokeManaged(command,'.ctor',[cp.path.handle,boxArgument('int',index),value.handle]);
                onInvoke?.();invokeManaged(s.m.context,'ExecuteSyncCommand',[command.handle]);
            });
        },
        clone(s,category,id,onInvoke,captured){
            const g=group(s,category,id);
            if(g.type!=='brush')throw Error('NOT_A_BRUSH_HAIR_GROUP');
            if(captured&&(g.group_id!==captured.group_id||g.native_type!==captured.native_type))throw Error('CLONE_SOURCE_IDENTITY_CHANGED');
            owned(s,g,captured?.owner||g.owner);
            return temporary(s,()=>{
                const command=pin(s,cls('VRoidCore','VRoidCore.Editing.History.Command.CloneBrushHairGroupCommand').alloc());
                invokeManaged(command,'.ctor',[g.path.handle]);onInvoke?.();
                invokeManaged(s.m.context,'ExecuteSyncCommand',[command.handle]);
            });
        },
    };
};
globalThis.createHairGroupApi = ({adapter}) => {
    const categories=['HairFront','HairBack','AllHair','HairTied','HairSideburns','HairAhoge','HairHanege'];
    const metadata={coordinate_space:'native_control_point',units:'native_control_point_coordinates',
        rendered_strand_length:null,geometry_measurement:'mean control-point polyline length; guide transform not applied'};
    const finite=x=>typeof x==='number'&&Number.isFinite(x),same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
    function validate(args,scoped=false){
        if(typeof args.expected_model!=='string'||!args.expected_model)throw Error('EXPECTED_MODEL_REQUIRED');
        if((scoped||args.category!=null)&&!categories.includes(args.category))throw Error('HAIR_PART_CATEGORY_REQUIRED');
        if(scoped&&(typeof args.scope!=='string'||!args.scope))throw Error('HAIR_GROUP_SCOPE_REQUIRED');
    }
    function snapshot(s,args,id=args.scope,resolved){
        adapter.identity(s);const g=adapter.snapshot(s,args.category,id,resolved);
        if(!g)throw Error('UNKNOWN_HAIR_GROUP');
        if(g.strands.length>256||new Set(g.strands.map(x=>x.id)).size!==g.strands.length)throw Error('HAIR_STRAND_LIMIT_OR_AMBIGUITY');
        let count=0;
        for(const strand of g.strands){
            if(strand.points.length>512)throw Error('UNEXPECTED_CONTROL_POINT_COUNT');
            count+=strand.points.length;if(count>4096)throw Error('HAIR_BATCH_LIMIT');
            if(strand.transferable_id!=null&&(strand.transferable_id!==g.transferable_id||strand.group_id!==g.group_id))
                throw Error('HAIR_CHILD_PATH_IDENTITY_MISMATCH');
            for(const p of strand.points)for(const [key,n] of [['point',3],['normal',3],['uv',2]])
                if(!Array.isArray(p[key])||p[key].length!==n||!p[key].every(finite))throw Error('INVALID_NATIVE_CONTROL_POINT');
        }
        return g;
    }
    function stats(g){
        const lengths=g.strands.map(s=>s.points.slice(1).reduce((sum,p,i)=>sum+Math.hypot(...p.point.map((v,k)=>v-s.points[i].point[k])),0));
        return {...g,strands:g.strands.map((s,i)=>({id:s.id,type:s.type,control_point_count:s.points.length,control_point_polyline_length:lengths[i]})),
            strand_count:g.strands.length,control_point_polyline_length:lengths.length?lengths.reduce((a,b)=>a+b,0)/lengths.length:0,...metadata};
    }
    function run(args,work){const s=adapter.begin(args);try{return work(s);}finally{adapter.end(s);}}
    function receipt(args,procedural=false){return {model_token:args.expected_model,source_scope:args.scope,category:args.category,
        ok:false,partial:false,uncertain:false,dispatch_state:'prewrite_rejected',native_invocation_attempted:false,
        command_count:procedural?null:0,attempted_commands:procedural?null:0,
        ...(procedural?{setter_count:0,attempted_setters:0}:{}),history_entry_count:null,
        history_evidence:procedural?'native VM setter calls; actual command and undo-entry delta unobserved':
            'completed explicit ExecuteSyncCommand calls; merged undo-entry delta unobserved',
        completed_points:[],verified_points:[],changed_points:[],affected_points:0,affected_strands:0,...metadata};}
    function fail(result,error){
        result.error=String(error);result.ok=false;
        const attempted=(result.attempted_commands||result.attempted_setters||0),completed=(result.command_count||result.setter_count||0);
        result.uncertain=attempted>0;result.partial=completed>0;
        result.dispatch_state=attempted?'invocation_unconfirmed':'prewrite_rejected';
    }
    function mutate(args,procedural,work){
        const result=receipt(args,procedural);let s;
        try{validate(args,true);s=adapter.begin(args);result.model_token=s.token;result.frame=s.frame;work(s,result);}
        catch(error){fail(result,error);}finally{if(s)adapter.end(s);}
        return result;
    }
    const brush=g=>{if(g.type!=='brush')throw Error('NOT_A_BRUSH_HAIR_GROUP');
        if(g.strands.some(s=>s.type!=='brush'))throw Error('NONBRUSH_GROUP_CHILD');};
    const preservation=g=>({material:g.material,guide:g.guide,strands:g.strands.map(s=>({id:s.id,material:s.material,
        points:s.points.map(p=>({normal:p.normal,uv:p.uv}))}))});
    function verify(result,before,after,plan,complete){
        if(!same(preservation(before),preservation(after)))throw Error('HAIR_PRESERVATION_READBACK_MISMATCH');
        const actual=new Map(after.strands.map(s=>[s.id,s])),completed=new Set(result.completed_points.map(p=>JSON.stringify([p.strand_id,p.index])));
        result.verified_points=[];result.changed_points=[];let mismatch=false;
        for(const p of plan){
            if(!complete&&!completed.has(JSON.stringify([p.strand,p.index])))continue;
            const got=actual.get(p.strand)?.points[p.index]?.point,expected=p.point.point.map(Math.fround);
            const matches=got&&got.length===3&&got.every((v,k)=>v===expected[k]);
            if(!matches){mismatch=true;continue;}
            const identity={strand_id:p.strand,index:p.index};result.verified_points.push(identity);
            if(got.some((v,k)=>v!==p.original[k]))result.changed_points.push(identity);
        }
        result.affected_points=result.changed_points.length;
        result.affected_strands=new Set(result.changed_points.map(p=>p.strand_id)).size;
        if(mismatch)throw Error('HAIR_POINT_READBACK_MISMATCH');
    }
    function transform(args,kind){return mutate(args,false,(s,result)=>{
        if(kind==='scale'&&(!finite(args.factor)||args.factor<=0||args.factor>10))throw Error('INVALID_FACTOR');
        if(kind==='clone'&&(!Array.isArray(args.offset)||args.offset.length!==3||!args.offset.every(finite)))throw Error('INVALID_OFFSET');
        const before=snapshot(s,args);brush(before);
        const planFor=g=>g.strands.flatMap(strand=>strand.points.map((cp,index)=>{
            const point=cp.point.map((v,k)=>kind==='scale'?strand.points[0].point[k]+(v-strand.points[0].point[k])*args.factor:v+args.offset[k]);
            if(!point.every(x=>finite(x)&&Number.isFinite(Math.fround(x))))throw Error('NONFINITE_TRANSFORM_RESULT');
            return {strand:strand.id,index,original:cp.point,point:{...cp,point:point.map(Math.fround)}};
        }).filter(p=>kind==='clone'||p.index>0));
        let target=before,plan=planFor(before),targetConfirmed=kind==='scale';
        const invoke=()=>{result.attempted_commands++;result.native_invocation_attempted=true;result.dispatch_state='invoked';};
        try{
            if(kind==='clone'){
                const initial=adapter.list(s,args.category,before),ids=new Set(initial.map(g=>g.scope));
                const original=g=>g.scope===before.scope&&g.transferable_id===before.transferable_id&&g.group_id===before.group_id&&
                    g.native_type===before.native_type&&g.type===before.type&&same(g.owner,before.owner);
                if(!initial.some(original))
                    throw Error('CLONE_SOURCE_IDENTITY_CHANGED');
                adapter.clone(s,args.category,args.scope,invoke,before);result.command_count++;
                adapter.identity(s);const current=adapter.list(s,args.category,before);
                if(!current.some(original))
                    throw Error('CLONE_SOURCE_IDENTITY_CHANGED');
                const added=current.filter(g=>!ids.has(g.scope));result.added_group_ids=added.map(g=>g.scope);
                if(added.length!==1)throw Error('CLONE_IDENTITY_UNCONFIRMED');
                const row=added[0];
                if(row.transferable_id!==before.transferable_id||!same(row.owner,before.owner)||row.group_id===before.group_id)
                    throw Error('CLONE_DESTINATION_IDENTITY_MISMATCH');
                result.new_scope=row.scope;target=snapshot(s,args,row.scope);brush(target);
                if(target.transferable_id!==before.transferable_id||!same(target.owner,before.owner))throw Error('CLONE_DESTINATION_IDENTITY_MISMATCH');
                result.new_strand_ids=target.strands.map(x=>x.id);result.cloned_strand_count=target.strands.length;
                result.cloned_point_count=target.strands.reduce((n,x)=>n+x.points.length,0);
                const shape=g=>({material:g.material,guide:g.guide,strands:g.strands.map(x=>({material:x.material,points:x.points}))});
                if(!same(shape(before),shape(target)))throw Error('CLONE_COPY_UNCONFIRMED');
                plan=planFor(target);targetConfirmed=true;
            }
            const writes=kind==='clone'&&args.offset.every(x=>x===0)?[]:plan;
            for(const p of writes){
                adapter.identity(s);adapter.move(s,target.scope,p.strand,p.index,p.point,invoke);
                result.command_count++;result.completed_points.push({strand_id:p.strand,index:p.index});
            }
            const after=snapshot(s,args,target.scope);
            verify(result,target,after,plan,true);
            if(kind==='scale')for(const strand of target.strands){
                const root=after.strands.find(x=>x.id===strand.id)?.points[0]?.point;
                if(!same(root,strand.points[0]?.point))throw Error('HAIR_ROOT_READBACK_MISMATCH');
            }
            result.ok=true;result.dispatch_state='completed';result.readback=stats(after);result.verification_snapshot=after;
        }catch(error){
            fail(result,error);
            if(targetConfirmed&&result.attempted_commands){
                try{const after=snapshot(s,args,target.scope);verify(result,target,after,plan,false);result.observed_readback=stats(after);}
                catch(readbackError){result.readback_error=String(readbackError);}
            }
        }
    });}
    function proceduralChanges(args){
        const changes=['length','hair_count'].filter(k=>args[k]!=null).map(key=>({key,value:args[key]}));
        if(!changes.length)throw Error('PROCEDURAL_CHANGES_REQUIRED');
        for(const {key,value} of changes)if(!finite(value)||(key==='hair_count'&&(!Number.isInteger(value)||value<=0)))throw Error('INVALID_PROCEDURAL_'+key);
        return changes;
    }
    function setProcedural(args){return mutate(args,true,(s,result)=>{
        const changes=proceduralChanges(args);
        if(changes.length!==1)throw Error('PROCEDURAL_SINGLE_SETTLED_STEP_REQUIRED');
        const native=adapter.procedural(s,args.category,args.scope),{key,value}=changes[0];
        if(args.expected_identity&&!same(args.expected_identity,native.identity))throw Error('PROCEDURAL_OWNER_IDENTITY_CHANGED');
        const requested=key==='length'?Math.fround(value):value;
        const c=native.controls.find(x=>x.key===key);
        if(!c||!finite(requested)||requested<c.min||requested>c.max)throw Error('PROCEDURAL_NATIVE_RANGE');
        if(c.native_route==='command'){
            result.command_count=0;result.attempted_commands=0;
            result.history_evidence='completed explicit native managed-modifier command calls; merged undo-entry delta unobserved';
        }
        result.native_route=c.native_route||'native_vm_setter';result.fallback_reason=native.fallback_reason;
        result.before=native.configured;result.controls=native.controls.map(({write,...x})=>x);
        result.requested_configured={...native.configured,[key]:requested};
        result.verification_identity=native.identity||{scope:args.scope,type:'procedural'};
        result.procedural_length_units='native_procedural_parameter';
        if(native.configured[key]!==requested){
            adapter.identity(s);c.write(value,()=>{
                if(c.native_route==='command')result.attempted_commands++;else result.attempted_setters++;
                result.native_invocation_attempted=true;result.dispatch_state='invoked';
            });
            if(c.native_route==='command')result.command_count++;else result.setter_count++;
        }
        result.ok=true;result.dispatch_state='completed';result.verification_pending=true;
    });}
    return {operations:{
        get_procedural_hair_controls(args){validate(args,true);return run(args,s=>{
            const n=adapter.procedural(s,args.category,args.scope);
            return {model_token:s.token,configured:n.configured,identity:n.identity,fallback_reason:n.fallback_reason,controls:n.controls.map(({write,...x})=>x)};
        });},
        set_procedural_hair:setProcedural,
        get_hair_group_state(args){validate(args,true);return run(args,s=>{const g=snapshot(s,args);return {model_token:s.token,group:g,stats:stats(g)};});},
        list_hair_groups(args){validate(args);return run(args,s=>{
            const rows=adapter.list(s,args.category);if(rows.length>128)throw Error('HAIR_GROUP_BATCH_LIMIT');
            const groups=[];let total=0;
            for(const row of rows)try{
                const g=snapshot(s,{...args,category:row.category},row.scope,{...row,point_budget:8192-total});
                total+=g.strands.reduce((n,x)=>n+x.points.length,0);if(total>8192)throw Error('HAIR_AGGREGATE_POINT_LIMIT');
                groups.push(stats(g));
            }finally{adapter.releaseRead?.(s);}
            adapter.identity(s);return {model_token:s.token,groups,...metadata};
        });},
        scale_brush_hair:args=>transform(args,'scale'),clone_brush_hair:args=>transform(args,'clone'),
    }};
};
