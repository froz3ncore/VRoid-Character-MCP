// Screenshot-only adaptation of brainrom/vroid-studio-mcp RenderQuality.cs.
// MIT attribution: vroid_mcp/data/capture_quality/NOTICE. No global quality changes.
function captureQualityPlan(size,quality='balanced') {
    if(!Number.isInteger(size)||size<256||size>2048)throw Error('CAPTURE_SIZE_RANGE: 256..2048');
    if(!['legacy','balanced','high'].includes(quality))throw Error('UNSUPPORTED_CAPTURE_QUALITY');
    const scale=quality==='high'?2:1,side=Math.min(size*scale,Math.floor(Math.sqrt(8000000)));
    return {quality,output_size:size,render_size:side,requested_scale:scale,effective_scale:side/size,
        requested_msaa:quality==='legacy'?1:4,pixel_budget:8000000,clamped:side!==size*scale};
}

function createCaptureQuality({core,cls,invokeManaged}) {
    function begin(size,quality) {
        const plan=captureQualityPlan(size,quality),rtClass=core('RenderTexture'),destroy=core('Object').method('DestroyImmediate',1);
        const active=rtClass.method('get_active').invoke(),owned=[];let texture=null;
        const started=Date.now();
        function dispose(){
            rtClass.method('set_active').invoke(active);
            if(texture){destroy.invoke(texture);texture=null;}
            for(const rt of owned.splice(0).reverse()){rt.method('Release').invoke();destroy.invoke(rt);}
        }
        function single(side,depth=0){
            const rt=rtClass.alloc();owned.push(rt);rt.method('.ctor',3).invoke(side,side,depth);rt.method('set_name').invoke(Il2Cpp.string('MCP capture RT'));
            if(!rt.method('Create').invoke())throw Error('CAPTURE_TEXTURE_CREATE_FAILED');return rt;
        }
        try{
            // This supported build has a get-only RT antiAliasing property.
            // Rebuild through its descriptor, as the upstream implementation does.
            let target=single(plan.render_size,24);
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
            if(target.method('get_width').invoke()!==plan.render_size||target.method('get_height').invoke()!==plan.render_size)
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
                    if(actual>1){read=single(plan.render_size);core('Graphics').method('Blit').overload('UnityEngine.Texture','UnityEngine.RenderTexture').invoke(target,read);read.method('set_filterMode').invoke(1);}
                    if(plan.render_size!==size){const output=single(size);core('Graphics').method('Blit').overload('UnityEngine.Texture','UnityEngine.RenderTexture').invoke(read,output);read=output;}
                    rtClass.method('set_active').invoke(read);
                    texture=core('Texture2D').alloc();texture.method('.ctor',2).invoke(size,size);
                    texture.method('set_name').invoke(Il2Cpp.string('MCP capture readback'));
                    const rect=core('Rect').alloc().unbox();rect.method('.ctor',4).invoke(0,0,size,size);
                    texture.method('ReadPixels',4).invoke(rect,0,0,false);texture.method('Apply',2).invoke(false,false);
                    const bytes=cls('UnityEngine.ImageConversionModule','UnityEngine.ImageConversion').method('EncodeToPNG',1).invoke(texture);
                    metadata.render_and_encode_ms=Date.now()-started;
                    return Il2Cpp.corlib.class('System.Convert').method('ToBase64String').overload('System.Byte[]').invoke(bytes).content;
                },dispose};
        }catch(error){dispose();throw error;}
    }
    return {begin};
}
