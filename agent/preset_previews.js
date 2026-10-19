// Thumbnail addressing adapted from brainrom/vroid-studio-mcp (MIT), commit a6b0719.
// Copyright (c) 2026 Ilya Chelyadin and vroid-studio-mcp contributors.
// Full notice: vroid_mcp/data/preset_labels/LICENSE and NOTICE.
globalThis.createPresetPreviewApi = ({model,main,presetEntries,core,text}) => {
    const pending=new Map();let serial=0;
    function get(object,name){
        const getter=object.tryMethod('get_'+name,0);
        return getter?getter.invoke():object.field(name).value;
    }
    function release(holder){
        holder.taskHandle?.free();holder.optionHandle?.free();pending.delete(holder.id);
    }
    function finish(holder,extra){
        const result={model_token:holder.token,preset_id:holder.preset_id,resource_name:holder.resource_name,
            completed:true,...extra};
        release(holder);return result;
    }
    function encode(texture){
        if(!texture||texture.handle.isNull())throw Error('PREVIEW_TEXTURE_MISSING');
        const width=texture.method('get_width').invoke(),height=texture.method('get_height').invoke();
        if(width<1||height<1||width>8192||height>8192)throw Error('PREVIEW_TEXTURE_DIMENSIONS');
        const factor=Math.min(1,512/Math.max(width,height));
        const w=Math.max(1,Math.round(width*factor)),h=Math.max(1,Math.round(height*factor));
        const rtClass=core('RenderTexture'),oldActive=rtClass.method('get_active').invoke();
        let rt=null,copy=null;
        try{
            // Blit also handles non-readable Texture2D assets and bounds response size.
            rt=rtClass.alloc();rt.method('.ctor',3).invoke(w,h,0);rt.method('Create').invoke();
            core('Graphics').method('Blit').overload('UnityEngine.Texture','UnityEngine.RenderTexture').invoke(texture,rt);
            rtClass.method('set_active').invoke(rt);
            copy=core('Texture2D').alloc();copy.method('.ctor',2).invoke(w,h);
            const rect=core('Rect').alloc().unbox();rect.method('.ctor',4).invoke(0,0,w,h);
            copy.method('ReadPixels',4).invoke(rect,0,0,false);copy.method('Apply',2).invoke(false,false);
            const bytes=cls('UnityEngine.ImageConversionModule','UnityEngine.ImageConversion').method('EncodeToPNG',1).invoke(copy);
            if(bytes.length>2*1024*1024)throw Error('PREVIEW_PNG_TOO_LARGE');
            return {width:w,height:h,mime_type:'image/png',
                base64:Il2Cpp.corlib.class('System.Convert').method('ToBase64String').overload('System.Byte[]').invoke(bytes).content};
        }finally{
            rtClass.method('set_active').invoke(oldActive);
            if(copy)core('Object').method('DestroyImmediate',1).invoke(copy);
            if(rt){rt.method('Release').invoke();core('Object').method('DestroyImmediate',1).invoke(rt);}
        }
    }
    function direct(resource){
        const cut=resource?.indexOf('/TransferableGroupType.');
        if(cut===undefined||cut<0)return null;
        const bundle='vroid-thumbnails-'+resource.slice(0,cut).toLowerCase().replaceAll('/','-');
        const path='Assets/vroid-vroidcoredata/AssetBundles/Thumbnails/'+bundle+'/thumbnail.png';
        const manager=get(get(main().field('_mainModel').value,'assetStorage'),'bundleManager');
        const fs=manager.method('OpenReadOnly',1).invoke(Il2Cpp.string(bundle));
        if(fs.handle.isNull())return null;
        const method=fs.class.methods.find(m=>m.name==='GetObject'&&m.isGeneric&&m.parameterCount===1);
        if(!method)throw Error('THUMBNAIL_ASSET_METHOD_MISSING');
        return method.inflate(core('Texture2D')).bind(fs).invoke(Il2Cpp.string(path));
    }
    function poll(args){
        const holder=pending.get(args.request_id);
        if(!holder)throw Error('UNKNOWN_PREVIEW_REQUEST');
        if(args.expected_model!==holder.token)throw Error('STALE_PREVIEW_REQUEST');
        try{model(holder.token);}catch(error){release(holder);throw error;}
        try{
            if(Date.now()-holder.started>12000)return finish(holder,{ok:false,error:'PREVIEW_TIMEOUT',direct_error:holder.directError});
            if(!holder.task){
                const preview=get(holder.option,'Preview');
                if(!preview||preview.handle.isNull())return {model_token:holder.token,preset_id:holder.preset_id,completed:false,request_id:holder.id};
                holder.task=preview.method('Create',0).invoke();holder.taskHandle=retain(holder.task);
            }
            if(!holder.task.method('get_IsCompleted').invoke())return {model_token:holder.token,preset_id:holder.preset_id,completed:false,request_id:holder.id};
            if(holder.task.method('get_IsCanceled').invoke())return finish(holder,{ok:false,error:'PREVIEW_CANCELED'});
            if(holder.task.method('get_IsFaulted').invoke())return finish(holder,{ok:false,error:'PREVIEW_TASK_FAILED',
                detail:text(holder.task.method('get_Exception').invoke().method('ToString').invoke())});
            return finish(holder,{ok:true,source:'native_preview',...encode(holder.task.method('get_Result').invoke())});
        }catch(error){return finish(holder,{ok:false,error:'PREVIEW_UNAVAILABLE',detail:String(error),direct_error:holder.directError});}
    }
    function begin(args){
        if(!args.expected_model)throw Error('EXPECTED_MODEL_REQUIRED');
        const m=model(args.expected_model);
        const entry=presetEntries(m,args.area).find(p=>p.id===args.preset_id);
        if(!entry)throw Error('UNKNOWN_PRESET');
        if(!entry.owned)throw Error('PRESET_NOT_OWNED');
        const identity={model_token:m.token,preset_id:entry.id,resource_name:entry.resource_name,completed:true};
        if(entry.clear||!entry.resource_name)return {...identity,ok:false,error:'NO_PREVIEW_CLEAR'};
        let directError=null;
        try{
            const texture=direct(entry.resource_name);
            if(texture&&!texture.handle.isNull())return {...identity,ok:true,source:'native_thumbnail',...encode(texture)};
        }catch(error){directError=String(error);}
        // Only the resource/preview task is prepared; no preset is selected or applied.
        const holder={id:String(++serial),token:m.token,preset_id:entry.id,resource_name:entry.resource_name,
            option:entry.p,optionHandle:retain(entry.p),task:null,started:Date.now(),directError};
        pending.set(holder.id,holder);
        try{entry.p.method('PrepareResources',0).invoke();return poll({expected_model:m.token,request_id:holder.id});}
        catch(error){return finish(holder,{ok:false,error:'PREVIEW_UNAVAILABLE',detail:String(error),direct_error:directError});}
    }
    return {operations:{preset_preview_begin:begin,preset_preview_poll:poll,
        preset_preview_cancel(args){const h=pending.get(args.request_id);
            if(h&&h.token!==args.expected_model)throw Error('STALE_PREVIEW_REQUEST');
            if(h)release(h);return {released:!!h};}}};
};
