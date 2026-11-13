// Unity application framebuffer, never desktop input or an offscreen fallback.
function createAppFrameCapture({subscribe,identity,read,now=()=>Date.now(),ttl=10000}){
    const jobs=new Map();let next=0;
    function cleanup(job){if(job.cancel){job.cancel();job.cancel=null;}if(job.timer){clearTimeout(job.timer);job.timer=null;}}
    function expire(){for(const job of jobs.values()){
        if(!job.completed&&now()>=job.deadline){cleanup(job);job.completed=true;job.error='APP_FRAME_TIMEOUT';job.retireAt=now()+ttl;job.timer=setTimeout(expire,ttl+1);}
        else if(job.completed&&now()>=job.retireAt){cleanup(job);jobs.delete(job.id);}
    }}
    function start(expected){
        expire();if(jobs.size)throw Error('APP_FRAME_PENDING_RESULT');
        const owner=identity(expected),job={id:++next,deadline:now()+ttl,completed:false,cancel:null};jobs.set(job.id,job);
        try{job.cancel=subscribe(()=>{
            if(job.completed)return;
            cleanup(job);job.completed=true;
            try{if(now()>=job.deadline)throw Error('APP_FRAME_TIMEOUT');
                if(identity(expected)!==owner)throw Error('APP_FRAME_IDENTITY_CHANGED');
                const result=read(expected);
                if(identity(expected)!==owner)throw Error('APP_FRAME_IDENTITY_CHANGED');
                job.result={...result,model_token:expected,provenance:'unity_application_frame',phase:'UnityEngine.Awaitable.OnEndOfFrame.onLeave',preview_identity:owner};
            }catch(error){job.error=String(error);}
            job.retireAt=now()+ttl;job.timer=setTimeout(expire,ttl+1);
        });job.timer=setTimeout(expire,ttl+1);
        }catch(error){cleanup(job);jobs.delete(job.id);throw error;}
        return {id:job.id};
    }
    function poll({id}){expire();const job=jobs.get(id);if(!job)throw Error('UNKNOWN_APP_FRAME_JOB');
        if(!job.completed)return {completed:false};jobs.delete(id);cleanup(job);return {completed:true,result:job.result,error:job.error};}
    function dispose(){for(const job of jobs.values())cleanup(job);jobs.clear();}
    return {start,poll,dispose,expire};
}
function createNativeAppFrame({core,cls,preview,mainThread,frame}){
    let requestedUnityFrame=null;
    function identity(expected){return preview.adapter.identity(preview.verify(expected));}
    function subscribe(callback){
        requestedUnityFrame=core('Time').method('get_frameCount').invoke();
        const awaitable=core('Awaitable');
        // Idempotent managed gate wires Unity's actual end-of-frame callback.
        // This is not an Update callback or a later ordinary frame counter.
        awaitable.method('EnsureDelayedCallWiredUp').invoke();
        const address=awaitable.method('OnEndOfFrame').virtualAddress;
        if(address.isNull())throw Error('END_OF_FRAME_NATIVE_CALLBACK_UNAVAILABLE');
        return (()=>{const hook=Interceptor.attach(address,{onLeave(){
            if(Process.getCurrentThreadId()===mainThread())callback();
        }});return ()=>hook.detach();})();
    }
    function read(expected){
        preview.verify(expected);
        const unityFrame=core('Time').method('get_frameCount').invoke();
        if(!Number.isInteger(unityFrame)||unityFrame<requestedUnityFrame)throw Error('APP_FRAME_COUNT_INVALID');
        const screen=core('Screen'),w=screen.method('get_width').invoke(),h=screen.method('get_height').invoke();
        if(!Number.isInteger(w)||!Number.isInteger(h)||w<1||h<1||w*h>8000000)throw Error('APP_FRAME_PIXEL_BUDGET');
        const rt=core('RenderTexture'),active=rt.method('get_active').invoke();let texture=null;
        try{
            rt.method('set_active').invoke(NULL);
            texture=core('Texture2D').alloc();texture.method('.ctor',2).invoke(w,h);
            const rect=core('Rect').alloc().unbox();rect.method('.ctor',4).invoke(0,0,w,h);
            texture.method('ReadPixels',4).invoke(rect,0,0,false);texture.method('Apply',2).invoke(false,false);
            const bytes=cls('UnityEngine.ImageConversionModule','UnityEngine.ImageConversion').method('EncodeToPNG',1).invoke(texture);
            const base64=Il2Cpp.corlib.class('System.Convert').method('ToBase64String').overload('System.Byte[]').invoke(bytes).content;
            return {width:w,height:h,mime_type:'image/png',base64,view:'current_editor',frame:unityFrame,
                requested_unity_frame:requestedUnityFrame,bridge_frame:frame(),
                quality:{source:'live_Unity_QualitySettings',msaa_samples:core('QualitySettings').method('get_antiAliasing').invoke(),
                    msaa_verification:'application_quality_setting_not_render_target_readback',ssaa:'application_owned'},
                framing:preview.adapter.cameraState(preview.open(expected))};
        }finally{captureCleanup([()=>rt.method('set_active').invoke(active),
            ()=>{if(texture)core('Object').method('DestroyImmediate',1).invoke(texture);}]);}
    }
    return createAppFrameCapture({subscribe,identity,read});
}
