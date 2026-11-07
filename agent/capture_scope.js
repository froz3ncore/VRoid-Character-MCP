// Guide-free camera configuration without clearing selection or leaving features.
// Named BuildModifier bindings audited on ed65; material overrides fail before writes.
function createCleanCaptureScope({model}){
    const id=o=>o.handle.toString();
    function inspectNative(m,{clonedCamera=false}={}){
        const modifier=m.engine.method('get_BuildModifier').invoke();
        if(modifier.class.type.name!=='VRoid.Studio.Engine.BuildModifier')throw Error('CAPTURE_BUILD_MODIFIER_TYPE');
        const selected=modifier.field('_selectedHairStrands').value.method('get_Count').invoke();
        const bones=modifier.field('_boneGroupOverrideMaterials').value.method('get_Count').invoke();
        if(!Number.isInteger(selected)||!Number.isInteger(bones)||selected<0||bones<0)throw Error('CAPTURE_PRESENTATION_STATE_UNAVAILABLE');
        if(bones||selected&&!clonedCamera)throw Error('CAPTURE_PRESENTATION_OVERRIDE_ACTIVE: clear bone material overrides'+(!clonedCamera?' and photo hair selection':'')+' in the editor before capture; no selection was changed');
        if(modifier.method('get_NeedsUpdate').invoke())throw Error('CAPTURE_PRESENTATION_UPDATE_PENDING');
        const layers=modifier.field('_resources').value.field('_layers').value;
        if(layers.class.type.name!=='VRoid.UI.LayerConstants')throw Error('CAPTURE_LAYER_CONSTANTS_TYPE');
        const layer=name=>{const value=layers.method('get_'+name).invoke();if(!Number.isInteger(value)||value<0||value>31)throw Error('CAPTURE_LAYER_UNAVAILABLE: '+name);return value;};
        const mask=layers.method('get_MaskAvatarCamera').invoke();if(!Number.isInteger(mask)||mask< -2147483648||mask>2147483647)throw Error('CAPTURE_AVATAR_MASK_UNAVAILABLE');
        const outline=layer('Outline'),excluded=['UI','UI3D','UI3DGizmo','BrushPreview'].map(layer);
        const cullingMask=(mask|(1<<outline))&~excluded.reduce((value,index)=>value|(1<<index),0);
        if(!(cullingMask&(1<<outline)))throw Error('CAPTURE_LAYER_MASK_CONFLICT');
        return {model_token:m.token,engine_id:id(m.engine),root_id:id(m.root),modifier_id:id(modifier),
            selected_hair_overrides:selected,bone_material_overrides:0,culling_mask:cullingMask,outline_layer:outline,
            cloned_camera_without_selection_outline:clonedCamera,
            excluded_guide_layers:excluded,ui_visibility:'unchanged',policy:'native_avatar_mask_without_auxiliary_guides; preserve selected hair on Outline in an isolated clone; reject bone material overrides'};
    }
    function inspect(m,options){
        try{return inspectNative(m,options);}
        catch(error){if(String(error).includes('CAPTURE_'))throw error;
            throw Error('CAPTURE_GUIDE_ISOLATION_UNAVAILABLE: this runtime lacks a verified named presentation/layer binding; no selection or UI was changed; '+String(error));}
    }
    function verify(m,scope){const current=model(m.token);
        if(id(current.engine)!==scope.engine_id||id(current.root)!==scope.root_id)throw Error('CAPTURE_OWNER_CHANGED');
        const actual=inspect(current,{clonedCamera:scope.cloned_camera_without_selection_outline});if(JSON.stringify(actual)!==JSON.stringify(scope))throw Error('CAPTURE_PRESENTATION_CHANGED');return actual;
    }
    function apply(camera,scope){camera.method('set_cullingMask').invoke(scope.culling_mask);
        if(camera.method('get_cullingMask').invoke()!==scope.culling_mask)throw Error('CAPTURE_MASK_READBACK_FAILED');}
    return {inspect,verify,apply};
}
