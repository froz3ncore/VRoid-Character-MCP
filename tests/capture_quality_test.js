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
            if(name==='.ctor'){o.side=args[0];return;}
            if(name==='Create'){creates++;if(options.failCreate===creates)throw Error('CREATE_FAILED');return true;}
            if(name==='get_descriptor')return {handle:null,field:()=>({set value(v){this.samples=v;descriptorSamples=v;}})};
            if(name==='get_antiAliasing')return o.msaa;
            if(name==='get_width'||name==='get_height')return o.side;
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
            if(name==='Blit'){blits.push([args[0].msaa,args[1].msaa]);active=args[1];return;}
        }})};}
    const cls=()=>({method:()=>({invoke:()=>({})})});
    const invokeManaged=(o,name)=>{assert.equal(name,'.ctor');o.msaa=options.gpuSamples||descriptorSamples;o.side=[...live].find(x=>x!==o&&x.type==='RenderTexture').side;};
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
console.log('Capture quality GPU ownership regression passed (9 scenarios)');
