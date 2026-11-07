// Whole-group geometry adapted from mcjo79/vroid-mcp 0dc7d5e HairShape.cs (MIT).
// Copyright (c) 2026 mcjo79 and vroid-mcp contributors.
// Full notice: licenses/mcjo79-0dc7d5e.txt. No managed callback enters history.
globalThis.createHairGroupNative = H => {
    const {model,cls,text,invokeManaged,retain,helpers,inventory,state}=H;
    const {hairDesignEditor,hairNodeList,seq,boxArgument,readPoint}=helpers;
    const categories=['HairFront','HairBack','AllHair','HairTied','HairSideburns','HairAhoge','HairHanege'];
    const type=p=>p.class.type.name;
    const kind=p=>type(p)==='VRoidCore.Common.SpecificTypes.BrushHairGroupPath'?'brush'
        :type(p)==='VRoidCore.Common.SpecificTypes.ProceduralHairGroupPath'?'procedural':'unknown';
    const prop=H.groupHelpers.prop;
    const id=p=>['TransferableId','HairGroupId','HairStrandId'].filter(k=>p.tryMethod('get_'+k))
        .map(k=>text(prop(p,k))).join('/');
    function pin(s,o){if(o?.handle&&!o.handle.isNull())s.holds.push(retain(o));return o;}
    function query(s,name,args){
        const q=pin(s,cls('VRoidCore','VRoidCore.Editing.Query.'+name).alloc());
        invokeManaged(q,'.ctor',args);
        return pin(s,invokeManaged(q,'Execute',[pin(s,prop(s.m.context,'ActiveModel')).handle]));
    }
    function identity(s){
        const current=model(s.token);
        if(current.token!==s.token)throw Error('STALE_MODEL');
    }
    function owned(s,path){
        const inv=inventory(s.m);
        if(inv.membership_complete!==true)throw Error('HAIR_OWNERSHIP_INCOMPLETE');
        const raw=s.m.context.method('GetActiveLeafTransferables').invoke();
        const pairs=H.groupHelpers.sequence(raw).map(p=>Array.isArray(p)?p:[text(prop(p,'Key')),prop(p,'Value')]);
        const tid=text(prop(path,'TransferableId'));
        const matches=pairs.filter(([key])=>key===tid);
        if(matches.length!==1)throw Error('HAIR_OWNERSHIP_UNCONFIRMED');
        const owner=text(prop(matches[0][1],'GroupId'));
        if(!inv.groups.some(g=>g.id===owner&&g.active))throw Error('HAIR_OWNERSHIP_UNCONFIRMED');
    }
    function list(s,category){
        identity(s);const seen=new Set(),out=[];
        for(const cat of category?[category]:categories){
            const design=pin(s,hairDesignEditor(s.m,cat));
            const tids=new Map();
            for(const node of hairNodeList(design).filter(n=>n.parent===null)){
                const p=pin(s,prop(node.n,'HairGroupPath'));
                tids.set(text(prop(p,'TransferableId')),p);
            }
            for(const [tid,example] of tids){
                owned(s,example);
                const groups=query(s,'GetHairGroupListQuery',[Il2Cpp.string(tid).handle]);
                for(const path of seq(groups)){
                    pin(s,path);const scope=id(path);
                    if(seen.has(scope))continue;seen.add(scope);
                    out.push({scope,category:cat,type:kind(path),native_type:type(path),path});
                }
            }
        }
        return out;
    }
    function group(s,category,scope){
        const rows=list(s,category).filter(g=>g.scope===scope);
        if(rows.length!==1)throw Error('UNKNOWN_OR_STALE_HAIR_GROUP');
        return rows[0];
    }
    function material(s,path,strand){
        const ps=query(s,strand?'GetBrushHairStrandParameterSetQuery':'GetBrushHairGroupParameterSetQuery',[path.handle]);
        const ref=pin(s,prop(ps,'HairMaterialReference'));
        if(ref.handle.isNull())return null;
        // Keep the two native identities distinct; do not collapse shared and transferable IDs.
        return {shared:text(prop(ref,'SharedHairMaterialId')),transferable:text(prop(ref,'TransferableMaterialId'))};
    }
    function configured(s,path){
        const ps=query(s,'GetProceduralHairGroupParameterSetQuery',[path.handle]);
        const form=pin(s,prop(ps,'ProceduralFormParameterSet'));
        return {length:prop(form,'Length'),hair_count:prop(form,'HairCount')};
    }
    function procedural(s,category,scope){
        const g=group(s,category,scope);
        if(g.type!=='procedural')throw Error('NOT_A_PROCEDURAL_HAIR_GROUP');
        const property=pin(s,helpers.hairGroupProperty(s.m,category,scope));
        const bindings=createProceduralHairBindings({assemblySha256:H.assemblySha256,prop,seq,text,
            pin:o=>pin(s,o),invokeManaged,boxArgument});
        return {configured:configured(s,g.path),controls:bindings({property,path:g.path,engine:s.m.engine})};
    }
    function snapshot(s,category,scope){
        const g=group(s,category,scope),path=g.path;
        const children=seq(query(s,'GetHairGroupChildrenQuery',[path.handle]));
        if(children.length>256)throw Error('HAIR_BATCH_LIMIT');
        let total=0;
        const strands=children.map(p=>{
            pin(s,p);
            const count=query(s,'GetHairStrandControlPointCountQuery',[p.handle]).unbox().field('m_value').value;
            if(!Number.isInteger(count)||count<0||count>512)throw Error('UNEXPECTED_CONTROL_POINT_COUNT');
            total+=count;if(total>4096)throw Error('HAIR_BATCH_LIMIT');
            const strandId=id(p),points=[];
            for(let index=0;index<count;index++){
                const boxed=query(s,'GetHairStrandControlPointQuery',[p.handle,boxArgument('int',index)]);
                // Query returns a complete boxed value copy. Keep its owner pinned until
                // command construction/execution finishes; modify only Point in that copy.
                s.points.set(strandId+'/'+index,{boxed,path:p,group:scope});
                points.push(readPoint(boxed));
            }
            const brush=type(p)==='VRoidCore.Common.SpecificTypes.BrushHairStrandPath';
            return {id:strandId,type:brush?'brush':type(p)==='VRoidCore.Common.SpecificTypes.ProceduralHairStrandPath'?'procedural':'unknown',
                material:brush?material(s,p,true):null,points};
        });
        const transform=query(s,'GetGuideOriginTransformQuery',[path.handle]).unbox();
        const guide={};
        for(const [field,channels] of [['Position',['x','y','z']],['Rotation',['x','y','z','w']],['Scale',['x','y','z']]]){
            const v=transform.field(field).value;guide[field]=channels.map(k=>v.field(k).value);
        }
        return {scope,category,type:g.type,native_type:g.native_type,strands,
            ...(g.type==='procedural'?{configured:configured(s,path),procedural_length_units:'native_procedural_parameter'}:{}),
            material:g.type==='brush'?material(s,path,false):null,guide};
    }
    return {
        begin(args){
            const m=model(args.expected_model);
            const screen=prop(prop(prop(m.main,'GlobalBus'),'ScreenNavigation'),'ActiveScreen');
            if(screen.class.type.name!=='VRoid.Studio.EditRootScreen.ViewModel')throw Error('ORDINARY_EDIT_SCREEN_REQUIRED');
            return {m,token:m.token,frame:state.frame,holds:[],points:new Map()};
        },
        end(s){for(const hold of s.holds.reverse())hold.free();s.points.clear();},identity,
        list:(s,category)=>list(s,category).map(({path,...g})=>g),snapshot,procedural,
        move(s,scope,strand,index,point){
            identity(s);
            const cp=s.points.get(strand+'/'+index);
            if(!cp||cp.group!==scope)throw Error('STALE_HAIR_POINT_SNAPSHOT');
            owned(s,cp.path);
            const value=cp.boxed.unbox(),v=value.field('<Point>k__BackingField').value;
            ['x','y','z'].forEach((k,i)=>{v.field(k).value=point.point[i];});
            const command=pin(s,cls('VRoidCore','VRoidCore.Editing.History.Command.MoveBrushHairStrandControlPointCommand').alloc());
            invokeManaged(command,'.ctor',[cp.path.handle,boxArgument('int',index),value.handle]);
            invokeManaged(s.m.context,'ExecuteSyncCommand',[command.handle]);
        },
        clone(s,category,scope){
            const g=group(s,category,scope);
            if(g.type!=='brush')throw Error('NOT_A_BRUSH_HAIR_GROUP');
            const command=pin(s,cls('VRoidCore','VRoidCore.Editing.History.Command.CloneBrushHairGroupCommand').alloc());
            invokeManaged(command,'.ctor',[g.path.handle]);
            invokeManaged(s.m.context,'ExecuteSyncCommand',[command.handle]);
        },
    };
};
globalThis.createHairGroupApi = ({adapter}) => {
    const categories=['HairFront','HairBack','AllHair','HairTied','HairSideburns','HairAhoge','HairHanege'];
    const metadata={coordinate_space:'native_control_point',units:'native_control_point_coordinates',
        rendered_strand_length:null,geometry_measurement:'mean control-point polyline length; guide transform not applied'};
    const finite = x => typeof x==='number' && Number.isFinite(x);
    function validate(args, scoped=false) {
        if(typeof args.expected_model!=='string'||!args.expected_model)throw Error('EXPECTED_MODEL_REQUIRED');
        if((scoped||args.category!=null)&&!categories.includes(args.category))throw Error('HAIR_PART_CATEGORY_REQUIRED');
        if(scoped&&(typeof args.scope!=='string'||!args.scope))throw Error('HAIR_GROUP_SCOPE_REQUIRED');
    }
    function snapshot(session,args,scope=args.scope) {
        adapter.identity(session);
        const group=adapter.snapshot(session,args.category,scope);
        if(!group)throw Error('UNKNOWN_HAIR_GROUP');
        if(group.strands.length>256)throw Error('HAIR_BATCH_LIMIT');
        let count=0;
        for(const s of group.strands){
            if(s.points.length>512)throw Error('UNEXPECTED_CONTROL_POINT_COUNT');
            count+=s.points.length;
            if(count>4096)throw Error('HAIR_BATCH_LIMIT');
            for(const cp of s.points){
                for(const [key,n] of [['point',3],['normal',3],['uv',2]])
                    if(!Array.isArray(cp[key])||cp[key].length!==n||!cp[key].every(finite))throw Error('INVALID_NATIVE_CONTROL_POINT');
            }
        }
        return group;
    }
    function stats(group){
        const lengths=group.strands.map(s=>s.points.slice(1).reduce((sum,p,i)=>
            sum+Math.hypot(...p.point.map((v,k)=>v-s.points[i].point[k])),0));
        return {...group,strands:group.strands.map((s,i)=>({id:s.id,type:s.type,control_point_count:s.points.length,
            control_point_polyline_length:lengths[i]})),strand_count:group.strands.length,
            control_point_polyline_length:lengths.length?lengths.reduce((a,b)=>a+b,0)/lengths.length:0,...metadata};
    }
    function run(args,work){
        const session=adapter.begin(args);
        try{return work(session);}finally{adapter.end(session);}
    }
    function brush(group){
        if(group.type!=='brush')throw Error('NOT_A_BRUSH_HAIR_GROUP');
        if(group.strands.some(s=>s.type!=='brush'))throw Error('NONBRUSH_GROUP_CHILD');
    }
    const comparable=group=>JSON.stringify({material:group.material,guide:group.guide,
        strands:group.strands.map(s=>({id:s.id,material:s.material,points:s.points.map(p=>({normal:p.normal,uv:p.uv}))}))});
    function proceduralChanges(args){
        validate(args,true);
        const changes=['length','hair_count'].filter(k=>args[k]!=null).map(key=>({key,value:args[key]}));
        if(!changes.length)throw Error('PROCEDURAL_CHANGES_REQUIRED');
        for(const {key,value} of changes)if(!finite(value)||(key==='hair_count'&&(!Number.isInteger(value)||value<=0)))
            throw Error('INVALID_PROCEDURAL_'+key.toUpperCase());
        return changes;
    }
    function setProcedural(args){
        const changes=proceduralChanges(args);
        return run(args,s=>{
            const native=adapter.procedural(s,args.category,args.scope);
            for(const change of changes){
                const control=native.controls.find(c=>c.key===change.key);
                if(!control||change.value<control.min||change.value>control.max)throw Error('PROCEDURAL_NATIVE_RANGE');
            }
            const result={model_token:s.token,frame:s.frame,ok:false,partial:false,uncertain:false,
                setter_count:0,attempted_setters:0,command_count:null,attempted_commands:null,history_entry_count:null,
                history_evidence:'native VM setter route; history delta and merged undo entries not observed',
                before:native.configured,applied:[],
                procedural_length_units:'native_procedural_parameter',...metadata,
                controls:native.controls.map(({write,...c})=>c)};
            try{
                for(const {key,value} of changes){
                    const control=native.controls.find(c=>c.key===key);
                    const requested=key==='length'?Math.fround(value):value;
                    if(native.configured[key]===requested)continue;
                    adapter.identity(s);result.attempted_setters++;
                    control.write(value);result.setter_count++;
                    const current=adapter.procedural(s,args.category,args.scope).configured;
                    if(current[key]!==requested)throw Error('PROCEDURAL_SCALAR_READBACK_MISMATCH');
                    result.applied.push({key,before:native.configured[key],after:current[key]});
                }
                const after=snapshot(s,args);
                for(const {key,value} of changes)if(after.configured[key]!== (key==='length'?Math.fround(value):value))
                    throw Error('PROCEDURAL_SCALAR_READBACK_MISMATCH');
                result.configured=after.configured;result.readback=stats(after);result.verification_snapshot=after;result.ok=true;
            }catch(error){result.error=String(error);result.uncertain=result.attempted_setters>0;result.partial=result.setter_count>0;}
            return result;
        });
    }
    function transform(args,kind){
        validate(args,true);
        if(kind==='scale'&&(!finite(args.factor)||args.factor<=0||args.factor>10))throw Error('INVALID_FACTOR: finite (0,10] required');
        if(kind==='clone'&&(!Array.isArray(args.offset)||args.offset.length!==3||!args.offset.every(finite)))throw Error('INVALID_OFFSET');
        return run(args,session=>{
            const before=snapshot(session,args);brush(before);
            // Precompute the complete plan before the first history command.
            const planned=before.strands.flatMap(s=>s.points.map((cp,index)=>{
                const point=cp.point.map((v,k)=>kind==='scale'
                    ?s.points[0].point[k]+(v-s.points[0].point[k])*args.factor:v+args.offset[k]);
                if(!point.every(x=>finite(x)&&Number.isFinite(Math.fround(x))))throw Error('NONFINITE_TRANSFORM_RESULT');
                return {strand:s.id,index,point:{...cp,point}};
            }).filter(p=>kind!=='scale'||p.index>0));
            const result={model_token:session.token,frame:session.frame,source_scope:args.scope,...metadata,
                ok:false,partial:false,uncertain:false,command_count:0,attempted_commands:0,
                history_entry_count:null,history_evidence:'completed explicit ExecuteSyncCommand calls; merged undo entry count not observed',
                affected_points:0,affected_strands:0,completed_points:[]};
            let target=before, plan=planned;
            try{
                if(kind==='clone'){
                    const ids=new Set(adapter.list(session,args.category).map(g=>g.scope));
                    adapter.identity(session);result.attempted_commands++;
                    adapter.clone(session,args.category,args.scope);result.command_count++;
                    adapter.identity(session);
                    const added=adapter.list(session,args.category).filter(g=>!ids.has(g.scope));
                    result.added_group_ids=added.map(g=>g.scope);
                    if(added.length!==1)throw Error('CLONE_IDENTITY_UNCONFIRMED: expected exactly one new brush group');
                    result.new_scope=added[0].scope;
                    target=snapshot(session,args,result.new_scope);brush(target);
                    result.new_strand_ids=target.strands.map(s=>s.id);
                    result.cloned_strand_count=target.strands.length;
                    result.cloned_point_count=target.strands.reduce((n,s)=>n+s.points.length,0);
                    const sourceShape=JSON.stringify(before.strands.map(s=>({material:s.material,points:s.points})));
                    const clonedShape=JSON.stringify(target.strands.map(s=>({material:s.material,points:s.points})));
                    if(JSON.stringify(before.material)!==JSON.stringify(target.material)||JSON.stringify(before.guide)!==JSON.stringify(target.guide)||sourceShape!==clonedShape)
                        throw Error('CLONE_COPY_UNCONFIRMED');
                    plan=target.strands.flatMap(s=>s.points.map((cp,index)=>({strand:s.id,index,
                        point:{...cp,point:cp.point.map((v,k)=>v+args.offset[k])}})));
                    if(args.offset.every(x=>x===0))plan=[];
                }
                for(const p of plan){
                    adapter.identity(session);result.attempted_commands++;
                    adapter.move(session,target.scope,p.strand,p.index,p.point);result.command_count++;
                    result.completed_points.push({strand_id:p.strand,index:p.index});
                    result.affected_points++;
                }
                adapter.identity(session);
                const after=snapshot(session,args,target.scope);
                if(comparable(target)!==comparable(after))throw Error('HAIR_PRESERVATION_READBACK_MISMATCH');
                for(const p of plan){
                    const actual=after.strands.find(s=>s.id===p.strand)?.points[p.index]?.point;
                    if(!actual||actual.some((v,k)=>Math.abs(v-p.point.point[k])>1e-5*Math.max(1,Math.abs(v))))
                        throw Error('HAIR_POINT_READBACK_MISMATCH');
                }
                // Roots and skipped short/empty strands must remain unchanged.
                if(kind==='scale')for(const s of target.strands){
                    const root=after.strands.find(t=>t.id===s.id)?.points[0]?.point;
                    if(JSON.stringify(root)!==JSON.stringify(s.points[0]?.point))throw Error('HAIR_ROOT_READBACK_MISMATCH');
                }
                result.ok=true;result.readback=stats(after);result.verification_snapshot=after;
            }catch(error){
                result.error=String(error);result.uncertain=result.attempted_commands>0;
                result.partial=result.command_count>0;
            }
            result.affected_strands=new Set(result.completed_points.map(p=>p.strand_id)).size;
            return result;
        });
    }
    return {operations:{
        get_procedural_hair_controls(args){validate(args,true);return run(args,s=>{
            const native=adapter.procedural(s,args.category,args.scope);
            return {model_token:s.token,configured:native.configured,controls:native.controls.map(({write,...c})=>c)};
        });},
        set_procedural_hair:setProcedural,
        get_hair_group_state(args){validate(args,true);return run(args,session=>{
            const group=snapshot(session,args);return {model_token:session.token,group,stats:stats(group)};
        });},
        list_hair_groups(args){validate(args);return run(args,session=>{
            const groups=adapter.list(session,args.category).map(g=>stats(snapshot(session,{...args,category:g.category},g.scope)));
            adapter.identity(session);return {model_token:session.token,groups,...metadata};
        });},
        scale_brush_hair:args=>transform(args,'scale'),
        clone_brush_hair:args=>transform(args,'clone'),
    }};
};
