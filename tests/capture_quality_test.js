// Exercise ownership on success, GPU downgrade, allocation failure and readback failure.
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
vm.runInThisContext(fs.readFileSync('agent/capture_quality.js','utf8'));
global.Il2Cpp={string:s=>s,corlib:{class:()=>({method:()=>({overload:()=>({invoke:()=>({content:'png'})})})})}};
function native(options={}){
    const live=new Set(),old={},blits=[];let active=old,creates=0;
    function object(type){
        const o={type,msaa:1,handle:null};o.handle=o;
        if(type==='RenderTexture'||type==='Texture2D')live.add(o);
        o.method=(name)=>({invoke(...args){
            if(name==='.ctor'){o.side=args[0];o.height=args[1];return;}
            if(name==='Create'){creates++;if(options.failCreate===creates)throw Error('CREATE_FAILED');return true;}
            if(name==='get_descriptor')return {handle:null,field:()=>({set value(v){this.samples=v;descriptorSamples=v;}})};
            if(name==='get_antiAliasing')return o.msaa;
            if(name==='get_width')return o.side;
            if(name==='get_height')return o.height;
            if(name==='ReadPixels'&&options.failRead)throw Error('READ_FAILED');
            if(name==='ReadPixels')assert.equal(active.msaa,1,'CPU read requires single-sample texture');
            if(name==='Release')o.released=true;
        }});return o;
    }
    let descriptorSamples=1;
    function core(type){return {alloc:()=>{const o=object(type);o.unbox=()=>o;return o;},method:name=>({
        overload(){return this;},invoke(...args){
            if(name==='get_active')return active;
            if(name==='set_active'){active=args[0];return;}
            if(name==='DestroyImmediate'){if(args[0].type==='RenderTexture')assert(args[0].released);live.delete(args[0]);return;}
            if(name==='Blit'){if(options.failBlit)throw Error('BLIT_FAILED');blits.push([args[0].msaa,args[1].msaa]);active=args[1];return;}
        }})};}
    const cls=()=>({method:()=>({invoke:()=>{if(options.failEncode)throw Error('ENCODE_FAILED');return {};}})});
    const invokeManaged=(o,name)=>{assert.equal(name,'.ctor');o.msaa=options.gpuSamples||descriptorSamples;const source=[...live].find(x=>x!==o&&x.type==='RenderTexture');o.side=source.side;o.height=source.height;};
    return {api:createCaptureQuality({core,cls,invokeManaged}),live,blits,old,get active(){return active;}};
}
for(const quality of ['legacy','balanced','high']){
    const n=native(),capture=n.api.begin(768,quality);
    assert.equal(capture.metadata.msaa_samples,quality==='legacy'?1:4);
    assert.equal(capture.encode(),'png');capture.dispose();capture.dispose();
    assert.equal(n.live.size,0);assert.equal(n.active,n.old);
    assert.equal(n.blits.length,quality==='high'?2:quality==='balanced'?1:0);
}
{
    const n=native({gpuSamples:2}),c=n.api.begin(512,'high');
    assert(c.metadata.hardware_downgrade);assert.equal(c.metadata.msaa_samples,2);c.dispose();assert.equal(n.live.size,0);
}
for(const failCreate of [1,2]){
    const n=native({failCreate});assert.throws(()=>n.api.begin(512,'high'),/CREATE_FAILED/);
    assert.equal(n.live.size,0);assert.equal(n.active,n.old);
}
{
    const n=native({failRead:true}),c=n.api.begin(512,'high');
    try{assert.throws(()=>c.encode(),/READ_FAILED/);}finally{c.dispose();}
    assert.equal(n.live.size,0);assert.equal(n.active,n.old);
}
assert.equal(captureQualityPlan(2048,'high').render_size,2828);
assert.throws(()=>captureQualityPlan(512,'invalid'),/UNSUPPORTED_CAPTURE_QUALITY/);
for(const [width,height] of [[640,1024],[1024,640]]){
    const n=native({gpuSamples:2}),c=n.api.begin(512,'balanced',{width,height,msaa:4,ssaa:3});
    assert.equal(c.target.side,width*3);assert.equal(c.target.height,height*3);
    assert.equal(c.metadata.output_width,width);assert.equal(c.metadata.output_height,height);assert(c.metadata.hardware_downgrade);
    assert.equal(c.encode(),'png');c.dispose();assert.equal(n.live.size,0);assert.equal(n.active,n.old);
}
for(const options of [{width:640},{width:640,height:2049},{msaa:8},{ssaa:4},{msaa:true},{ssaa:NaN}])assert.throws(()=>captureQualityPlan(512,'balanced',options));
const rectangular=captureQualityPlan(512,'high',{width:2048,height:1536,ssaa:3});
assert(rectangular.render_width*rectangular.render_height<=8000000);assert(Math.abs(rectangular.effective_scale_x-rectangular.effective_scale_y)<.001);
for(const options of [{failBlit:true},{failEncode:true}]){
    const n=native(options),c=n.api.begin(512,'high',{width:640,height:1024});
    try{assert.throws(()=>c.encode(),/FAILED/);}finally{c.dispose();}
    assert.equal(n.live.size,0);assert.equal(n.active,n.old);
}
console.log('Capture quality GPU ownership regression passed (9 scenarios)');
