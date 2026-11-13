// Settings/lifecycle adapted from mcjo79/vroid-mcp VrmExport.cs
// 0dc7d5eb3cf27f7f943713960cac1b65f479a876 (MIT); see licenses/mcjo79-0dc7d5e.txt.
// Keep ordinary VRM export separate from the XWear exporter.
function createVrmExportApi({model, text, invokeManaged, retain, metadata}) {
    let job = null;
    const meshNames = {delete_transparent:'MeshErasure',hair_cross_section:'HairCrossSection',
        hair_smoothness:'HairSmoothnessRate',hair:'HairReductionStrength',face:'FaceReductionStrength',
        body:'BodyReductionStrength',outfit:'ClothingReductionStrength'};
    const settingNames = {combine_hair:'IsEnableHairCombination',material_mode:'MaterialReductionModeIndex',
        atlas_resolution:'AtlasResolutionIndex',texture_mode:'TextureCompressionModeIndex'};
    const choiceNames = {material_mode:['MaterialReductionModeItems','MaterialReductionMode'],
        atlas_resolution:['AtlasResolutionItems','AtlasResolution'],texture_mode:['TextureCompressionModeItems','TextureCompressionMode']};
    const flags = ['delete_transparent','hair_cross_section','combine_hair'];
    const sliders = ['hair_smoothness','hair','face','body','outfit','hair_bones'];
    const get = (o, name) => o.method('get_'+name).invoke();
    const present = o => !!o && !o.handle.isNull();
    function expect(args) {
        if(!args.expected_model)throw Error('EXPECTED_MODEL_REQUIRED');
        const m=model(args.expected_model),b=m.root.field('obsoleteLegacyPhotoBoothViewModel').value;
        return {m,b};
    }
    function settings(b) {
        if(!present(b))throw Error('VRM_EXPORT_NOT_READY');
        const s=get(b,'ExportSettings');
        if(!present(s))throw Error('VRM_EXPORT_NOT_READY');
        return s;
    }
    function snapshot(args) {
        const {m,b}=expect(args),s=settings(b),mesh=get(s,'MeshReduction'),values={},choices={};
        for(const [key,name] of Object.entries(meshNames))values[key]=get(mesh,name);
        for(const [key,name] of Object.entries(settingNames))values[key]=get(s,name);
        const bones=get(s,'hairBoneReduction');
        values.hair_bones=present(bones)?get(bones,'HairReductionStrength'):null;
        for(const [key,[name,value]] of Object.entries(choiceNames)) {
            const list=get(s,name),items=[];
            if(present(list))for(let index=0;index<get(list,'Count');index++){
                const item=list.method('get_Item').invoke(index),native=get(item,value);
                // Enum getters return unboxed value types through the bridge.
                // System.Enum.ToString requires a managed boxed receiver.
                const boxed=native && typeof native.box==='function'?native.box():native;
                const hold=boxed!==native?retain(boxed):null;
                let serialized;
                try { serialized=boxed && typeof boxed.method==='function'
                    ? text(boxed.method('ToString').invoke()) : String(boxed); }
                finally { if(hold)hold.free(); }
                items.push({index,name:text(get(item,'TranslatedDisplayName')),value:serialized});
            }
            choices[key]=items;
        }
        return {model_token:m.token,settings:values,choices};
    }
    function validate(options, choices) {
        if(!options||typeof options!=='object'||Array.isArray(options))throw Error('INVALID_VRM_OPTIONS');
        for(const [key,value] of Object.entries(options)) {
            let valid=false;
            if(flags.includes(key))valid=typeof value==='boolean';
            else if(sliders.includes(key))valid=Number.isInteger(value)&&value>=0&&value<=100;
            else if(key in choiceNames)valid=Number.isInteger(value)&&choices[key].some(v=>v.index===value);
            if(!valid)throw Error('INVALID_VRM_OPTION: '+key);
        }
    }
    function set(o,name,value) {
        if(get(o,name)===value)return;
        // Source C# assignments allow implicit numeric conversion. Derive the
        // real setter type instead of assuming every native slider is Int32.
        const type=o.method('set_'+name,1).parameters[0].type.name;
        const arg=Memory.alloc(type==='System.Double'?8:4);
        if(type==='System.Boolean' && typeof value==='boolean')arg.writeU8(value?1:0);
        else if(type==='System.Int32' && Number.isInteger(value))arg.writeS32(value);
        else if(type==='System.Single' && typeof value==='number')arg.writeFloat(value);
        else if(type==='System.Double' && typeof value==='number')arg.writeDouble(value);
        else throw Error('VRM_SETTING_SIGNATURE_MISMATCH: '+name+': '+type);
        invokeManaged(o,'set_'+name,[arg]);
    }
    function apply(args) {
        if(job)throw Error('VRM_EXPORT_BUSY');
        const {b}=expect(args),s=settings(b),before=snapshot(args);
        validate(args.options,before.choices);
        if(!['mesh','material','texture'].includes(args.stage))throw Error('INVALID_VRM_OPTIONS_STAGE');
        const options=args.options;
        if(args.stage==='mesh')for(const [key,name] of Object.entries(meshNames))if(key in options)set(get(s,'MeshReduction'),name,options[key]);
        if(args.stage==='material') {
            if('hair_bones' in options) {
                const bones=get(s,'hairBoneReduction');
                if(present(bones))set(bones,'HairReductionStrength',options.hair_bones);
            }
            for(const key of ['combine_hair','material_mode'])if(key in options)set(s,settingNames[key],options[key]);
        }
        if(args.stage==='texture') {
            for(const key of ['atlas_resolution','texture_mode'])if(key in options)set(s,settingNames[key],options[key]);
            // Source 2.14.0 setter can refuse the UI-only shrink toggle. Read back
            // after the setter and expose the actual backing-field result in snapshot.
            if('texture_mode' in options && get(s,'TextureCompressionModeIndex')!==options.texture_mode)
                s.field('textureCompressionModeIndex').value=options.texture_mode;
        }
        return snapshot(args);
    }
    function preview(args) {
        const {m,b}=expect(args);
        if(!present(b))return {model_token:m.token,busy:!!job,ready:false,preview_avatar:false};
        const active=get(b,'IsActive'),s=active?get(b,'ExportSettings'):null;
        const avatar=active?get(b,'PreviewAvatar'):null;
        const blocked=!!b.field('_isBlockingUpdateExportPreview').value;
        const queued=present(b.field('waitForPointerUpAndUpdateExportPreview').value);
        const updating=m.main.field('_editModelTransform').value.method('get_IsUpdatingModel').invoke();
        return {model_token:m.token,busy:!!job,ready:active&&present(s)&&present(avatar)&&!blocked&&!queued&&!updating,
            preview_avatar:present(avatar),preview_blocked:blocked,preview_queued:queued,updating};
    }
    function start(args) {
        if(job)throw Error('VRM_EXPORT_BUSY');
        if(!Number.isInteger(args.version)||![0,1].includes(args.version)||typeof args.path!=='string'||!/\.vrm$/i.test(args.path))throw Error('INVALID_VRM_EXPORT_ARGS');
        for(const key of ['title','author','model_version'])if(args[key]!=null &&
            (typeof args[key]!=='string'||!args[key].trim()||args[key].length>160||/[\x00-\x1f\x7f]/.test(args[key])))throw Error('INVALID_VRM_METADATA');
        const {m,b}=expect(args),s=settings(b);
        if(!preview(args).ready)throw Error('VRM_EXPORT_NOT_READY');
        const method=args.version===0?'OnVRMSettingChanged':'OnVRM1SettingChanged';
        // Derive the closed TaskCompletionSource<bool> type from this build's
        // actual third parameter, following the existing XWear allocation idiom.
        const signature=b.method(method,3),type=signature.parameters[2].type;
        if(!/TaskCompletionSource/.test(type.name)||!/(Boolean|bool)/.test(type.name))throw Error('VRM_COMPLETION_SIGNATURE_MISMATCH');
        const meta=metadata(m,args.version,s.method(args.version===0?'get_VRM0MetaData':'get_VRM10MetaData').invoke(),args);
        const completion=type.class.alloc();invokeManaged(completion,'.ctor');
        const task=get(completion,'Task');
        job={token:m.token,completion,task,handles:[retain(b),retain(meta),retain(completion),retain(task)]};
        // Install retained state before invocation. A managed exception is not
        // proof that the async native entry point never dispatched work.
        invokeManaged(b,method,[meta.handle,Il2Cpp.string(args.path).handle,completion.handle]);
        return {started:true,version:args.version,path:args.path};
    }
    function status(args) {
        if(!job)return {running:false,done:false};
        const {m}=expect(args);
        if(m.token!==job.token)throw Error('STALE_VRM_EXPORT');
        const task=job.task;
        if(!get(task,'IsCompleted'))return {running:true};
        const faulted=!!get(task,'IsFaulted'),canceled=!!get(task,'IsCanceled');
        const result=!faulted&&!canceled?get(task,'Result'):false;
        return {running:false,done:!faulted&&!canceled&&result===true,result,faulted,canceled,
            ...(faulted?{error:text(get(task,'Exception').method('ToString').invoke())}:{})};
    }
    function finish(args) {
        const result=status(args);
        if(!job||!result.done||args.output_stable!==true||!preview(args).ready)throw Error('VRM_EXPORT_NOT_SAFE_TO_RELEASE');
        releaseWork();
        return {released:true};
    }
    function pendingWork() {
        if (!job) return [];
        try {
            if (get(job.task,'IsCompleted')===true) return [];
            return [{kind:'vrm_export',model_token:job.token}];
        } catch(error) { return [{kind:'vrm_export',model_token:job.token,error:String(error)}]; }
    }
    function releaseWork() {
        if (!job) return;
        for (const handle of job.handles) handle.free();
        job=null;
    }
    return {isPending:()=>!!job,pendingWork,releaseWork,operations:{vrm_export_options:snapshot,apply_vrm_export_options:apply,
        vrm_export_preview:preview,start_vrm_export:start,vrm_export_status:status,finish_vrm_export:finish}};
}
