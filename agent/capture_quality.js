// Screenshot-only adaptation of brainrom/vroid-studio-mcp RenderQuality.cs.
// MIT attribution: vroid_mcp/data/capture_quality/NOTICE. No global quality changes.
function captureCleanup(actions){
    const errors=[];for(const action of actions)try{action();}catch(error){errors.push(String(error));}
    if(errors.length)throw Error('CAPTURE_CLEANUP_FAILED: '+errors.join('; '));
}
function captureQualityPlan(size,quality='balanced',options={}) {
    if(!Number.isInteger(size)||size<256||size>2048)throw Error('CAPTURE_SIZE_RANGE: 256..2048');
    if(!['legacy','balanced','high'].includes(quality))throw Error('UNSUPPORTED_CAPTURE_QUALITY');
    const {width,height,msaa,ssaa}=options,present=v=>v!==undefined&&v!==null;
    if(present(width)!==present(height))throw Error('CAPTURE_DIMENSIONS_PAIRED');
    const w=present(width)?width:size,h=present(height)?height:size;
    if(![w,h].every(v=>Number.isInteger(v)&&v>=256&&v<=2048))throw Error('CAPTURE_DIMENSIONS_RANGE');
    if(present(msaa)&&![1,2,4].includes(msaa))throw Error('CAPTURE_MSAA_RANGE');
    if(present(ssaa)&&![1,2,3].includes(ssaa))throw Error('CAPTURE_SSAA_RANGE');
    const scale=present(ssaa)?ssaa:quality==='high'?2:1,effective=Math.min(scale,Math.sqrt(8000000/(w*h)));
    const rw=Math.floor(w*effective),rh=Math.floor(h*effective);
    return {quality,output_size:size,render_size:rw,output_width:w,output_height:h,render_width:rw,render_height:rh,
        requested_scale:scale,effective_scale:rw/w,effective_scale_x:rw/w,effective_scale_y:rh/h,
        requested_msaa:present(msaa)?msaa:quality==='legacy'?1:4,pixel_budget:8000000,clamped:rw!==w*scale||rh!==h*scale};
}

function createCaptureQuality({core,cls,invokeManaged}) {
    function begin(size,quality,options={}) {
        const plan=captureQualityPlan(size,quality,options),rtClass=core('RenderTexture'),destroy=core('Object').method('DestroyImmediate',1);
        const active=rtClass.method('get_active').invoke(),owned=[];let texture=null;
        const started=Date.now();
        function dispose(){
            const image=texture;texture=null;
            captureCleanup([()=>rtClass.method('set_active').invoke(active),()=>{if(image)destroy.invoke(image);},
                ...owned.splice(0).reverse().flatMap(rt=>[()=>rt.method('Release').invoke(),()=>destroy.invoke(rt)])]);
        }
        function single(width,height,depth=0){
            const rt=rtClass.alloc();owned.push(rt);rt.method('.ctor',3).invoke(width,height,depth);rt.method('set_name').invoke(Il2Cpp.string('MCP capture RT'));
            if(!rt.method('Create').invoke())throw Error('CAPTURE_TEXTURE_CREATE_FAILED');return rt;
        }
        try{
            // This supported build has a get-only RT antiAliasing property.
            // Rebuild through its descriptor, as the upstream implementation does.
            let target=single(plan.render_width,plan.render_height,24);
            if(plan.requested_msaa>1){
                const desc=target.method('get_descriptor').invoke();
                // The shipped IL2CPP binary strips the descriptor setter and
                // SystemInfo MSAA query. Use its real backing field and read
                // back the created texture; never invent hardware support.
                desc.field('<msaaSamples>k__BackingField').value=plan.requested_msaa;
                const msaa=rtClass.alloc();owned.push(msaa);invokeManaged(msaa,'.ctor',[desc.handle]);msaa.method('set_name').invoke(Il2Cpp.string('MCP capture MSAA RT'));
                if(!msaa.method('Create').invoke())throw Error('CAPTURE_MSAA_TEXTURE_CREATE_FAILED');target=msaa;
            }
            target.method('set_filterMode').invoke(1); // bilinear downsampling, exact 2x at normal sizes
            if(target.method('get_width').invoke()!==plan.render_width||target.method('get_height').invoke()!==plan.render_height)
                throw Error('CAPTURE_RENDER_SIZE_READBACK_MISMATCH');
            const actual=target.method('get_antiAliasing').invoke();
            if(![1,2,4].includes(actual)||actual>plan.requested_msaa)throw Error('CAPTURE_MSAA_READBACK_INVALID: '+actual);
            const metadata={...plan,msaa_samples:actual,hardware_downgrade:actual<plan.requested_msaa,
                downgrade_reason:actual<plan.requested_msaa?'Created GPU texture reports '+actual+' samples':null,
                msaa_verification:'created_render_texture_readback'};
            return {target,metadata,
                encode(){
                    let read=target;
                    // bindMS is false on this descriptor. Unity's Blit resolves
                    // the MSAA source into a single-sample RT. The explicit
                    // ResolveAntiAliasedSurface API is stripped in this build.
                    if(actual>1){read=single(plan.render_width,plan.render_height);core('Graphics').method('Blit').overload('UnityEngine.Texture','UnityEngine.RenderTexture').invoke(target,read);read.method('set_filterMode').invoke(1);}
                    if(plan.render_width!==plan.output_width||plan.render_height!==plan.output_height){const output=single(plan.output_width,plan.output_height);core('Graphics').method('Blit').overload('UnityEngine.Texture','UnityEngine.RenderTexture').invoke(read,output);read=output;}
                    rtClass.method('set_active').invoke(read);
                    texture=core('Texture2D').alloc();texture.method('.ctor',2).invoke(plan.output_width,plan.output_height);
                    texture.method('set_name').invoke(Il2Cpp.string('MCP capture readback'));
                    const rect=core('Rect').alloc().unbox();rect.method('.ctor',4).invoke(0,0,plan.output_width,plan.output_height);
                    texture.method('ReadPixels',4).invoke(rect,0,0,false);texture.method('Apply',2).invoke(false,false);
                    const bytes=cls('UnityEngine.ImageConversionModule','UnityEngine.ImageConversion').method('EncodeToPNG',1).invoke(texture);
                    metadata.render_and_encode_ms=Date.now()-started;
                    return Il2Cpp.corlib.class('System.Convert').method('ToBase64String').overload('System.Byte[]').invoke(bytes).content;
                },dispose};
        }catch(error){dispose();throw error;}
    }
    return {begin};
}
