// Ordinary-edit parts and VRM export, adapted from Karylcode/VRoid-MCP
// commit baaa94e2fdc0419c68cb83b0ecc0b61fcc5661dd (MIT).
// See licenses/karylcode-upstream-20261023.txt.
function createOrdinaryExtensions({model, cls, core, text, invokeManaged, retain, state}) {
    function customItemState(args) {
        if(!args.expected_model)throw Error('EXPECTED_MODEL_REQUIRED');
        const m=model(args.expected_model),registry=m.root.field('_customItemRegistry').value;
        const files=[],it=registry.field('_pathToFileCustomItemModels').value.method('get_Values').invoke().method('GetEnumerator').invoke();
        try { while(it.method('MoveNext').invoke()) {
            const f=it.method('get_Current').invoke();
            files.push({id:text(f.method('get_TransferableGroupId').invoke()),
                group_type:text(f.method('get_TransferableGroupTypeId').invoke()),
                path:text(f.method('get_FilePath').invoke()),name:text(f.method('get_DisplayName').invoke())});
        }} finally {it.method('Dispose').invoke();}
        const allowed=registry.method('get_CustomizableTransferableGroupTypes').invoke();
        const parts=listParts(args).parts.filter(p=>allowed.method('Contains').invoke(Il2Cpp.string(p.group_type)));
        return {model_token:m.token,base_path:text(registry.field('_basePath').value),parts,files};
    }
    function saveCustomItem(args) {
        if(!args.expected_model)throw Error('EXPECTED_MODEL_REQUIRED');
        const m=model(args.expected_model),snapshot=customItemState(args);
        if(!snapshot.parts.some(p=>p.id===args.part_id))throw Error('CUSTOM_ITEM_NOT_SAVABLE');
        const registry=m.root.field('_customItemRegistry').value;
        const meta=cls('VRoid.Studio','VRoid.Studio.Saving.VRoidCustomItemFileMetaData')
            .method('CreateWithVRoidFileMetaData').invoke(m.engine.method('get_VRoidFileMetaData').invoke());
        const thumbnail=m.engine.method('CaptureThumbnail').invoke(
            cls('VRoidCore','VRoidCore.Common.Container.EncodedThumbnailType').field('Png').value);
        // false requests a new item, never overwrite. The returned bool is not a persistence receipt.
        cls('VRoid.Studio','VRoid.Studio.ModelPresetsSelector.CustomItemSaveUtil').method('SaveCustomItem')
            .invoke(registry,m.context,meta,Il2Cpp.string(args.part_id),false,NULL,NULL,thumbnail);
        return {requested:true,frame:state.frame};
    }
    function listParts(args) {
        if(!args.expected_model)throw Error('EXPECTED_MODEL_REQUIRED');
        // Every active transferable group: what the model is built from, by native id and resource.
        const m=model(args.expected_model),parts=[];
        const it=m.context.method('get_ActiveModel').invoke().method('GetActiveTransferableGroups').invoke()
            .method('get_Values').invoke().method('GetEnumerator').invoke();
        try{while(it.method('MoveNext').invoke()){
            const g=it.method('get_Current').invoke(),type=text(g.method('get_Type').invoke()),res=text(g.method('get_ResourceName').invoke());
            parts.push({id:text(g.method('get_Id').invoke()),type:type.split('.').pop(),group_type:type,resource_name:res,
                original_resource_name:text(g.method('get_OriginalResourceName').invoke()),custom:!!res&&res.startsWith('user/'),
                updated:g.method('get_UpdatedSinceLastRevision').invoke()});
        }}finally{it.method('Dispose').invoke();}
        return {model_token:m.token,parts:parts.sort((a,b)=>a.type.localeCompare(b.type)||a.id.localeCompare(b.id))};
    }
    let partCallbacks=null;
    function managedCallbacks() {
        // Frida-made delegates crash when VRoid invokes them from its async loader, so build real managed
        // delegates over harmless corlib/Unity methods: success is a no-op, errors go to Player.log.
        if(partCallbacks)return partCallbacks;
        const typeOf=c=>c.type.object,typeClass=Il2Cpp.corlib.class('System.Type');
        const create=(delegateClass,methodInfo)=>Il2Cpp.corlib.class('System.Delegate').method('CreateDelegate')
            .overload('System.Type','System.Reflection.MethodInfo').invoke(typeOf(delegateClass),methodInfo);
        const thread=typeOf(Il2Cpp.corlib.class('System.Threading.Thread'));
        const noop=thread.method('GetMethod').overload('System.String','System.Type[]')
            .invoke(Il2Cpp.string('MemoryBarrier'),Il2Cpp.array(typeClass,0));
        const exception=Il2Cpp.corlib.class('System.Exception');
        const logException=typeOf(core('Debug')).method('GetMethod').overload('System.String','System.Type[]')
            .invoke(Il2Cpp.string('LogException'),Il2Cpp.array(typeClass,[typeOf(exception)]));
        const ok=create(Il2Cpp.corlib.class('System.Action'),noop);
        const fail=create(Il2Cpp.corlib.class('System.Action`1').inflate(exception),logException);
        partCallbacks={ok,fail,handles:[retain(ok),retain(fail)]};
        return partCallbacks;
    }
    function replacePart(args) {
        // Native Context.LoadAndReplaceTransferableGroup: swaps exactly one built-in part by id.
        if(!args.expected_model)throw Error('EXPECTED_MODEL_REQUIRED');
        if(typeof args.part_id!=='string'||!args.part_id.endsWith('.transferablegroup'))throw Error('PART_ID_REQUIRED: a *.transferablegroup id');
        const m=model(args.expected_model);
        const custom=customItemState(args).files.find(f=>f.id===args.part_id);
        if(custom){
            const c=cls('VRoid.Studio','VRoid.Studio.ModelPresetsSelector.CustomItemOptionViewModel');
            const option=Il2Cpp.gc.choose(c).find(o=>{
                const context=o.field('_context').value,item=o.field('_model').value;
                return !context.handle.isNull()&&context.handle.equals(m.context.handle)&&!item.handle.isNull()
                    &&text(item.method('get_TransferableGroupId').invoke())===args.part_id;
            });
            if(!option)throw Error('CUSTOM_ITEM_OPTION_NOT_READY: reopen the model and list parts again');
            const enabled=Memory.alloc(1);enabled.writeU8(1);
            invokeManaged(option,'set_IsSelected',[enabled]);
            return {requested:true,part_id:args.part_id,frame:state.frame};
        }
        // An id missing from the asset catalog (e.g. from a file made with an older VRoid, or a custom
        // item id) makes the native loader throw outside any handler and VRoid crashes: refuse it here.
        const registry=Il2Cpp.gc.choose(cls('VRoid.Studio','VRoid.Studio.ModelPresetsSelector.CustomItemRegistry'))[0];
        if(!registry)throw Error('ASSET_CATALOG_NOT_FOUND');
        if(!registry.field('_assetCatalog').value.method('ContainsId').invoke(Il2Cpp.string(args.part_id)))
            throw Error('UNKNOWN_PART_ID: not in this VRoid\'s asset catalog; for closet custom items use list_presets and apply_preset');
        const {ok,fail}=managedCallbacks();
        const preserveMaterial=Memory.alloc(1);preserveMaterial.writeU8(0);
        invokeManaged(m.context,'LoadAndReplaceTransferableGroup',[Il2Cpp.string(args.part_id).handle,ok.handle,fail.handle,preserveMaterial]);
        return {requested:true,part_id:args.part_id,frame:state.frame};
    }
    // VRM export through VRoid's own photo-booth exporter, given a path instead of the save dialog.
    let vrmJob=null;
    const findClass=name=>{for(const a of Il2Cpp.domain.assemblies){const c=a.image.tryClass(name);if(c)return c;}throw Error('CLASS_NOT_FOUND: '+name);};
    const flag=v=>{const b=Memory.alloc(1);b.writeU8(v?1:0);return b;};
    const booth=m=>m.root.field('obsoleteLegacyPhotoBoothViewModel').value;
    const screenNav=m=>m.main.method('get_GlobalBus').invoke().method('get_ScreenNavigation').invoke();
    const EXPORT_SCREEN='VRoid.Studio.VRMExportScreen.ViewModel';
    function vrmExportState(args) {
        const m=model(args.expected_model),b=booth(m),screen=screenNav(m).method('get_ActiveScreen').invoke().class.type.name;
        const settings=b.method('get_IsActive').invoke()?b.method('get_ExportSettings').invoke():null;
        return {model_token:m.token,export_screen:screen===EXPORT_SCREEN,busy:!!vrmJob,frame:state.frame,
            ready:!!settings&&!settings.handle.isNull()&&!b.field('_isBlockingUpdateExportPreview').value};
    }
    function enterVrmExport(args) {
        if(!args.expected_model)throw Error('EXPECTED_MODEL_REQUIRED');
        const m=model(args.expected_model);invokeManaged(m.root,'EnterToVRMExport');
        return {model_token:m.token,frame:state.frame};
    }
    function leaveVrmExport(args) {
        const m=model(args.expected_model),nav=screenNav(m),screen=nav.method('get_ActiveScreen').invoke();
        if(screen.class.type.name===EXPORT_SCREEN)invokeManaged(nav,'Pop',[screen.handle,flag(false)]);
        return {model_token:m.token,frame:state.frame};
    }
    function stringList(value) {
        const list=Il2Cpp.corlib.class('System.Collections.Generic.List`1').inflate(Il2Cpp.corlib.class('System.String')).new();
        for(const s of String(value||'').split(/\s*,\s*/).filter(Boolean))list.method('Add').invoke(Il2Cpp.string(s));
        return list;
    }
    function vrmMeta(m,version,dialogMeta,args) {
        // The settings' meta objects stay empty until the dialog fills them; build from the model's stored export meta.
        const app=m.context.method('get_ActiveModel').invoke().method('get_AppState').invoke();
        const src=app.method(version===0?'get_Vrm0Export':'get_Vrm1Export').invoke(),get=n=>src.field('<'+n+'>k__BackingField').value;
        const str=n=>Il2Cpp.string(text(get(n))||'');
        if(version===0){
            const meta=findClass('VRM.glTF_VRM_Meta').new();
            for(const [k,n] of [['title','Title'],['version','Version'],['author','Author'],['contactInformation','ContactInformation'],
                ['reference','Reference'],['otherPermissionUrl','OtherPermissionUrl'],['otherLicenseUrl','OtherLicenseUrl']])meta.field(k).value=str(n);
            for(const [k,n] of [['allowedUserName','AllowedUserName'],['violentUssageName','ViolentUssageName'],['sexualUssageName','SexualUssageName'],
                ['commercialUssageName','CommercialUssageName'],['licenseName','LicenseName']])meta.field(k).value=Il2Cpp.string(get(n).toString());
            if(args.title)meta.field('title').value=Il2Cpp.string(args.title);
            if(args.author)meta.field('author').value=Il2Cpp.string(args.author);
            meta.field('texture').value=dialogMeta.handle.isNull()?-1:dialogMeta.field('texture').value;
            if(!text(meta.field('title').value))throw Error('VRM_META_TITLE_REQUIRED: set the model\'s VRM title in VRoid first');
            return meta;
        }
        const meta=findClass('UniVRM10.VRM10ObjectMeta').new();
        for(const n of ['Name','Version','CopyrightInformation','ContactInformation','ThirdPartyLicenses','OtherLicenseUrl'])meta.field(n).value=str(n);
        meta.field('Authors').value=stringList(text(get('Authors')));meta.field('References').value=stringList(text(get('References')));
        if(args.title)meta.field('Name').value=Il2Cpp.string(args.title);
        if(args.author)meta.field('Authors').value=stringList(args.author);
        for(const n of ['AvatarPermission','ViolentUsage','SexualUsage','CommercialUsage','PoliticalOrReligiousUsage','AntisocialOrHateUsage',
            'CreditNotation','Redistribution','Modification'])meta.field(n).value=get(n);
        if(!dialogMeta.handle.isNull()&&!dialogMeta.field('Thumbnail').value.handle.isNull())meta.field('Thumbnail').value=dialogMeta.field('Thumbnail').value;
        if(!text(meta.field('Name').value))throw Error('VRM_META_NAME_REQUIRED: set the model\'s VRM name in VRoid first');
        return meta;
    }
    function managedSignal() {
        // Action bound to ManualResetEventSlim.Set: a real managed delegate whose firing can be polled.
        const c=Il2Cpp.corlib.class('System.Threading.ManualResetEventSlim'),event=c.new();
        const set=c.type.object.method('GetMethod').overload('System.String','System.Type[]').invoke(Il2Cpp.string('Set'),Il2Cpp.array(Il2Cpp.corlib.class('System.Type'),0));
        const action=Il2Cpp.corlib.class('System.Delegate').method('CreateDelegate').overload('System.Type','System.Object','System.Reflection.MethodInfo')
            .invoke(Il2Cpp.corlib.class('System.Action').type.object,event,set);
        return {event,action,handles:[retain(event),retain(action)]};
    }
    function progressLog() {
        const dbl=Il2Cpp.corlib.class('System.Double'),listClass=Il2Cpp.corlib.class('System.Collections.Generic.List`1').inflate(dbl),list=listClass.new();
        const add=listClass.type.object.method('GetMethod').overload('System.String').invoke(Il2Cpp.string('Add'));
        const action=Il2Cpp.corlib.class('System.Delegate').method('CreateDelegate').overload('System.Type','System.Object','System.Reflection.MethodInfo')
            .invoke(Il2Cpp.corlib.class('System.Action`1').inflate(dbl).type.object,list,add);
        return {list,action,handles:[retain(list),retain(action)]};
    }
    function startVrmExport(args) {
        if(!args.expected_model)throw Error('EXPECTED_MODEL_REQUIRED');
        if(vrmJob)throw Error('VRM_EXPORT_BUSY');
        if(![0,1].includes(args.version)||typeof args.path!=='string'||!/\.vrm$/i.test(args.path))throw Error('VRM_EXPORT_ARGS: version 0|1 and a .vrm path');
        const m=model(args.expected_model),b=booth(m),settings=b.method('get_ExportSettings').invoke();
        if(settings.handle.isNull())throw Error('VRM_EXPORT_NOT_READY: enter the export screen first');
        const meta=vrmMeta(m,args.version,settings.method(args.version===0?'get_VRM0MetaData':'get_VRM10MetaData').invoke(),args);
        const ok=managedSignal(),fail=managedSignal(),progress=progressLog();
        const hair=args.hair_combination??settings.field('isEnableHairCombination').value;
        const reduction=findClass('VRoidStudio.PhotoBooth.MaterialReductionMode').field('None').value;
        const routine=b.method(args.version===0?'ExportVRM0':'ExportVRM1').invoke(Il2Cpp.string(args.path),meta,!!hair,false,reduction,false,ok.action,fail.action,progress.action);
        // The view model's coroutines need a MonoBehaviour host; a temporary GameObject keeps VRoid's UI untouched.
        const go=core('GameObject').alloc();go.method('.ctor',1).invoke(Il2Cpp.string('VRoid MCP VRM export'));
        go.method('AddComponent',1).invoke(findClass('UnityEngine.UI.LayoutElement').type.object).method('StartCoroutine').overload('System.Collections.IEnumerator').invoke(routine);
        vrmJob={ok,fail,progress,go,handles:[retain(go),retain(meta),retain(routine)]};
        return {started:true,version:args.version,path:args.path,hair_combination:!!hair};
    }
    function vrmExportStatus() {
        if(!vrmJob)return {running:false};
        const done=vrmJob.ok.event.method('get_IsSet').invoke(),failed=vrmJob.fail.event.method('get_IsSet').invoke();
        const n=vrmJob.progress.list.method('get_Count').invoke(),progress=n?vrmJob.progress.list.method('get_Item').invoke(n-1):0;
        if(!done&&!failed)return {running:true,progress};
        core('Object').method('Destroy',1).invoke(vrmJob.go);
        [...vrmJob.ok.handles,...vrmJob.fail.handles,...vrmJob.progress.handles,...vrmJob.handles].forEach(h=>h.free());vrmJob=null;
        return {running:false,done,failed,progress};
    }
    return {operations:{list_parts:listParts, replace_part:replacePart,
        custom_item_state:customItemState, save_custom_item:saveCustomItem,
        vrm_export_state:vrmExportState,
        enter_vrm_export:enterVrmExport, leave_vrm_export:leaveVrmExport,
        start_vrm_export:startVrmExport, vrm_export_status:vrmExportStatus}};
}
