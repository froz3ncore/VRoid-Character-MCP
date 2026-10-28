// Native Dress-up operations. No desktop input or fabricated success states.
function createWearApi({main,cls,core,text,invokeManaged,rememberTask,captureQuality,captureFraming}) {
    const session=Date.now().toString(36)+Math.random().toString(36).slice(2);
    let generation=0,address='',previewOverride=null,vrmExportSession=null,legPose=null;const imports=new Map();
    function boolArg(value){const p=Memory.alloc(1);p.writeU8(value?1:0);return p;}
    function sequence(o){
        if(!o||o.handle.isNull())return [];
        if(o instanceof Il2Cpp.Array)return [...o];
        if(o.tryMethod('get_Count')&&o.tryMethod('get_Item'))return Array.from({length:o.method('get_Count').invoke()},(_,i)=>o.method('get_Item').invoke(i));
        const iterator=o.method('GetEnumerator').invoke(),result=[];
        try{while(iterator.method('MoveNext').invoke())result.push(iterator.method('get_Current').invoke());}
        finally{if(iterator.tryMethod('Dispose'))iterator.method('Dispose').invoke();}return result;
    }
    function editor(required=true){
        const p=state.refs['VRoid.Studio.XWear.Edit.ViewModel'];
        const nav=main().method('get_GlobalBus').invoke().method('get_ScreenNavigation').invoke();
        const screen=nav.method('get_ActiveScreen').invoke();
        const active=screen.class.type.name==='VRoid.Studio.XWear.Edit.ViewModel';
        if(required&&(!p||!active))throw Error('DRESS_UP_NOT_ACTIVE');
        const key=active?p:'';
        if(address!==key){address=key;generation++;}
        return {vm:active?new Il2Cpp.Object(ptr(p)):null,screen:screen.class.type.name,token:session+':wear:'+generation};
    }
    function expect(args,required=true){
        const e=editor(required);
        if(!args.expected_wear||args.expected_wear!==e.token)throw Error('STALE_WEAR: call get_wear_status');
        return e;
    }
    function status(){
        const e=editor(false);
        const items=e.vm?[...e.vm.method('get_DressItems').invoke()].map(o=>{
            const f=o.field('_autoFittingProperty').value;
            return {id:o.handle.toString(),name:text(o.method('get_Name').invoke()),visible:o.method('get_Visibility').invoke(),
                parts:[...o.method('get_DressParts').invoke()].map(p=>text(p.method('get_Name').invoke())),
                fit_y:f.method('get_FitY').invoke(),fit_z:f.method('get_FitZ').invoke()};}):[];
        const preview=e.vm?e.vm.method('get_Preview').invoke():null,director=preview?preview.field('_currentDirector').value:null;
        const playing=preview?preview.method('get_IsPreview').invoke():false;
        const animator=preview?preview.field('_baseModelAnimator').value:null;
        const ready=!!director&&!director.handle.isNull()&&!!animator&&!animator.handle.isNull();
        const hasTime=ready&&director.class.methods.some(m=>m.name==='get_time');
        const savePath=e.vm?text(e.vm.field('EditContext').value.method('GetCurrentXRoidPath').invoke()):null;
        return {active:!!e.vm,screen:e.screen,wear_token:e.token,items,animation_playing:playing,save_path:savePath,
            selected_preview_clip:previewOverride?{id:previewOverride.id,name:previewOverride.name}:null,
            animation_ready:playing&&ready,animation_time:hasTime?director.method('get_time').invoke():null,frame:state.frame};
    }
    function describe(o){return {type:o.class.type.name,fields:o.class.fields.filter(f=>!f.isStatic).map(f=>({name:f.name,type:f.type.name})),methods:o.class.methods.map(m=>({name:m.name,returns:m.returnType.name,args:m.parameters.map(p=>p.type.name)}))};}
    function xyz(v){return ['x','y','z'].map(k=>v.field(k).value);}
    function matrixRows(value){return Array.from({length:4},(_,r)=>Array.from({length:4},(_,c)=>value.field('m'+r+c).value));}
    function nativeClips(){
        const finder=core('Resources').methods.find(m=>m.isStatic&&m.name==='FindObjectsOfTypeAll'&&m.parameters.length===1&&m.parameters[0].type.name==='System.Type');
        if(!finder)throw Error('NATIVE_CLIP_ENUMERATION_UNAVAILABLE');
        // This exact player build strips AnimationClip.humanMotion. Limit selection
        // to identified native body motions and the built-in sitting pose instead
        // of exposing loaded UI animation clips as avatar animations.
        const names=new Set(['Hub_Idle02','WAIT00','WALK00_F','RUN00_F','JUMP00B','shot_sitting']);
        return [...finder.invoke(cls('UnityEngine.AnimationModule','UnityEngine.AnimationClip').type.object)].filter(c=>names.has(text(c.method('get_name').invoke())));
    }
    function restorePreviewClip(){
        restoreLegPose();
        if(!previewOverride)return;
        const previous=previewOverride;
        previous.slot.field('m_Asset').value=previous.original;
        if(!previous.slot.field('m_Asset').value.handle.equals(previous.original.handle))throw Error('PREVIEW_CLIP_RESTORE_FAILED');
        previewOverride=null;previous.holds.forEach(h=>h.free());core('Object').method('DestroyImmediate',1).invoke(previous.clone);
    }
    function selectPreviewClip(args){
        const e=expect(args),preview=e.vm.method('get_Preview').invoke();
        if(preview.method('get_IsPreview').invoke())throw Error('STOP_WEAR_ANIMATION_FIRST');
        if(args.clip_id===null){restorePreviewClip();return status();}
        const selected=nativeClips().find(c=>c.handle.toString()===args.clip_id);
        if(!selected)throw Error('UNKNOWN_WEAR_PREVIEW_CLIP: list clips again');
        if(previewOverride?.id===args.clip_id)return status();
        const timeline=preview.field('_previewTimeline').value;
        if(timeline.handle.isNull())throw Error('PREVIEW_TIMELINE_NOT_READY: start then stop preview once');
        const slots=[];
        for(let i=0;i<timeline.method('get_outputTrackCount').invoke();i++)
            for(const slot of sequence(timeline.method('GetOutputTrack').invoke(i).method('GetClips').invoke()))
                if(slot.method('get_asset').invoke().class.type.name==='UnityEngine.Timeline.AnimationPlayableAsset')slots.push(slot);
        const slot=slots[0];
        if(!slot||!slot.tryField('m_Asset'))throw Error('NATIVE_PREVIEW_OVERRIDE_UNSUPPORTED');
        restorePreviewClip();const original=slot.field('m_Asset').value;
        const clone=core('Object').method('Instantiate',1).overload('UnityEngine.Object').invoke(original);
        const holds=[retain(slot),retain(original),retain(clone),retain(selected)];
        try{
            invokeManaged(clone,'set_clip',[selected.handle]);
            if(!clone.method('get_clip').invoke().handle.equals(selected.handle))throw Error('PREVIEW_CLIP_READBACK_FAILED');
            slot.field('m_Asset').value=clone;
            if(!slot.field('m_Asset').value.handle.equals(clone.handle))throw Error('PREVIEW_SLOT_READBACK_FAILED');
            previewOverride={slot,original,clone,holds,id:args.clip_id,name:text(selected.method('get_name').invoke())};
        }catch(error){slot.field('m_Asset').value=original;holds.forEach(h=>h.free());core('Object').method('DestroyImmediate',1).invoke(clone);throw error;}
        return status();
    }
    function freezePreviewPose(args){
        const e=expect(args),preview=e.vm.method('get_Preview').invoke();
        if(!preview.method('get_IsPreview').invoke()||!previewOverride||previewOverride.id!==args.clip_id)throw Error('PLAY_SELECTED_PREVIEW_CLIP_FIRST');
        const clip=previewOverride.clone.method('get_clip').invoke(),duration=clip.method('get_length').invoke(),seconds=args.seconds;
        if(typeof seconds!=='number'||!Number.isFinite(seconds)||seconds<0||seconds>duration)throw Error('PREVIEW_TIME_OUTSIDE_CLIP');
        const director=preview.field('_currentDirector').value,slot=previewOverride.slot;
        // Unity 6000.0.62f1 strips these managed wrappers but can retain the
        // registered engine bindings. Resolve all signatures before mutating.
        const binding=(name,returns)=>{
            const address=Il2Cpp.exports.resolveInternalCall(Memory.allocUtf8String('UnityEngine.Playables.PlayableDirector::'+name+'_Injected(System.IntPtr)'));
            if(address.isNull())throw Error('PREVIEW_ENGINE_BINDING_UNAVAILABLE: '+name);
            return new NativeFunction(address,returns,['pointer']);
        };
        const pause=binding('Pause','void'),evaluate=binding('Evaluate','void'),getTime=binding('get_time','double'),getState=binding('GetPlayState','int');
        const cached=core('Object').field('m_CachedPtr'),self=director.handle.add(cached.offset).readPointer();
        if(self.isNull()||!director.tryMethod('set_time'))throw Error('PREVIEW_DIRECTOR_NOT_READY');
        restoreLegPose();
        const target=slot.method('get_start').invoke()+seconds;
        pause(self);director.method('set_time').invoke(target);evaluate(self);
        const actual=getTime(self),paused=getState(self)===0;
        if(Math.abs(actual-target)>1e-5||!paused||!preview.method('get_IsPreview').invoke())throw Error('PREVIEW_HOLD_READBACK_FAILED');
        return {wear_token:e.token,clip_id:args.clip_id,clip_name:text(clip.method('get_name').invoke()),seconds,
            clip_time:actual-slot.method('get_start').invoke(),timeline_time:actual,director_paused:paused,pose_held:true,frame:state.frame,
            scope:'Native director paused and evaluated at requested time; native spring simulation can continue. Stop and restore default before saving.'};
    }
    function quaternionValues(q){return ['x','y','z','w'].map(k=>q.field(k).value);}
    function setQuaternion(t,name,values){
        const q=core('Quaternion').alloc().unbox();q.method('.ctor',4).invoke(...values);t.method(name).invoke(q);
    }
    function yawQuaternion(values,degrees){
        const a=degrees*Math.PI/360,s=Math.sin(a),c=Math.cos(a),[x,y,z,w]=values;
        return [c*x+s*z,c*y+s*w,c*z-s*x,c*w-s*y];
    }
    function restoreLegPose(){
        if(!legPose)return;
        const old=legPose;legPose=null;
        try{for(const b of old.bones)setQuaternion(b.transform,'set_localRotation',b.local_rotation);}
        finally{old.holds.forEach(h=>h.free());}
    }
    function posePreviewLegs(args){
        for(const [key,max] of [['upper_leg_inward_degrees',6],['foot_inward_degrees',12]])
            if(typeof args[key]!=='number'||!Number.isFinite(args[key])||args[key]<0||args[key]>max)throw Error('LEG_POSE_RANGE');
        if(args.upper_leg_inward_degrees>args.foot_inward_degrees)throw Error('LEG_TWIST_EXCEEDS_FOOT_YAW');
        const held=freezePreviewPose(args),e=expect(args),{root,renderers}=previewRenderers(e),found=new Map();
        for(const r of renderers)for(const b of r.method('get_bones').invoke()){
            const name=text(b.method('get_name').invoke());
            if(/^J_Bip_[LR]_(UpperLeg|LowerLeg|Foot|ToeBase)$/.test(name))found.set(b.handle.toString(),b);
        }
        const bones=[...found.values()].map(t=>({transform:t,name:text(t.method('get_name').invoke()),
            local_rotation:quaternionValues(t.method('get_localRotation').invoke()),
            world_rotation:quaternionValues(t.method('get_rotation').invoke()),position:xyz(t.method('get_position').invoke())}));
        for(const side of ['L','R'])for(const part of ['UpperLeg','LowerLeg','Foot','ToeBase'])
            if(bones.filter(b=>b.name===`J_Bip_${side}_${part}`).length!==1)throw Error('UNIQUE_PREVIEW_LEG_RIG_REQUIRED');
        legPose={bones:bones.filter(b=>/_(UpperLeg|Foot)$/.test(b.name)),holds:bones.map(b=>retain(b.transform))};
        try{
            for(const part of ['UpperLeg','Foot'])for(const b of bones.filter(b=>b.name.endsWith('_'+part))){
                const degrees=(b.name.includes('_L_')?1:-1)*(part==='UpperLeg'?args.upper_leg_inward_degrees:args.foot_inward_degrees);
                const target=yawQuaternion(b.world_rotation,degrees);
                setQuaternion(b.transform,'set_rotation',target);
                const actual=quaternionValues(b.transform.method('get_rotation').invoke());
                const error=Math.min(Math.max(...actual.map((v,i)=>Math.abs(v-target[i]))),Math.max(...actual.map((v,i)=>Math.abs(v+target[i]))));
                if(error>2e-5)throw Error('PREVIEW_LEG_ROTATION_READBACK_FAILED');
            }
            return {...held,preview_root:root.handle.toString(),upper_leg_inward_degrees:args.upper_leg_inward_degrees,foot_inward_degrees:args.foot_inward_degrees,
                session_only:true,animation_asset_exported:false,bones:bones.map(b=>({name:b.name,before_position:b.position,before_world_rotation:b.world_rotation,
                    after_position:xyz(b.transform.method('get_position').invoke()),after_world_rotation:quaternionValues(b.transform.method('get_rotation').invoke())})),
                scope:'Frozen native preview plus world-Y leg/foot yaw; reapply per sampled pose, not continuous animation or saved XRoid pose. Source edit rig untouched.'};
        }catch(error){restoreLegPose();throw error;}
    }
    function bodyOcclusionContext(args,allowPreviewRead=false,nativeShoes=false){
        const e=expect(args);
        if(!allowPreviewRead&&e.vm.method('get_Preview').invoke().method('get_IsPreview').invoke())throw Error('STOP_WEAR_ANIMATION_FIRST');
        const base=e.vm.method('get_CurrentBaseModel').invoke();
        const matches=[...base.method('get_SubContents').invoke()].filter(s=>text(s.field('_renderer').value.method('get_name').invoke())===(nativeShoes?'Cloth':'Body'));
        if(nativeShoes&&matches.length!==1)throw Error('UNIQUE_NATIVE_SHOE_RENDERER_REQUIRED');
        const sub=matches[0];
        if(!sub)throw Error('BASE_BODY_EDITOR_MISSING');
        if(nativeShoes){
            const materials=[...sub.field('_renderer').value.method('get_sharedMaterials').invoke()];
            if(!materials.length||materials.some(m=>m.handle.isNull()||!/_Shoes_\d+_CLOTH$/.test(text(m.method('get_name').invoke()))))throw Error('NATIVE_SHOE_ONLY_RENDERER_REQUIRED');
        }
        const view=sub.method('get_DrawableMeshViewModel').invoke(),drawable=view.field('_drawableMesh').value;
        const marker=drawable.field('_meshAliveMarker').value;
        if(marker.handle.isNull())throw Error('BASE_BODY_MARKER_NOT_READY');
        const renderer=sub.field('_renderer').value,original=drawable.method('get_DefaultMesh').invoke();
        const current=renderer.method('get_sharedMesh').invoke(),marks=[...marker.method('get_CurrentVertexActiveMark').invoke()];
        const hidden=marks.flatMap((v,i)=>v?[]:[i]),count=original.method('get_vertexCount').invoke();
        if(marks.length!==count)throw Error('BODY_MARK_COUNT_MISMATCH');
        return {e,drawable,marker,renderer,original,current,marks,hidden,count};
    }
    function nativeShoeVisibilitySnapshot(args){
        const c=bodyOcclusionContext(args,false,true);
        return {wear_token:c.e.token,frame:state.frame,renderer_name:'Cloth',renderer_id:c.renderer.handle.toString(),
            material_names:[...c.renderer.method('get_sharedMaterials').invoke()].map(m=>text(m.method('get_name').invoke())),
            default_mesh_id:c.original.handle.toString(),default_vertex_count:c.count,current_vertex_count:c.current.method('get_vertexCount').invoke(),
            current_triangle_count:c.current.method('get_triangles').invoke().length/3,
            source_positions:[...c.original.method('get_vertices').invoke()].map(xyz),source_triangles:[...c.original.method('get_triangles').invoke()],hidden_vertices:c.hidden};
    }
    function setNativeShoeVisibility(args){
        const c=bodyOcclusionContext(args,false,true),ids=args.hidden_vertices;
        if(args.renderer_id!==c.renderer.handle.toString()||args.default_mesh_id!==c.original.handle.toString())throw Error('STALE_NATIVE_SHOE_MESH');
        if(JSON.stringify(args.expected_hidden_vertices)!==JSON.stringify(c.hidden))throw Error('NATIVE_SHOE_MASK_CHANGED');
        if(!Array.isArray(ids)||!([0,c.count].includes(ids.length))||ids.some((v,i)=>v!==i))throw Error('FULL_SHOE_VISIBILITY_ONLY');
        const hidden=new Set(ids),marks=Il2Cpp.array(Il2Cpp.corlib.class('System.Boolean'),c.count),indices=Il2Cpp.array(Il2Cpp.corlib.class('System.Int32'),ids.length);
        for(let i=0;i<c.count;i++)marks.set(i,!hidden.has(i));ids.forEach((v,i)=>indices.set(i,v));
        try{
            c.drawable.method('HandleBeginDrag').invoke();invokeManaged(c.marker,'UpdateMesh',[marks.handle,indices.handle,boolArg(true)]);c.drawable.method('HandleEndDrag').invoke();
            const actual=[...c.marker.method('get_CurrentVertexActiveMark').invoke()].flatMap((v,i)=>v?[]:[i]);
            if(JSON.stringify(actual)!==JSON.stringify(ids))throw Error('readback mismatch');
            return {wear_token:c.e.token,hidden_vertices:actual,visible:actual.length===0,native_history_used:true,changed:JSON.stringify(actual)!==JSON.stringify(c.hidden),
                current_vertex_count:c.renderer.method('get_sharedMesh').invoke().method('get_vertexCount').invoke(),current_triangle_count:c.renderer.method('get_sharedMesh').invoke().method('get_triangles').invoke().length/3};
        }catch(error){throw Error('NATIVE_SHOE_MUTATION_UNCERTAIN: '+error);}
    }
    function nativeShoeSurfaceReference(args,e,preview){
        const base=e.vm.method('get_CurrentBaseModel').invoke();
        const candidates=[...base.method('get_SubContents').invoke()].filter(s=>text(s.field('_renderer').value.method('get_name').invoke())==='Cloth');
        if(candidates.length!==1)return null;
        const materials=[...candidates[0].field('_renderer').value.method('get_sharedMaterials').invoke()];
        if(!materials.length||materials.some(m=>m.handle.isNull()||!/_Shoes_\d+_CLOTH$/.test(text(m.method('get_name').invoke()))))return null;
        const c=bodyOcclusionContext(args,true,true),renderers=preview?previewRenderers(e).renderers:[c.renderer],surfaces=[];
        for(const r of renderers){
            const mesh=r.method('get_sharedMesh').invoke();if(mesh.handle.isNull())continue;
            const name=text(r.method('get_name').invoke());
            if(/^Cloth(?:\s*\((?:Clone|Instance)\))?$/.test(name)){
                surfaces.push({renderer:name,material:'native shoe-only Cloth',triangles:mesh.method('get_triangles').invoke().length/3});continue;
            }
            const mats=[...r.method('get_sharedMaterials').invoke()];
            for(let i=0;i<Math.min(mats.length,mesh.method('get_subMeshCount').invoke());i++){
                if(mats[i].handle.isNull()||!/_Shoes_\d+_CLOTH(?:\s*\((?:Clone|Instance)\))?$/.test(text(mats[i].method('get_name').invoke())))continue;
                surfaces.push({renderer:text(r.method('get_name').invoke()),material:text(mats[i].method('get_name').invoke()),triangles:mesh.method('GetTriangles',1).overload('System.Int32').invoke(i).length/3});
            }
        }
        return {edit_hidden:c.hidden.length===c.count,preview,triangle_count:surfaces.reduce((n,s)=>n+s.triangles,0),surfaces};
    }
    function bodyOcclusionSnapshot(args){
        const c=bodyOcclusionContext(args);
        return {wear_token:c.e.token,frame:state.frame,renderer_name:'Body',renderer_id:c.renderer.handle.toString(),
            default_mesh_id:c.original.handle.toString(),current_mesh_id:c.current.handle.toString(),
            default_vertex_count:c.count,current_vertex_count:c.current.method('get_vertexCount').invoke(),
            current_triangle_count:c.current.method('get_triangles').invoke().length/3,
            source_positions:[...c.original.method('get_vertices').invoke()].map(xyz),
            source_triangles:[...c.original.method('get_triangles').invoke()],hidden_vertices:c.hidden,
            scope:'Native default Body vertex indices and active marks. Source positions are bind geometry, not a posed fitting reference.'};
    }
    function setBodyOcclusion(args){
        const c=bodyOcclusionContext(args),ids=args.hidden_vertices;
        if(args.renderer_id!==c.renderer.handle.toString()||args.default_mesh_id!==c.original.handle.toString())throw Error('STALE_BODY_MESH');
        if(JSON.stringify(args.expected_hidden_vertices)!==JSON.stringify(c.hidden))throw Error('BODY_MASK_CHANGED');
        if(!Array.isArray(ids)||ids.length>Math.min(2048,Math.floor(c.count*.2))||ids.some((v,i)=>!Number.isInteger(v)||v<0||v>=c.count||(i&&v<=ids[i-1])))throw Error('INVALID_BODY_OCCLUSION_INDICES');
        const hidden=new Set(ids),marks=Il2Cpp.array(Il2Cpp.corlib.class('System.Boolean'),c.count),indices=Il2Cpp.array(Il2Cpp.corlib.class('System.Int32'),ids.length);
        for(let i=0;i<c.count;i++)marks.set(i,!hidden.has(i));ids.forEach((v,i)=>indices.set(i,v));
        try{
            c.drawable.method('HandleBeginDrag').invoke();
            invokeManaged(c.marker,'UpdateMesh',[marks.handle,indices.handle,boolArg(true)]);
            c.drawable.method('HandleEndDrag').invoke();
        }catch(error){throw Error('BODY_MASK_MUTATION_UNCERTAIN: '+error);}
        const actual=[...c.marker.method('get_CurrentVertexActiveMark').invoke()].flatMap((v,i)=>v?[]:[i]);
        if(JSON.stringify(actual)!==JSON.stringify(ids))throw Error('BODY_MASK_MUTATION_UNCERTAIN: readback mismatch');
        return {changed:JSON.stringify(ids)!==JSON.stringify(c.hidden),wear_token:c.e.token,hidden_vertices:actual,
            previous_hidden_vertices:c.hidden,default_vertex_count:c.count,
            current_vertex_count:c.renderer.method('get_sharedMesh').invoke().method('get_vertexCount').invoke(),
            native_history_used:true,scope:'Native Body mesh active marks; save/reopen and VRM persistence require separate verification.'};
    }
    function wearReference(args){
        const e=expect(args);
        const moving=e.vm.method('get_Preview').invoke().method('get_IsPreview').invoke(),preview=args.preview===true;
        if(preview&&!moving)throw Error('START_WEAR_ANIMATION_FOR_PREVIEW_REFERENCE');
        if(!preview&&moving)throw Error('STOP_WEAR_ANIMATION_FIRST');
        const item=[...e.vm.method('get_DressItems').invoke()].find(i=>i.handle.toString()===args.item_id);
        if(!item)throw Error('UNKNOWN_WEAR_ITEM');
        const all=[...item.method('get_DressItem').invoke().method('get_EditInstances').invoke()].flatMap(i=>[...i.method('get_Renderers').invoke()]);
        const names=new Set(all.map(r=>text(r.method('get_name').invoke())));
        const previewMeshes=preview?previewRenderers(e).renderers:null;
        const candidates=preview?previewMeshes.filter(r=>names.has(text(r.method('get_name').invoke()))):all;
        const requested=args.mesh_names,selected=requested?candidates.filter(r=>requested.includes(text(r.method('get_name').invoke()))):candidates;
        if(requested&&selected.length!==requested.length)throw Error('UNKNOWN_OR_AMBIGUOUS_WEAR_MESH');
        if(!selected.length||selected.length>128)throw Error('WEAR_REFERENCE_MESH_LIMIT');
        const boneIds=new Map(),bones=[];let total=0;
        function captureMesh(renderer,skin){
            if(renderer.class.type.name!=='UnityEngine.SkinnedMeshRenderer')throw Error('WEAR_REFERENCE_REQUIRES_SKINNED_MESH');
            const source=renderer.method('get_sharedMesh').invoke(),count=source.method('get_vertexCount').invoke();
            total+=count;if(total>300000)throw Error('WEAR_REFERENCE_VERTEX_LIMIT');
            let baked=null;
            try{
                baked=core('Mesh').alloc();baked.method('.ctor').invoke();renderer.method('BakeMesh',1).invoke(baked);
                const data={name:text(renderer.method('get_name').invoke()),renderer_id:renderer.handle.toString(),mesh_id:source.handle.toString(),world_matrix:matrixRows(renderer.method('get_transform').invoke().method('get_localToWorldMatrix').invoke()),
                    positions:[...baked.method('get_vertices').invoke()].map(xyz),normals:[...baked.method('get_normals').invoke()].map(xyz),triangles:[...source.method('get_triangles').invoke()]};
                if(skin){
                    data.source_positions=[...source.method('get_vertices').invoke()].map(xyz);
                    data.uv0=[...source.method('get_uv').invoke()].map(v=>['x','y'].map(k=>v.field(k).value));
                    data.bindposes=[...source.method('get_bindposes').invoke()].map(matrixRows);
                    data.bone_ids=[...renderer.method('get_bones').invoke()].map(b=>{
                        const key=b.handle.toString();
                        if(!boneIds.has(key)){
                            if(bones.length>=32768)throw Error('WEAR_REFERENCE_BONE_LIMIT');
                            const parent=b.method('get_parent').invoke();
                            boneIds.set(key,bones.length);bones.push({id:bones.length,name:text(b.method('get_name').invoke()),parent_name:parent.handle.isNull()?null:text(parent.method('get_name').invoke()),world_matrix:matrixRows(b.method('get_localToWorldMatrix').invoke())});
                        }
                        return boneIds.get(key);
                    });
                    data.weights=[...source.method('get_boneWeights').invoke()].map(v=>{
                        const fields=new Set(v.type.class.fields.map(f=>f.name));
                        const field=k=>v.field(fields.has(k)?k:'m_'+k[0].toUpperCase()+k.slice(1)).value;
                        return {indices:[0,1,2,3].map(i=>field('boneIndex'+i)),weights:[0,1,2,3].map(i=>field('weight'+i))};
                    });
                }
                return data;
            }finally{if(baked)core('Object').method('DestroyImmediate',1).invoke(baked);}
        }
        const base=e.vm.field('EditContext').value.field('EditContents').value.field('CurrentBaseModel').value;
        const baseRenderers=preview?previewMeshes:components(base.method('get_RootGameObject').invoke(),core('SkinnedMeshRenderer'));
        const body=baseRenderers.find(r=>text(r.method('get_name').invoke())==='Body');
        if(!body)throw Error('WEAR_REFERENCE_BODY_RENDERER_NOT_FOUND');
        const bodyMesh=captureMesh(body,false),garments=selected.map(r=>captureMesh(r,true));
        const baseMeshes=args.include_base_meshes===true?(args.base_mesh_names||['Body','Foot','Face','Hair']).flatMap(name=>{
            const matches=baseRenderers.filter(r=>text(r.method('get_name').invoke())===name);
            if(!matches.length&&name!=='Body')return [];
            if(matches.length!==1)throw Error('MISSING_OR_AMBIGUOUS_BASE_REFERENCE: '+name);
            return [captureMesh(matches[0],true)];
        }):[];
        let bodyOcclusion=null;
        if(args.include_base_meshes===true){
            const mask=bodyOcclusionContext(args,true);
            bodyOcclusion={default_vertex_count:mask.count,hidden_vertex_count:mask.hidden.length,
                hidden_original_vertex_indices:mask.hidden,scope:'Captured base geometry is the current visible mesh. Hidden original Body vertices are absent, not evidence of improved geometric enclosure.'};
        }
        return {schema:'vroid-wear-reference-v1',wear_token:e.token,item_id:args.item_id,frame:state.frame,
            coordinate_system:'Unity +Y up, +Z front; row-major matrices; positions are renderer-local BakeMesh results',
            pose_source:preview?'native_preview':'native_edit',selected_preview_clip:preview?status().selected_preview_clip:null,
            body:bodyMesh,garments,base_meshes:baseMeshes,base_body_occlusion:bodyOcclusion,base_native_shoes:nativeShoeSurfaceReference(args,e,preview),
            base_foot_source:baseMeshes.some(m=>m.name==='Foot')?'Foot':baseMeshes.length?'Body (combined; no separate Foot renderer)':null,bones,
            colliders:preview?components(previewRenderers(e).root,cls('VRM10','UniVRM10.VRM10SpringBoneCollider')).map(colliderDescription):[],
            spring_bones:preview?components(previewRenderers(e).root,core('Transform')).filter(t=>text(t.method('get_name').invoke()).startsWith('WM_')).map(t=>({
                id:t.handle.toString(),name:text(t.method('get_name').invoke()),parent_name:text(t.method('get_parent').invoke().method('get_name').invoke()),
                position:xyz(t.method('get_position').invoke()),world_matrix:matrixRows(t.method('get_localToWorldMatrix').invoke())})):[],
            scope:'Single native pose BakeMesh and skin transforms; no body editing, animation asset or VRM export'};
    }
    function jointInfo(b){
        const go=b.method('get_gameObject').invoke(),j=go.method('GetComponent',1).overload('System.Type').invoke(cls('VRM10','UniVRM10.VRM10SpringBoneJoint').type.object);
        return j.handle.isNull()?null:{stiffness:j.field('m_stiffnessForce').value,gravity_power:j.field('m_gravityPower').value,
            gravity_dir:xyz(j.field('m_gravityDir').value),drag:j.field('m_dragForce').value,radius:j.field('m_jointRadius').value};
    }
    function colliderInfo(b){
        const c=b.method('get_gameObject').invoke().method('GetComponent',1).overload('System.Type').invoke(cls('VRM10','UniVRM10.VRM10SpringBoneCollider').type.object);
        return c.handle.isNull()?null:{radius:c.field('Radius').value,offset:xyz(c.field('Offset').value),tail:xyz(c.field('Tail').value)};
    }
    function colliderDescription(c){
        const t=c.method('get_transform').invoke(),p=t.method('get_parent').invoke();
        const matrix=matrixRows(t.method('get_localToWorldMatrix').invoke()),offset=xyz(c.field('Offset').value),tail=xyz(c.field('Tail').value);
        const point=v=>matrix.slice(0,3).map(row=>row[3]+row.slice(0,3).reduce((sum,n,i)=>sum+n*v[i],0));
        return {name:text(c.method('get_name').invoke()),parent:p.handle.isNull()?null:text(p.method('get_name').invoke()),
            radius:c.field('Radius').value,offset,tail,world_matrix:matrix,world_offset:point(offset),world_tail:point(tail),
            type_fields:c.class.fields.filter(f=>!f.isStatic&&/type|shape/i.test(f.name)).map(f=>({name:f.name,type:f.type.name,value:String(c.field(f.name).value)}))};
    }
    function scopeSaveCache(args){
        const e=expect(args),cache=e.vm.field('EditContext').value.field('_xRoidSaver').value.field('CacheDirectory').value;
        const before=text(cache.method('GetDirectoryPath').invoke());
        if(ATTACHED){
            if(!before)throw Error('WEAR_NATIVE_CACHE_UNAVAILABLE');
            return {cache_path:before,isolated:false};
        }
        const after=remapFolder(before),old=cache.field('_directoryName').value;
        if(!within(after))throw Error('WEAR_CACHE_OUTSIDE_LAB');
        if(norm(before)!==norm(after)){
            cache.field('_directoryName').value=Il2Cpp.string(after);
            const actual=text(cache.method('GetDirectoryPath').invoke());
            if(norm(actual)!==norm(after)){
                cache.field('_directoryName').value=old;
                throw Error('WEAR_CACHE_PATH_OVERRIDE_UNSUPPORTED: '+actual);
            }
        }
        return {cache_path:text(cache.method('GetDirectoryPath').invoke()),isolated:true};
    }
    function components(go,type){
        const found=[];let visited=0;
        function walk(t,depth){
            if(++visited>4096||depth>48)throw Error('WEAR_HIERARCHY_LIMIT');
            const component=t.method('get_gameObject').invoke().method('GetComponent',1).overload('System.Type').invoke(type.type.object);
            if(!component.handle.isNull())found.push(component);
            for(let i=0;i<t.method('get_childCount').invoke();i++)walk(t.method('GetChild').invoke(i),depth+1);
        }
        walk(go.method('get_transform').invoke(),0);return found;
    }
    function snapshot(args){
        const e=expect(args),items=[...e.vm.method('get_DressItems').invoke()];
        if(e.vm.method('get_Preview').invoke().method('get_IsPreview').invoke())throw Error('STOP_WEAR_ANIMATION_FIRST');
        const base=e.vm.field('EditContext').value.field('EditContents').value.field('CurrentBaseModel').value;
        const baseRenderers=components(base.method('get_RootGameObject').invoke(),core('SkinnedMeshRenderer')).map(r=>{
            const mesh=r.method('get_sharedMesh').invoke();
            return {name:text(r.method('get_name').invoke()),enabled:r.method('get_enabled').invoke(),
                active:r.method('get_gameObject').invoke().method('get_activeInHierarchy').invoke(),
                vertices:mesh.method('get_vertexCount').invoke(),triangles:mesh.method('get_triangles').invoke().length/3,
                materials:[...r.method('get_sharedMaterials').invoke()].map(m=>m.handle.isNull()?null:text(m.method('get_name').invoke()))};});
        return {...status(),schema:'vroid-wear-snapshot-v1',coordinate_system:'Unity +Y up, +Z front',
          base_model:{name:text(base.method('get_Name').invoke()),renderers:baseRenderers},
          items:items.map(item=>{
            const dress=item.method('get_DressItem').invoke(),instances=[...dress.method('get_EditInstances').invoke()];
            const skeletons=[],skeletonIds=new Map();
            return {id:item.handle.toString(),edit_guid:text(dress.method('get_EditGuid').invoke()),name:text(item.method('get_Name').invoke()),
              skeletons,
              instances:instances.map(instance=>{
                const root=instance.method('get_RootGameObject').invoke();
                const renderers=[...instance.method('get_Renderers').invoke()].map(r=>{
                    const mesh=r.class.type.name==='UnityEngine.SkinnedMeshRenderer'?r.method('get_sharedMesh').invoke():null;
                    const bounds=r.method('get_bounds').invoke();
                    const bones=mesh?[...r.method('get_bones').invoke()]:[],key=bones.map(b=>b.handle.toString()).join(',');
                    if(mesh&&!skeletonIds.has(key)){
                        skeletonIds.set(key,skeletons.length);
                        skeletons.push({bones:bones.map(b=>({name:text(b.method('get_name').invoke()),position:xyz(b.method('get_position').invoke()),spring_joint:jointInfo(b),spring_collider:colliderInfo(b)})),
                          colliders:components(bones[0].method('get_gameObject').invoke(),cls('VRM10','UniVRM10.VRM10SpringBoneCollider')).map(colliderDescription)});
                    }
                    return {name:text(r.method('get_name').invoke()),enabled:r.method('get_enabled').invoke(),
                      active:r.method('get_gameObject').invoke().method('get_activeInHierarchy').invoke(),
                      vertices:mesh?mesh.method('get_vertexCount').invoke():null,
                      triangles:mesh?mesh.method('get_triangles').invoke().length/3:null,
                      skeleton_index:mesh?skeletonIds.get(key):null,bone_count:bones.length,
                      bounds:{center:xyz(bounds.method('get_center').invoke()),extents:xyz(bounds.method('get_extents').invoke())},
                      materials:[...r.method('get_sharedMaterials').invoke()].map(m=>{
                        if(m.handle.isNull())return null;
                        const tex=m.method('get_mainTexture').invoke();
                        return {name:text(m.method('get_name').invoke()),shader:text(m.method('get_shader').invoke().method('get_name').invoke()),
                          main_texture:tex.handle.isNull()?null:{name:text(tex.method('get_name').invoke()),width:tex.method('get_width').invoke(),height:tex.method('get_height').invoke()}};})};});
                const vrm=components(root,cls('VRM10','UniVRM10.Vrm10Instance')).map(v=>{
                    const sb=v.field('SpringBone').value;
                    return {root:text(v.method('get_name').invoke()),
                      springs:[...sb.field('Springs').value].map(s=>({name:text(s.field('Name').value),
                        joints:[...s.field('Joints').value].map(j=>({bone:text(j.method('get_name').invoke()),
                          stiffness:j.field('m_stiffnessForce').value,gravity_power:j.field('m_gravityPower').value,
                          gravity_dir:xyz(j.field('m_gravityDir').value),drag:j.field('m_dragForce').value,radius:j.field('m_jointRadius').value})),
                        collider_groups:[...s.field('ColliderGroups').value].length})),
                      collider_groups:[...sb.field('ColliderGroups').value].map(g=>({name:text(g.field('Name').value),
                        colliders:[...g.field('Colliders').value].map(c=>({bone:text(c.method('get_name').invoke()),radius:c.field('Radius').value,
                          offset:xyz(c.field('Offset').value),tail:xyz(c.field('Tail').value)}))}))};});
                return {root:text(root.method('get_name').invoke()),renderers,vrm_instances:vrm};})};})};
    }
    function previewRenderers(e){
        const p=e.vm.method('get_Preview').invoke(),a=p.field('_baseModelAnimator').value;
        if(!p.method('get_IsPreview').invoke()||!a||a.handle.isNull())throw Error('WEAR_ANIMATION_NOT_READY');
        const root=a.method('get_gameObject').invoke();
        return {root,renderers:components(root,core('SkinnedMeshRenderer'))};
    }
    function motionSample(args){
        const e=expect(args),{root,renderers}=previewRenderers(e),bones=new Map();
        for(const r of renderers)for(const b of r.method('get_bones').invoke()){
            const name=text(b.method('get_name').invoke());
            if(!name.startsWith('WM_')&&!name.startsWith('J_Bip_'))continue;
            const key=b.handle.toString();if(bones.has(key))continue;
            if(bones.size>=32768)throw Error('WEAR_MOTION_BONE_LIMIT');
            const q=b.method('get_localRotation').invoke();
            bones.set(key,{id:key,name,position:xyz(b.method('get_position').invoke()),
                local_rotation:['x','y','z','w'].map(k=>q.field(k).value)});
        }
        return {...capture(args,true),frame:state.frame,preview_root:root.handle.toString(),
            preview_root_name:text(root.method('get_name').invoke()),
            renderers:renderers.map(r=>({id:r.handle.toString(),name:text(r.method('get_name').invoke()),
                vertices:r.method('get_sharedMesh').invoke().method('get_vertexCount').invoke(),
                enabled:r.method('get_enabled').invoke(),active:r.method('get_gameObject').invoke().method('get_activeInHierarchy').invoke()})),
            bones:[...bones.values()]};
    }
    function samplePreviewRig(args){
        const e=expect(args),{root,renderers}=previewRenderers(e),nodes=new Map();
        function add(t){
            if(t.handle.isNull()||nodes.has(t.handle.toString()))return;
            if(nodes.size>=4096)throw Error('PREVIEW_RIG_NODE_LIMIT');
            const parent=t.method('get_parent').invoke();
            nodes.set(t.handle.toString(),{id:t.handle.toString(),name:text(t.method('get_name').invoke()),
                parent_id:parent.handle.isNull()?null:parent.handle.toString(),world_matrix:matrixRows(t.method('get_localToWorldMatrix').invoke()),
                local_position:xyz(t.method('get_localPosition').invoke()),local_rotation:quaternionValues(t.method('get_localRotation').invoke())});
            if(!parent.handle.isNull()&&!t.method('get_gameObject').invoke().handle.equals(root.handle))add(parent);
        }
        for(const r of renderers)for(const b of r.method('get_bones').invoke())add(b);
        return {schema:'vroid-preview-rig-v1',wear_token:e.token,frame:state.frame,preview_root:root.handle.toString(),
            selected_preview_clip:status().selected_preview_clip,animation_time:status().animation_time,nodes:[...nodes.values()],
            renderers:renderers.map(r=>({name:text(r.method('get_name').invoke()),id:r.handle.toString(),bone_ids:[...r.method('get_bones').invoke()].map(b=>b.handle.toString())})),
            model_modified:false,scope:'Actual current preview bone transforms and ancestry only; no image, mesh, animation asset or pose modification.'};
    }
    function captureSources(e,motion=false){
        let renderers;
        if(motion)return previewRenderers(e);
        else{
            const base=e.vm.field('EditContext').value.field('EditContents').value.field('CurrentBaseModel').value;
            const root=base.method('get_RootGameObject').invoke();
            renderers=components(root,core('SkinnedMeshRenderer'));
            for(const item of e.vm.method('get_DressItems').invoke())
                for(const inst of item.method('get_DressItem').invoke().method('get_EditInstances').invoke())renderers.push(...inst.method('get_Renderers').invoke());
            return {root,renderers};
        }
    }
    function framingReference(args){
        const e=expect(args);
        if(e.vm.method('get_Preview').invoke().method('get_IsPreview').invoke())throw Error('STOP_WEAR_ANIMATION_FIRST');
        const {root,renderers}=captureSources(e);
        return {wear_token:e.token,root_id:root.handle.toString(),reference_frame:state.frame,...captureFraming.bounds(renderers)};
    }
    function capture(args,motion=false){
        const e=expect(args),size=args.size,view=args.view;
        if(!Number.isInteger(size)||size<256||size>2048)throw Error('CAPTURE_SIZE_RANGE');
        captureQualityPlan(size,args.quality);
        const parsed=parseCaptureView(view,true);
        if(!motion&&e.vm.method('get_Preview').invoke().method('get_IsPreview').invoke())throw Error('STOP_WEAR_ANIMATION_FIRST');
        const {root,renderers}=captureSources(e,motion);
        let lo=null,hi=null;const boundDetails=[];
        for(const r of renderers){
            // VRoid temporarily hides edit renderers between its own camera passes.
            // Bounds come only from the current base and explicit DressItems, independent of that transient flag.
            const b=r.method('get_bounds').invoke(),c=xyz(b.method('get_center').invoke()),ex=xyz(b.method('get_extents').invoke());
            boundDetails.push({name:text(r.method('get_name').invoke()),center:c,extents:ex,types:c.map(v=>typeof v)});
            if(![...c,...ex].every(v=>Number.isFinite(v)))continue;
            const lower=c.map((v,i)=>v-ex[i]),upper=c.map((v,i)=>v+ex[i]);
            if(lo===null){lo=lower;hi=upper;}
            else for(let i=0;i<3;i++){lo[i]=Math.min(lo[i],lower[i]);hi[i]=Math.max(hi[i],upper[i]);}
        }
        if(motion&&args.fixed_bounds){lo=args.fixed_bounds.min;hi=args.fixed_bounds.max;}
        const ref=args.framing_reference;
        if(parsed.regional&&ref){
            if(ref.wear_token!==e.token||ref.root_id!==root.handle.toString())throw Error('STALE_WEAR_FRAMING_REFERENCE');
            validateFramingBounds(ref.bounds);lo=ref.bounds.min;hi=ref.bounds.max;
        }
        const plan=parsed.regional?{...regionalCameraPlan({min:lo,max:hi},parsed),
            source_root_id:root.handle.toString(),reference_frame:ref?ref.reference_frame:null,
            bounds_locked:!!ref||!!args.fixed_bounds}:null;
        if(!lo||!lo.every(v=>Number.isFinite(v))||hi[1]-lo[1]<.1)throw Error('NO_VISIBLE_WEAR_BOUNDS: '+JSON.stringify({min:lo,max:hi,renderers:boundDetails}));
        const center=lo.map((v,i)=>(v+hi[i])/2),radius=Math.max((hi[1]-lo[1])*.58,(hi[0]-lo[0])*.58,(hi[2]-lo[2])*.58),distance=radius/Math.tan(Math.PI/12);
        const vector=(x,y,z)=>{const v=core('Vector3').alloc().unbox();v.method('.ctor',3).invoke(x,y,z);return v;};
        const rtClass=core('RenderTexture'),oldActive=rtClass.method('get_active').invoke();let go=null,capture=null;
        const excluded=[],layerOverrides=[],lightOverrides=[],boundsOverrides=[];let captureLayer=null;
        try{
            if(motion&&parsed.regional){
                // Synthesized preview clothing can retain bind-pose culling bounds.
                // A wide view still draws it, but a close camera may cull the shoe
                // while its posed foot remains visible. Temporarily use the shared
                // framing box for culling only; never edit vertices or source bounds.
                for(const r of renderers){
                    if(!r.tryMethod('get_localBounds')||!r.tryMethod('set_localBounds'))throw Error('PREVIEW_CULLING_BOUNDS_UNAVAILABLE');
                }
                for(const r of renderers){
                    const old=r.method('get_localBounds').invoke(),oldCenter=xyz(old.method('get_center').invoke()),oldSize=xyz(old.method('get_size').invoke());
                    const transform=r.method('get_transform').invoke();let lower=[Infinity,Infinity,Infinity],upper=[-Infinity,-Infinity,-Infinity];
                    for(let mask=0;mask<8;mask++){
                        const p=xyz(transform.method('InverseTransformPoint',1).invoke(vector(...lo.map((v,i)=>(mask&(1<<i))?hi[i]:v))));
                        for(let i=0;i<3;i++){lower[i]=Math.min(lower[i],p[i]);upper[i]=Math.max(upper[i],p[i]);}
                    }
                    const b=core('Bounds').alloc().unbox();b.method('.ctor',2).invoke(vector(...lower.map((v,i)=>(v+upper[i])/2)),vector(...lower.map((v,i)=>Math.max(upper[i]-v,.001))));
                    boundsOverrides.push({renderer:r,center:oldCenter,size:oldSize});r.method('set_localBounds').invoke(b);
                }
            }
            {
                // A new camera also sees the edit-only assembly. Exclude those
                // duplicate renderers for this synchronous Render, then restore
                // every flag. All preview body and garment renderers remain intact.
                const keep=new Set(renderers.map(r=>r.handle.toString()));
                const base=e.vm.field('EditContext').value.field('EditContents').value.field('CurrentBaseModel').value;
                const edit=components(base.method('get_RootGameObject').invoke(),core('SkinnedMeshRenderer'));
                for(const item of e.vm.method('get_DressItems').invoke())
                    for(const inst of item.method('get_DressItem').invoke().method('get_EditInstances').invoke())edit.push(...inst.method('get_Renderers').invoke());
                for(const r of edit)if(!keep.has(r.handle.toString())){
                    excluded.push({renderer:r,enabled:r.method('get_enabled').invoke()});r.method('set_enabled').invoke(false);
                }
                const used=new Set([...edit,...renderers].map(r=>r.method('get_gameObject').invoke().method('get_layer').invoke()));
                for(let i=31;i>=0;i--)if(!used.has(i)){captureLayer=i;break;}
                if(captureLayer===null)throw Error('NO_TEMPORARY_PREVIEW_LAYER');
                const objects=new Set();
                for(const r of renderers){
                    const object=r.method('get_gameObject').invoke(),key=object.handle.toString();
                    if(objects.has(key))continue;objects.add(key);
                    layerOverrides.push({object,layer:object.method('get_layer').invoke()});object.method('set_layer').invoke(captureLayer);
                }
                const finder=core('Object').methods.find(m=>m.isStatic&&m.name==='FindObjectsOfType'&&m.parameters.length===1&&m.parameters[0].type.name==='System.Type');
                if(!finder)throw Error('NATIVE_LIGHT_ENUMERATION_UNAVAILABLE');
                for(const light of finder.invoke(core('Light').type.object)){
                    const mask=light.method('get_cullingMask').invoke();
                    lightOverrides.push({light,mask});light.method('set_cullingMask').invoke(mask|(1<<captureLayer));
                }
            }
            const body=main().method('get_GlobalBus').invoke().method('get_Common3D').invoke().method('get_AvatarCamera').invoke().field('_body').value;
            const source=body.field('_templateCamera').value.method('get_PrimaryCamera').invoke();
            go=core('GameObject').alloc();go.method('.ctor',1).invoke(Il2Cpp.string('MCP temporary assembled wear capture'));
            const cam=go.method('AddComponent',1).invoke(core('Camera').type.object);cam.method('CopyFrom').invoke(source);
            cam.method('set_enabled').invoke(false);cam.method('set_orthographic').invoke(false);cam.method('set_fieldOfView').invoke(30);
            // CopyFrom may inherit a depth-only clear. A fresh pooled RT must
            // clear its colour buffer too, otherwise old poses remain as ghosts.
            cam.method('set_clearFlags').invoke(core('CameraClearFlags').field('SolidColor').value);
            cam.method('set_cullingMask').invoke(1<<captureLayer);
            capture=captureQuality.begin(size,args.quality);cam.method('set_allowMSAA').invoke(true);cam.method('set_targetTexture').invoke(capture.target);
            const [x,y,z]=center,d=distance/Math.sqrt(2),t=cam.method('get_transform').invoke();
            if(plan)t.method('set_position').invoke(vector(...plan.position));
            else t.method('set_position').invoke(view==='front'?vector(x,y,z+distance):view==='back'?vector(x,y,z-distance):view==='side'?vector(x+distance,y,z):vector(x+d,y,z+d));
            t.method('LookAt').overload('UnityEngine.Vector3','UnityEngine.Vector3').invoke(vector(...(plan?plan.target:[x,y,z])),vector(0,1,0));cam.method('Render').invoke();
            const base64=capture.encode();
            return {wear_token:e.token,view,width:size,height:size,mime_type:'image/png',bounds:{min:lo,max:hi},
                excluded_edit_renderer_count:excluded.length,
                capture_layer:captureLayer,color_buffer_cleared:true,light_masks_temporarily_extended:lightOverrides.length,temporary_preview_culling_bounds:boundsOverrides.length,
                quality:capture.metadata,...(plan?{framing:captureFraming.readback(cam,plan)}:{}),base64};
        }finally{
            for(const entry of boundsOverrides){const b=core('Bounds').alloc().unbox();b.method('.ctor',2).invoke(vector(...entry.center),vector(...entry.size));entry.renderer.method('set_localBounds').invoke(b);}
            for(const entry of lightOverrides)entry.light.method('set_cullingMask').invoke(entry.mask);
            for(const entry of layerOverrides)entry.object.method('set_layer').invoke(entry.layer);
            for(const entry of excluded)entry.renderer.method('set_enabled').invoke(entry.enabled);
            rtClass.method('set_active').invoke(oldActive);
            if(go)core('Object').method('DestroyImmediate',1).invoke(go);
            if(capture)capture.dispose();
        }
    }
    return {operations:{
        prepare_wear_vrm_export(args){
            const e=expect(args);
            if(vrmExportSession)throw Error('VRM_EXPORT_ALREADY_PENDING');
            if(e.vm.method('get_Preview').invoke().method('get_IsPreview').invoke())throw Error('STOP_WEAR_ANIMATION_FIRST');
            if(previewOverride)throw Error('RESET_WEAR_PREVIEW_CLIP_FIRST');
            const vm=e.vm.method('get_Preview').invoke().field('_exportContextViewModel').value,ctx=vm.field('Context').value;
            const previous=ctx.field('<CurrentExportMode>k__BackingField').value.field('value__').value;
            vrmExportSession={token:e.token,vm,ctx,previous,handles:[],submitted:false};
            const mode=Memory.alloc(4);mode.writeS32(3);invokeManaged(vm,'SetExportMode',[mode]);
            return {requested:true,wear_token:e.token,previous_mode:previous,mode:3};
        },
        wear_vrm_export_state(args){
            const e=expect(args),s=vrmExportSession;
            if(!s||s.token!==e.token)throw Error('NO_MATCHING_VRM_EXPORT');
            const root=s.ctx.method('GetCurrentExportRoot').invoke();
            return {wear_token:e.token,mode:s.ctx.field('<CurrentExportMode>k__BackingField').value.field('value__').value,
                ready:!root.handle.isNull()&&!s.ctx.field('_currentVrmConverter').value.handle.isNull(),
                renderers:root.handle.isNull()?0:components(root,core('SkinnedMeshRenderer')).length};
        },
        write_wear_vrm_export(args){
            const e=expect(args),s=vrmExportSession;
            if(!s||s.token!==e.token||s.submitted)throw Error('NO_MATCHING_UNSUBMITTED_VRM_EXPORT');
            if(s.ctx.field('<CurrentExportMode>k__BackingField').value.field('value__').value!==3)throw Error('VRM_EXPORT_MODE_CHANGED');
            if(!args.path||!args.path.toLowerCase().endsWith('.vrm'))throw Error('VRM_DESTINATION_REQUIRED');
            for(const name of ['title','author','version'])if(typeof args[name]!=='string'||!args[name].trim()||args[name].length>160||/[\x00-\x1f\x7f]/.test(args[name]))throw Error('INVALID_VRM_METADATA');
            const type=cls('XWear.Core','XWear.Core.Export.VrmExporter'),exporter=type.alloc();
            invokeManaged(exporter,'.ctor',[s.ctx.handle]);s.exporter=exporter;s.handles.push(retain(exporter));
            const meta=cls('VRM10','UniVRM10.VRM10ObjectMeta').alloc();invokeManaged(meta,'.ctor');s.handles.push(retain(meta));
            meta.field('Name').value=Il2Cpp.string(args.title);meta.field('Version').value=Il2Cpp.string(args.version);
            const authors=meta.field('Authors').value;authors.method('Clear').invoke();authors.method('Add').invoke(Il2Cpp.string(args.author));
            const completion=type.method('ExportVrm10').parameters[2].type.class.alloc();invokeManaged(completion,'.ctor');s.handles.push(retain(completion));
            s.submitted=true;
            return {...rememberTask(invokeManaged(exporter,'ExportVrm10',[Il2Cpp.string(args.path).handle,meta.handle,completion.handle])),wear_token:e.token};
        },
        finish_wear_vrm_export(args){
            const e=expect(args),s=vrmExportSession;
            if(!s||s.token!==e.token)throw Error('NO_MATCHING_VRM_EXPORT');
            if(s.exporter)invokeManaged(s.exporter,'Dispose');
            const mode=Memory.alloc(4);mode.writeS32(s.previous);invokeManaged(s.vm,'SetExportMode',[mode]);
            for(const h of s.handles)h.free();vrmExportSession=null;
            return {wear_token:e.token,restored_mode:s.previous,disposed:true};
        },
        get_wear_status:status,
        get_wear_snapshot:snapshot,
        inspect_wear_body_occlusion:bodyOcclusionSnapshot,
        set_wear_body_occlusion:setBodyOcclusion,
        inspect_wear_native_shoes:nativeShoeVisibilitySnapshot,
        set_wear_native_shoes_visible:setNativeShoeVisibility,
        capture_wear_reference:wearReference,
        wear_capture:capture,
        wear_framing_reference:framingReference,
        wear_motion_sample:motionSample,
        sample_wear_preview_rig:samplePreviewRig,
        list_wear_preview_clips(args){const e=expect(args);return {wear_token:e.token,clips:nativeClips().map(c=>({id:c.handle.toString(),name:text(c.method('get_name').invoke()),duration_seconds:c.method('get_length').invoke(),humanoid:null})),
            selected_preview_clip:status().selected_preview_clip,scope:'Allowlisted native body motions/pose; humanoid getter unavailable in this build; session-local IDs, no animation asset export'};},
        select_wear_preview_clip:selectPreviewClip,
        hold_wear_preview_pose:freezePreviewPose,
        pose_wear_preview_legs:posePreviewLegs,
        wear_motion_debug(args){
            const e=expect(args),preview=e.vm.method('get_Preview').invoke(),context=preview.field('_exportContextViewModel').value,timeline=preview.field('_previewTimeline').value;
            const tracks=[];
            if(!timeline.handle.isNull())for(let i=0;i<timeline.method('get_outputTrackCount').invoke();i++){
                const track=timeline.method('GetOutputTrack').invoke(i);
                const clips=sequence(track.method('GetClips').invoke()).map(c=>{
                    const asset=c.method('get_asset').invoke();
                    return {name:text(c.method('get_displayName').invoke()),start:c.method('get_start').invoke(),duration:c.method('get_duration').invoke(),
                        asset:asset.handle.isNull()?null:describe(asset)};
                });
                tracks.push({name:text(track.method('get_name').invoke()),clips});
            }
            const resources=core('Resources'),finder=resources.methods.find(m=>m.isStatic&&m.name==='FindObjectsOfTypeAll'&&m.parameters.length===1&&m.parameters[0].type.name==='System.Type');
            const loaded=finder?[...finder.invoke(cls('UnityEngine.AnimationModule','UnityEngine.AnimationClip').type.object)].map(c=>({
                id:c.handle.toString(),name:text(c.method('get_name').invoke()),length:c.method('get_length').invoke()})):[];
            const director=preview.field('_currentDirector').value;
            return {status:status(),director:director.handle.isNull()?null:describe(director),export_context:describe(context),timeline:timeline.handle.isNull()?null:describe(timeline),
                tracks,loaded_animation_clips:loaded,
                children:context.class.fields.filter(f=>!f.isStatic&&/Photo|Animation|Preview|Motion/.test(f.type.name)).map(f=>{
                    const child=context.field(f.name).value;return {field:f.name,object:child&&child.handle&&!child.handle.isNull()?describe(child):null};})};
        },
        wear_scope_save_cache:scopeSaveCache,
        open_wear_project(args){expect(args,false);if(args.discard_unsaved!==true)throw Error('EXPLICIT_DISCARD_REQUIRED');
            restorePreviewClip();
            generation++;return rememberTask(invokeManaged(main(),args.path.toLowerCase().endsWith('.xroid')?'MoveToXWearEditRootWithXRoidFile':'MoveToXWearEditRootWithVRoidFile',[Il2Cpp.string(args.path).handle]));},
        set_wear_fit(args){const e=expect(args),item=[...e.vm.method('get_DressItems').invoke()].find(o=>o.handle.toString()===args.item_id);
            if(!item)throw Error('UNKNOWN_WEAR_ITEM');
            if(!Number.isFinite(args.fit_y)||!Number.isFinite(args.fit_z)||args.fit_y<0||args.fit_y>2||args.fit_z<0||args.fit_z>2)throw Error('FIT_RANGE: 0..2');
            if(e.vm.method('get_Preview').invoke().method('get_IsPreview').invoke())throw Error('STOP_WEAR_ANIMATION_FIRST');
            const f=item.field('_autoFittingProperty').value;
            for(const [key,value] of [['FitY',args.fit_y],['FitZ',args.fit_z]]){const p=Memory.alloc(4);p.writeFloat(value);invokeManaged(f,'set_'+key,[p]);}
            return status();},
        set_wear_animation(args){const e=expect(args);if(typeof args.playing!=='boolean')throw Error('BOOLEAN_REQUIRED');
            restoreLegPose();
            const current=e.vm.method('get_Preview').invoke().method('get_IsPreview').invoke();
            if(current!==args.playing)invokeManaged(e.vm,'ToggleAnimationState');return status();},
        save_wear_project(args){const e=expect(args);if(e.vm.method('get_Preview').invoke().method('get_IsPreview').invoke())throw Error('STOP_WEAR_ANIMATION_FIRST');
            if(legPose)throw Error('RESET_PREVIEW_LEG_POSE_FIRST');
            if(previewOverride)throw Error('RESET_WEAR_PREVIEW_CLIP_FIRST');
            const scoped=scopeSaveCache(args);
            const context=e.vm.field('EditContext').value,mask=Memory.alloc(4);
            const body=main().method('get_GlobalBus').invoke().method('get_Common3D').invoke().method('get_AvatarCamera').invoke().field('_body').value;
            const source=body.field('_templateCamera').value.method('get_PrimaryCamera').invoke();
            mask.writeS32(source.method('get_cullingMask').invoke());
            // Opening a .vroid has no previous XRoid thumbnail. The native UI takes
            // this before saving; call the same API rather than inventing a cache file.
            invokeManaged(context,'TakeThumbnail',[mask]);
            return {...rememberTask(invokeManaged(context,'SaveXRoid',[Il2Cpp.string(args.path).handle])),cache_path:scoped.cache_path};},
        import_xwear(args){const e=expect(args);if(e.vm.method('get_Preview').invoke().method('get_IsPreview').invoke())throw Error('STOP_WEAR_ANIMATION_FIRST');
            const alert=e.vm.method('get_SettingsViewModel').invoke().method('get_AutoFitAlertSettingViewModel').invoke();
            const previous={alert:alert.method('get_IsAutoFitAlertDisplayed').invoke(),auto:alert.method('get_AlwaysRunAutoFit').invoke()};
            const restore=()=>{invokeManaged(alert,'set_IsAutoFitAlertDisplayed',[boolArg(previous.alert)]);invokeManaged(alert,'set_AlwaysRunAutoFit',[boolArg(previous.auto)]);};
            try{
                // Import without a GUI fit/delete dialog. Fitting is an explicit separate tool.
                invokeManaged(alert,'set_IsAutoFitAlertDisplayed',[boolArg(false)]);
                invokeManaged(alert,'set_AlwaysRunAutoFit',[boolArg(false)]);
                const path=cls('VRoid.Studio','VRoid.Studio.Util.ResourcePath.FullAccessibleResourcePath').alloc();
                invokeManaged(path,'.ctor',[Il2Cpp.string(args.path).handle]);
                const task=rememberTask(invokeManaged(e.vm,'ImportXWear',[path.handle]));
                imports.set(task.task_id,{restore,hold:retain(alert)});generation++;return task;
            }catch(error){restore();throw error;}},
        wear_finish_import(args){const entry=imports.get(args.task_id);if(entry){try{entry.restore();}finally{entry.hold.free();imports.delete(args.task_id);}}return status();},
        wear_clear_save_path(args){const e=expect(args);invokeManaged(e.vm.field('EditContext').value,'UpdateXRoidPath',[Il2Cpp.string('').handle]);return status();},
        wear_set_save_path(args){const e=expect(args);if(!ATTACHED||!args.path)throw Error('ATTACHED_PATH_REQUIRED');
            const context=e.vm.field('EditContext').value;
            invokeManaged(context,'UpdateXRoidPath',[Il2Cpp.string(args.path).handle]);
            const actual=text(context.method('GetCurrentXRoidPath').invoke());
            if(actual!==args.path)throw Error('WEAR_SAVE_PATH_READBACK_FAILED: '+actual);
            return {...status(),save_path:actual};},
        wear_debug(){const e=editor(),context=e.vm.field('EditContext').value,saver=context.field('_xRoidSaver').value;
            return {status:status(),editor:describe(e.vm),context:describe(context),saver:describe(saver),
            saver_cache:describe(saver.field('CacheDirectory').value),
            saver_cache_values:saver.field('CacheDirectory').value.class.fields.filter(f=>!f.isStatic).map(f=>({name:f.name,type:f.type.name,value:f.type.name==='System.String'?text(saver.field('CacheDirectory').value.field(f.name).value):null})),
            thumbnail_method:context.class.method('TakeThumbnail').parameters.map(p=>({name:p.name,type:p.type.name})),
            saver_values:saver.class.fields.filter(f=>!f.isStatic).map(f=>{
                const v=saver.field(f.name).value;return {name:f.name,type:f.type.name,value:f.type.name==='System.String'?text(v):
                    typeof v==='number'||typeof v==='boolean'?v:v&&v.handle?{null:v.handle.isNull(),type:v.class?.type.name}:null};}),
            preview:describe(e.vm.method('get_Preview').invoke()),preview_model:describe(e.vm.method('get_Preview').invoke().field('_previewModel').value),contents:describe(context.field('EditContents').value),alert:describe(e.vm.method('get_SettingsViewModel').invoke().method('get_AutoFitAlertSettingViewModel').invoke()),items:[...e.vm.method('get_DressItems').invoke()].map(o=>({item:describe(o),fit:describe(o.field('_autoFittingProperty').value)}))};}
    }};
}
