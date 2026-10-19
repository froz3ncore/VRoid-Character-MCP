// Regional/angle organization adapted from brainrom/vroid-studio-mcp Camera.cs.
// MIT attribution: vroid_mcp/data/capture_framing/NOTICE.
const captureRegions={body:[.50,1],face:[.91,.24/.86],head:[.90,.33/.86],
    upper:[.72,.58/.86],legs:[.33,.62/.86],feet:[.11,.28/.86]};
// Observer sides when looking at the model from +Z. Front camera's right is -X.
const captureAngles={front:0,back:180,left:90,right:-90,three_quarter_left:45,three_quarter_right:-45};
function parseCaptureView(view,wear=false){
    const old=wear?['front','side','back','three_quarter']:
        ['front','side','back','three_quarter','full_front','full_side','full_back','full_three_quarter','photo'];
    if(old.includes(view))return {view,regional:false};
    if(typeof view==='string')for(const region of Object.keys(captureRegions)){
        const prefix=region+'_';if(!view.startsWith(prefix))continue;
        const angle=view.slice(prefix.length);
        if(Object.hasOwn(captureAngles,angle))return {view,regional:true,region,angle,yaw_degrees:captureAngles[angle]};
    }
    throw Error('UNSUPPORTED_CAPTURE_VIEW: '+view);
}
function validateFramingBounds(bounds){
    if(!bounds||!Array.isArray(bounds.min)||!Array.isArray(bounds.max)||bounds.min.length!==3||bounds.max.length!==3
        ||![...bounds.min,...bounds.max].every(Number.isFinite)||bounds.min.some((v,i)=>bounds.max[i]<=v)
        ||bounds.max[1]-bounds.min[1]<.1)throw Error('INVALID_CAPTURE_FRAMING_BOUNDS');
    return bounds;
}
function regionalCameraPlan(bounds,parsed){
    validateFramingBounds(bounds);
    if(!parsed.regional)throw Error('REGIONAL_VIEW_REQUIRED');
    const [fraction,zoom]=captureRegions[parsed.region],lo=bounds.min,hi=bounds.max;
    const c=lo.map((v,i)=>(v+hi[i])/2),ex=lo.map((v,i)=>(hi[i]-v)/2),rad=parsed.yaw_degrees*Math.PI/180;
    const snap=v=>Math.abs(v)<1e-12?0:v,dx=snap(Math.sin(rad)),dz=snap(Math.cos(rad));
    const width=Math.abs(dz)*ex[0]+Math.abs(dx)*ex[2],depth=Math.abs(dx)*ex[0]+Math.abs(dz)*ex[2];
    // Fit the actual scoped body box, including perspective depth, before
    // applying the relative regional zoom. Mirror angles have equal distance.
    const distance=(depth+Math.max(width,ex[1])*1.16/Math.tan(Math.PI/12))*zoom;
    const target=[c[0],lo[1]+fraction*(hi[1]-lo[1]),c[2]];
    return {schema:'vroid-regional-framing-v1',view:parsed.view,region:parsed.region,angle:parsed.angle,
        angle_reference:'observer_from_front',yaw_degrees:parsed.yaw_degrees,source_bounds:bounds,
        center_fraction:fraction,relative_distance:zoom,fov_degrees:30,distance,
        target,position:[target[0]+dx*distance,target[1],target[2]+dz*distance]};
}
function createCaptureFraming({core,text}){
    const xyz=v=>['x','y','z'].map(k=>v.field(k).value);
    function bounds(renderers){
        let lo=null,hi=null,count=0;
        for(const r of renderers){
            const b=r.method('get_bounds').invoke(),c=xyz(b.method('get_center').invoke()),ex=xyz(b.method('get_extents').invoke());
            if(![...c,...ex].every(Number.isFinite)||ex.some(v=>v<0))throw Error('NONFINITE_CAPTURE_RENDERER_BOUNDS');
            if(ex.every(v=>v===0))continue;count++;
            const lower=c.map((v,i)=>v-ex[i]),upper=c.map((v,i)=>v+ex[i]);
            if(!lo){lo=lower;hi=upper;}else for(let i=0;i<3;i++){lo[i]=Math.min(lo[i],lower[i]);hi[i]=Math.max(hi[i],upper[i]);}
        }
        const result={min:lo,max:hi};validateFramingBounds(result);return {bounds:result,renderer_count:count};
    }
    function modelRoot(m){
        const root=m.face.method('GetFaceSMR').invoke().method('get_transform').invoke().method('get_parent').invoke();
        if(text(root.method('get_name').invoke())!=='CurrentModelOrigin')throw Error('UNEXPECTED_CAPTURE_MODEL_ROOT');return root;
    }
    function reference(m){
        const root=modelRoot(m),renderers=[];let nodes=0;
        function walk(t,depth){
            if(depth>32||++nodes>4096)throw Error('CAPTURE_MODEL_HIERARCHY_LIMIT');
            const go=t.method('get_gameObject').invoke();
            if(!go.method('get_activeInHierarchy').invoke())return;
            const r=go.method('GetComponent',1).overload('System.Type').invoke(core('SkinnedMeshRenderer').type.object);
            if(!r.handle.isNull())renderers.push(r);
            for(let i=0;i<t.method('get_childCount').invoke();i++)walk(t.method('GetChild').invoke(i),depth+1);
        }
        walk(root,0);
        return {model_token:m.token,root_id:root.handle.toString(),reference_frame:state.frame,...bounds(renderers)};
    }
    function modelPlan(m,parsed,fixed){
        const ref=fixed||reference(m);
        if(ref.model_token!==m.token||ref.root_id!==modelRoot(m).handle.toString())throw Error('STALE_CAPTURE_FRAMING_REFERENCE');
        return {...regionalCameraPlan(ref.bounds,parsed),reference_frame:ref.reference_frame,source_root_id:ref.root_id,source_renderer_count:ref.renderer_count};
    }
    function readback(cam,plan){
        const t=cam.method('get_transform').invoke(),p=xyz(t.method('get_position').invoke()),q=t.method('get_rotation').invoke();
        const [x,y,z,w]=['x','y','z','w'].map(k=>q.field(k).value),fov=cam.method('get_fieldOfView').invoke();
        const forward=[2*(x*z+w*y),2*(y*z-w*x),1-2*(x*x+y*y)];
        const intended=plan.target.map((v,i)=>(v-plan.position[i])/plan.distance);
        if(![...p,...forward,fov].every(Number.isFinite)||p.some((v,i)=>Math.abs(v-plan.position[i])>1e-4*Math.max(1,plan.distance))
            ||forward.some((v,i)=>Math.abs(v-intended[i])>1e-4)||Math.abs(fov-30)>1e-4)
            throw Error('CAPTURE_CAMERA_READBACK_MISMATCH');
        return {...plan,position:p,forward,right_vector:[1-2*(y*y+z*z),2*(x*y+w*z),2*(x*z-w*y)],
            fov_degrees:fov,camera_readback_verified:true};
    }
    return {bounds,reference,modelPlan,readback};
}
