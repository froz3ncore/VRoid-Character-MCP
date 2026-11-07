// CameraView.cs / FacePreview.cs adaptation, mcjo79/vroid-mcp 0dc7d5e (MIT).
// See licenses/mcjo79-0dc7d5e.txt and MIGRATION.md. No saved model commands.
const editorCameraModes=['Front','Right','Top','Reverse','RotateUp','RotateLeft','RotateRight','RotateDown'];
function validateEditorCamera(args){
    const fields={get:[],angles:['angles'],rotate:['angles'],zoom:['delta'],pan:['pan'],reset:[],mode:['mode'],projection:[],custom:['position','center']};
    if(!Object.hasOwn(fields,args.action))throw Error('INVALID_EDITOR_CAMERA_ACTION');
    if(typeof args.expected_model!=='string'||!args.expected_model)throw Error('EXPECTED_MODEL_REQUIRED');
    for(const key of ['angles','delta','pan','mode','position','center'])if(args[key]!=null&&!fields[args.action].includes(key))throw Error('UNRELATED_CAMERA_ARGUMENT: '+key);
    const vector=(v,n,b)=>Array.isArray(v)&&v.length===n&&v.every(x=>typeof x==='number'&&Number.isFinite(x)&&Math.abs(x)<=b);
    if(['angles','rotate'].includes(args.action)&&!vector(args.angles,2,36000))throw Error('INVALID_CAMERA_ANGLES');
    if(args.action==='zoom'&&(typeof args.delta!=='number'||!Number.isFinite(args.delta)||Math.abs(args.delta)>1000))throw Error('INVALID_CAMERA_DELTA');
    if(args.action==='pan'&&!vector(args.pan,2,1000))throw Error('INVALID_CAMERA_PAN');
    if(args.action==='mode'&&!editorCameraModes.includes(args.mode))throw Error('INVALID_CAMERA_MODE');
    if(args.action==='custom'&&(!vector(args.position,3,10000)||!vector(args.center,3,10000)||args.position.every((x,i)=>x===args.center[i])))throw Error('INVALID_CAMERA_CUSTOM');
}
function createEditorPreview({adapter,beforeMutation=()=>{}}){
    let snapshot=null,tracked=null;
    function validShapes(rows){
        if(!Array.isArray(rows)||rows.length>4096||rows.some((s,i)=>s.index!==i||typeof s.name!=='string'||!Number.isFinite(s.weight)))throw Error('NONFINITE_OR_INVALID_NATIVE_BLENDSHAPE');
        return rows;
    }
    function execute(name,args,work){
        let attempted=false,guardState='not_entered';
        try{return {...work(()=>{guardState='checking';beforeMutation(name);guardState='accepted';},()=>{attempted=true;}),
            ok:true,native_invocation_attempted:attempted,guard_state:guardState,uncertain:false};}
        catch(error){
            const definiteGuard=guardState==='checking'&&error.attached_guard_prewrite===true
                &&error.attached_guard_bookkeeping_attempted===false&&error.native_uncertain!==true;
            const uncertain=attempted||error.native_uncertain===true||(guardState!=='not_entered'&&!definiteGuard);
            if(attempted&&name==='face_preview'&&tracked)tracked.weights=null;
            const dispatchState=!uncertain?'prewrite_rejected':attempted?'invocation_unconfirmed':
                error.attached_guard_bookkeeping_attempted?'guard_bookkeeping_unconfirmed':guardState==='checking'?'guard_unconfirmed':'native_entry_unconfirmed';
            return {model_token:args.expected_model,ok:false,uncertain,
            native_invocation_attempted:attempted,guard_state:definiteGuard?'prewrite_rejected':guardState,
            dispatch_state:dispatchState,error:String(error)};}
    }
    function open(expected){if(typeof expected!=='string'||!expected)throw Error('EXPECTED_MODEL_REQUIRED');return adapter.open(expected);}
    function verify(expected){
        const c=open(expected),identity=adapter.identity(c);
        if(tracked&&tracked.token===expected){
            if(tracked.identity!==identity)throw Error('STALE_PREVIEW_RENDERER');
            if(tracked.weights===null)throw Error('PREVIEW_WRITE_UNCONFIRMED: do not retry');
            const now=validShapes(adapter.face(c));
            if(tracked.weights&&(now.length!==tracked.names.length||now.some((s,i)=>s.name!==tracked.names[i]||Math.abs(s.weight-tracked.weights[i])>.001)))throw Error('PREVIEW_WEIGHT_CHANGED_BEFORE_CAPTURE');
        }
        return c;
    }
    function camera(args,guard=()=>{},nativeEntry=()=>{}){
        validateEditorCamera(args);const c=open(args.expected_model);adapter.identity(c);
        let action=args.action,request=args;
        const before=adapter.cameraState(c);
        if(action==='rotate'){
            request={...args,angles:before.angles.map((x,i)=>x+args.angles[i])};
            validateEditorCamera({...request,action:'angles'});action='angles';
        }
        if(action!=='get'){
            const invoke=adapter.prepareCameraAction?adapter.prepareCameraAction(c,action,request):onEntry=>{onEntry();adapter.cameraAction(c,action,request);};
            guard();invoke(nativeEntry);
        }
        const result=adapter.cameraState(c);adapter.identity(c);
        if(action==='projection'&&result.projection===before.projection)throw Error('CAMERA_PROJECTION_TOGGLE_UNCONFIRMED');
        return {model_token:c.token,...result,units:{angles:'degrees',pan:'native_delta',zoom:'native_delta'},
            unavailable_fields:['zoom_scalar','pan_scalar'],saved_model_changed:false};
    }
    function face(args,guard=()=>{},nativeEntry=()=>{}){
        if(args.name!=null&&(typeof args.name!=='string'||!args.name||args.name.length>256))throw Error('INVALID_BLENDSHAPE_NAME');
        if(args.filter!=null&&(typeof args.filter!=='string'||args.filter.length>256))throw Error('INVALID_BLENDSHAPE_FILTER');
        const weight=args.weight===undefined?100:args.weight;
        if(typeof weight!=='number'||!Number.isFinite(weight)||weight<0||weight>100)throw Error('INVALID_BLENDSHAPE_WEIGHT');
        if(args.reset!=null&&typeof args.reset!=='boolean'||args.restore!=null&&typeof args.restore!=='boolean')throw Error('INVALID_PREVIEW_RESET');
        if([!!args.name,!!args.reset,!!args.restore].filter(Boolean).length>1)throw Error('CONFLICTING_PREVIEW_ACTIONS');
        const c=open(args.expected_model),identity=adapter.identity(c),all=validShapes(adapter.face(c));
        if(tracked&&tracked.token===c.token&&tracked.identity!==identity)throw Error('STALE_PREVIEW_RENDERER');
        if((args.restore||args.reset)&&snapshot&&snapshot.token===c.token&&snapshot.identity!==identity)throw Error('STALE_PREVIEW_RENDERER');
        let changed=[];
        if(args.name){
            const exact=all.filter(s=>s.name.toLowerCase()===args.name.toLowerCase());
            changed=exact.length?exact:all.filter(s=>s.name.toLowerCase().endsWith(args.name.toLowerCase()));
            if(changed.length!==1)throw Error(changed.length?'AMBIGUOUS_BLENDSHAPE_SUFFIX':'BLENDSHAPE_NOT_FOUND');
        }else if(args.reset||args.restore)changed=all;
        if(args.restore&&(!snapshot||snapshot.token!==c.token||snapshot.identity!==identity))throw Error('PREVIEW_SNAPSHOT_UNAVAILABLE');
        if(args.restore&&(snapshot.shapes.length!==all.length||all.some((s,i)=>s.name!==snapshot.shapes[i].name)))throw Error('PREVIEW_SNAPSHOT_UNAVAILABLE');
        if(changed.length){
            const original=snapshot&&snapshot.token===c.token&&snapshot.identity===identity?snapshot:{token:c.token,identity,shapes:all.map(s=>({...s}))};
            if(args.restore&&(original.shapes.length!==all.length||all.some((s,i)=>s.name!==original.shapes[i].name)))throw Error('PREVIEW_SNAPSHOT_UNAVAILABLE');
            // Snapshot precedes every raw write; partial failures retain the receipt.
            const batch=adapter.beginFaceBatch?adapter.beginFaceBatch(c):{setWeight:(i,w,onEntry)=>{onEntry();adapter.setWeight(c,i,w);},dispose:()=>{}};
            try{
                guard();
                snapshot=original;tracked={token:c.token,identity,names:all.map(s=>s.name),weights:null};
                for(const shape of changed)batch.setWeight(shape.index,args.restore?snapshot.shapes[shape.index].weight:args.reset?0:weight,nativeEntry);
                const result=validShapes(adapter.face(c));adapter.identity(c);
                for(const shape of changed){const expected=args.restore?snapshot.shapes[shape.index].weight:args.reset?0:weight;
                    if(result[shape.index].name!==all[shape.index].name||Math.abs(result[shape.index].weight-expected)>.001)throw Error('PREVIEW_WEIGHT_READBACK_FAILED');}
                tracked.weights=result.map(s=>s.weight);
            }finally{batch.dispose();}
        }
        const result=validShapes(adapter.face(c));adapter.identity(c);
        if(changed.length&&(result.length!==tracked.names.length||tracked.weights.some((v,i)=>result[i]?.weight!==v||result[i]?.name!==tracked.names[i])))throw Error('PREVIEW_LATE_WEIGHT_READBACK_FAILED');
        if(args.restore){snapshot=null;tracked=null;}
        return {model_token:c.token,preview_identity:identity,shapes:result.filter(s=>!args.filter||s.name.toLowerCase().includes(args.filter.toLowerCase())),
            changed_indices:changed.map(s=>s.index),saved_model_changed:false,
            reset_to_zero:!!args.reset,restored_original:!!args.restore,restoration_verified:!!args.restore,
            persistence:'raw renderer weights; rebuild or animation may replace them; checked again at capture'};
    }
    return {verify,verifyIfTracked(expected){if(tracked&&tracked.token===expected)return verify(expected);return null;},open,adapter,operations:{
        editor_camera:args=>execute('editor_camera',args,(guard,entry)=>camera(args,guard,entry)),
        face_preview:args=>execute('face_preview',args,(guard,entry)=>face(args,guard,entry)),
        get_editor_camera:args=>camera({...args,action:'get'}),
        list_face_preview:args=>face({...args,name:null,reset:false,restore:false}),
    }};
}

function createEditorPreviewNative({model,core,cls,text,retain=()=>({free(){}})}){
    const id=o=>o.handle.toString(),same=(a,b)=>a&&!a.handle.isNull()&&b&&!b.handle.isNull()&&a.handle.equals(b.handle);
    const type=(o,name)=>{if(!o||o.handle.isNull()||o.class.type.name!==name)throw Error('EDITOR_NATIVE_TYPE_MISMATCH: '+name);return o;};
    function values(v,n){return ['x','y','z','w'].slice(0,n).map(k=>v.field(k).value);}
    function vector(v){const o=core('Vector'+v.length).alloc().unbox();o.method('.ctor',v.length).invoke(...v);return o;}
    function requireActive(o){if(!o.method('get_gameObject').invoke().method('get_activeInHierarchy').invoke())throw Error('EDITOR_COMPONENT_INACTIVE');}
    function open(expected){
        const m=model(expected),bus=m.main.method('get_GlobalBus').invoke();
        const screen=bus.method('get_ScreenNavigation').invoke().method('get_ActiveScreen').invoke();
        if(!same(screen,m.root))throw Error('ACTIVE_EDIT_ROOT_REQUIRED');
        if(!same(m.root.field('_engineModel').value,m.engine)||!same(m.face.field('_engine').value,m.engine)
            ||!same(m.face.method('get_GlobalBus').invoke(),bus))throw Error('EDITOR_MODEL_BUS_MISMATCH');
        const origin=bus.method('get_ModelOrigin').invoke(),renderer=type(m.face.method('GetFaceSMR').invoke(),'UnityEngine.SkinnedMeshRenderer');
        let t=renderer.method('get_transform').invoke(),owned=false;
        for(let n=0;n<64&&!t.handle.isNull();n++,t=t.method('get_parent').invoke())if(same(t,origin)){owned=true;break;}
        if(!owned)throw Error('FACE_RENDERER_OUTSIDE_CURRENT_MODEL');
        requireActive(renderer);
        const mesh=type(renderer.method('get_sharedMesh').invoke(),'UnityEngine.Mesh');
        const controller=type(bus.method('get_EditAvatarCameraPosition').invoke(),'VRoid.UI.Component.AvatarCameraPosition');
        if(same(controller,bus.method('get_PhotoBoothAvatarCameraPosition').invoke()))throw Error('EDITOR_PHOTO_CAMERA_ALIAS');
        requireActive(controller);
        if(!controller.method('get_isActiveAndEnabled').invoke())throw Error('EDITOR_CONTROLLER_DISABLED');
        const rig=controller.field('_multipleRenderTextureCamera').value;
        let camera,group=null;
        if(!rig.handle.isNull()){
            type(rig,'VRoid.UI.Component.MultipleRenderTextureCamera');
            const wrapper=bus.method('get_Common3D').invoke().method('get_AvatarCamera').invoke();
            if(!same(wrapper.field('_body').value,rig)||!same(rig.method('get_transform').invoke(),controller.method('get_transform').invoke()))throw Error('EDITOR_RIG_OWNERSHIP_MISMATCH');
            const enumerator=rig.method('get_InstantiatedCameras').invoke().method('get_Keys').invoke().method('GetEnumerator').invoke();
            const candidates=[];let count=0;
            try{while(enumerator.method('MoveNext').invoke()){
                if(++count>32)throw Error('EDITOR_CAMERA_GROUP_LIMIT');
                const g=type(enumerator.method('get_Current').invoke(),'VRoid.UI.Component.CameraGroup');
                const primary=type(g.method('get_PrimaryCamera').invoke(),'UnityEngine.Camera');
                if(primary.method('get_enabled').invoke()&&primary.method('get_gameObject').invoke().method('get_activeInHierarchy').invoke())candidates.push({group:g,camera:primary});
            }}finally{if(enumerator.tryMethod('Dispose'))enumerator.method('Dispose').invoke();}
            if(candidates.length!==1)throw Error('AMBIGUOUS_ACTIVE_EDITOR_CAMERA: '+candidates.length);
            ({camera,group}=candidates[0]);
        }else{
            camera=type(controller.field('_unityCamera').value,'UnityEngine.Camera');
            if(!same(camera.method('get_transform').invoke(),controller.method('get_transform').invoke()))throw Error('EDITOR_SINGLE_CAMERA_OWNERSHIP_MISMATCH');
            requireActive(camera);if(!camera.method('get_enabled').invoke())throw Error('EDITOR_CAMERA_DISABLED');
        }
        const identity=[m.token,id(m.engine),id(m.root),id(bus),id(origin),id(renderer),renderer.method('GetInstanceID').invoke(),id(mesh),mesh.method('GetInstanceID').invoke(),id(controller),id(camera),group?id(group):null].join('|');
        return {token:m.token,m,bus,origin,renderer,mesh,controller,rig,camera,group,identity};
    }
    function identity(c){const fresh=open(c.token);if(fresh.identity!==c.identity)throw Error('STALE_EDITOR_PREVIEW_IDENTITY');return c.identity;}
    function cameraState(c){
        identity(c);const cam=c.camera,tr=c.controller.method('get_transform').invoke();
        const result={preview_identity:c.identity,controller_id:id(c.controller),camera_id:id(cam),group_id:c.group?id(c.group):null,
            camera_path:c.group?'owned_instantiated_group':'owned_single_camera',angles:values(c.controller.method('GetAngles').invoke(),2),
            position:values(tr.method('get_position').invoke(),3),center:values(c.controller.field('_rotationCenter').value,3),
            projection:cam.method('get_orthographic').invoke()?'orthographic':'perspective',fov_degrees:cam.method('get_fieldOfView').invoke(),
            orthographic_size:cam.method('get_orthographicSize').invoke(),aspect:cam.method('get_aspect').invoke(),
            rotating:c.controller.field('_isRunningCameraRotateCoroutine').value};
        if(![...result.angles,...result.position,...result.center,result.fov_degrees,result.orthographic_size,result.aspect].every(Number.isFinite))throw Error('NONFINITE_EDITOR_CAMERA_STATE');
        return result;
    }
    function prepareCameraAction(c,action,args){
        identity(c);const api=c.controller;
        const names={angles:'ChangeAngles',pan:'Pan',zoom:'Zoom',reset:'ResetPosition',projection:'SwitchCameraProjection',custom:'SetCustomView',mode:'RotateAxis'};
        const method=api.method(names[action]);let mode;
        if(action==='mode'){
            const enumClass=cls('VRoid.UI','VRoid.UI.Component.AvatarCameraPosition').nestedClasses.find(c=>c.name==='CameraRotationMode');
            if(!enumClass)throw Error('NATIVE_CAMERA_MODE_UNAVAILABLE');
            const field=enumClass.fields.find(f=>f.isStatic&&f.name===args.mode);
            if(!field)throw Error('NATIVE_CAMERA_MODE_UNAVAILABLE');mode=field.value;
        }
        return (onEntry=()=>{})=>{
            const values=action==='angles'?[vector(args.angles)]:action==='pan'?[vector(args.pan)]:
                action==='zoom'?[args.delta]:action==='custom'?[vector(args.position),vector(args.center)]:action==='mode'?[mode]:[];
            onEntry();method.invoke(...values);
        };
    }
    const cameraAction=(c,action,args)=>prepareCameraAction(c,action,args)();
    function face(c){identity(c);const count=c.mesh.method('get_blendShapeCount').invoke();
        if(count<0||count>4096)throw Error('BLENDSHAPE_COUNT_LIMIT');
        return Array.from({length:count},(_,index)=>({index,name:text(c.mesh.method('GetBlendShapeName').invoke(index)),weight:c.renderer.method('GetBlendShapeWeight').invoke(index)}));}
    function cheapFaceIdentity(c){
        const file=c.m.main.field('_mainModel').value.field('currentFile').value;
        if(!same(file,c.m.file)||!same(file.field('engine').value,c.m.engine)||!same(c.m.face.method('GetFaceSMR').invoke(),c.renderer)
            ||!same(c.m.main.method('get_GlobalBus').invoke(),c.bus)
            ||!same(c.bus.method('get_ScreenNavigation').invoke().method('get_ActiveScreen').invoke(),c.m.root)
            ||!same(c.renderer.method('get_sharedMesh').invoke(),c.mesh))throw Error('STALE_FACE_BATCH');
    }
    return {open,identity,cameraState,cameraAction,prepareCameraAction,face,
        setWeight(c,i,w){identity(c);c.renderer.method('SetBlendShapeWeight').invoke(i,w);},
        beginFaceBatch(c){
            identity(c);const pins=[];
            function release(){const failures=[];for(const pin of pins.splice(0).reverse())try{pin.free();}catch(error){failures.push(String(error));}
                if(failures.length){const error=Error('FACE_BATCH_PIN_CLEANUP_FAILED: '+failures.join('; '));error.native_uncertain=true;throw error;}}
            try{for(const object of [c.renderer,c.mesh,c.m.engine,c.m.root])pins.push(retain(object));}
            catch(error){error.native_uncertain=true;try{release();}catch(cleanup){error.message+='; '+String(cleanup);}throw error;}
            return {setWeight(i,w,onEntry=()=>{}){cheapFaceIdentity(c);const setter=c.renderer.method('SetBlendShapeWeight');onEntry();setter.invoke(i,w);},
                dispose:release};
        }};
}
