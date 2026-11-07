// Regional/angle organization adapted from brainrom/vroid-studio-mcp Camera.cs.
// MIT attribution: vroid_mcp/data/capture_framing/NOTICE.
const captureRegions={body:[.50,1],face:[.91,.24/.86],head:[.90,.33/.86],
    upper:[.72,.58/.86],legs:[.33,.62/.86],feet:[.11,.28/.86]};
// Observer sides when looking at the model from +Z. Front camera's right is -X.
const captureAngles={front:0,back:180,left:90,right:-90,three_quarter_left:45,three_quarter_right:-45};
function captureModelOwnership(m,text){return {engine_id:m.engine.handle.toString(),file_path:text(m.file.field('path').value)};}
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
function regionalCameraPlan(bounds,parsed,aspect=1){
    validateFramingBounds(bounds);
    if(!parsed.regional)throw Error('REGIONAL_VIEW_REQUIRED');
    const [fraction,zoom]=captureRegions[parsed.region],lo=bounds.min,hi=bounds.max;
    const c=lo.map((v,i)=>(v+hi[i])/2),ex=lo.map((v,i)=>(hi[i]-v)/2),rad=parsed.yaw_degrees*Math.PI/180;
    const snap=v=>Math.abs(v)<1e-12?0:v,dx=snap(Math.sin(rad)),dz=snap(Math.cos(rad));
    const width=Math.abs(dz)*ex[0]+Math.abs(dx)*ex[2],depth=Math.abs(dx)*ex[0]+Math.abs(dz)*ex[2];
    // Fit the actual scoped body box, including perspective depth, before
    // applying the relative regional zoom. Mirror angles have equal distance.
    if(!Number.isFinite(aspect)||aspect<=0)throw Error('INVALID_CAPTURE_ASPECT');
    const distance=(depth+Math.max(width/aspect,ex[1])*1.16/Math.tan(Math.PI/12))*zoom;
    const target=[c[0],lo[1]+fraction*(hi[1]-lo[1]),c[2]];
    return {schema:'vroid-regional-framing-v1',view:parsed.view,region:parsed.region,angle:parsed.angle,
        angle_reference:'observer_from_front',yaw_degrees:parsed.yaw_degrees,source_bounds:bounds,
        center_fraction:fraction,relative_distance:zoom,fov_degrees:30,aspect,distance,
        target,position:[target[0]+dx*distance,target[1],target[2]+dz*distance]};
}
// Source region-span convention adapted from mcjo79 vroid_mcp.py frame_region
// at 0dc7d5e (MIT; licenses/mcjo79-0dc7d5e.txt). Numeric half, translated
// bounds and perspective containment deliberately strengthen source semantics.
function situationCameraPlan(bounds,profile,aspect=1){
    validateFramingBounds(bounds);
    if(!profile||!['top','bottom','distance','yaw'].every(k=>Number.isFinite(profile[k]))
        ||profile.top<0||profile.top>=profile.bottom||profile.bottom>1||profile.distance<.1||profile.distance>100
        ||Math.abs(profile.yaw)>360||profile.half!==null&&(!Number.isFinite(profile.half)||profile.half<=0||profile.half>1)
        ||!['region','full-body'].includes(profile.fit)||!Number.isFinite(aspect)||aspect<=0)throw Error('INVALID_SITUATION_FRAMING');
    const lo=bounds.min,hi=bounds.max,H=hi[1]-lo[1],c=lo.map((v,i)=>(v+hi[i])/2),ex=lo.map((v,i)=>(hi[i]-v)/2);
    const angle=profile.yaw*Math.PI/180,dx=Math.sin(angle),dz=Math.cos(angle),full=profile.fit==='full-body';
    const top=full?hi[1]:hi[1]-profile.top*H,bottom=full?lo[1]:hi[1]-profile.bottom*H;
    const target=[c[0],(top+bottom)/2,c[2]],width=full||profile.half===null?
        Math.abs(dz)*ex[0]+Math.abs(dx)*ex[2]:profile.half*H;
    const depth=Math.abs(dx)*ex[0]+Math.abs(dz)*ex[2],span=Math.max(top-bottom,.14*H)*1.1;
    const requested=profile.distance*span,required=depth+Math.max(width/aspect,(top-bottom)/2)/Math.tan(Math.PI/12);
    // Tiny padding avoids boundary roundoff; all corners remain in front of the
    // near plane even when a caller requests a very small span multiplier.
    const distance=Math.max(requested,required*1.000001,depth+.02);
    return {schema:'vroid-situation-framing-v1',requested_profile:JSON.parse(JSON.stringify(profile)),
        source_bounds:bounds,yaw_degrees:profile.yaw,fit:profile.fit,
        inactive_fields:full?['top','bottom','half']:[],region_world_top:top,region_world_bottom:bottom,
        effective_half_width:width,source_span:span,source_span_policy:'max(region span, .14*model height)*1.1',
        requested_distance_multiplier:profile.distance,effective_distance_multiplier:distance/span,
        requested_distance:requested,distance,distance_adjusted:distance>requested,
        adjustment_reason:distance>requested?'perspective region containment including model depth':null,
        fov_degrees:30,aspect,near_clip:.01,far_clip:Math.max(1000,distance+depth+H+1),target,
        position:[target[0]+dx*distance,target[1],target[2]+dz*distance]};
}
function situationProjection(plan){
    const f=1/Math.tan(plan.fov_degrees*Math.PI/360),n=plan.near_clip,a=plan.far_clip;
    if(![f,n,a,plan.aspect].every(Number.isFinite)||n<=0||a<=n||plan.aspect<=0)throw Error('SITUATION_INVALID_CLIPS');
    return [f/plan.aspect,0,0,0,0,f,0,0,0,0,-(a+n)/(a-n),-2*a*n/(a-n),0,0,-1,0];
}
function verifySituationOptics(actual,plan){
    const matrix=actual.projection_matrix,expected=situationProjection(plan),near=(a,b)=>Math.abs(a-b)<=1e-4*Math.max(1,Math.abs(b));
    if(actual.projection!=='perspective'||!Array.isArray(matrix)||matrix.length!==16||!matrix.every(Number.isFinite)
        ||matrix.some((v,i)=>!near(v,expected[i]))||![actual.near_clip,actual.far_clip].every(Number.isFinite)
        ||!near(actual.near_clip,plan.near_clip)||!near(actual.far_clip,plan.far_clip))throw Error('SITUATION_OPTICAL_READBACK_MISMATCH');
    const rad=plan.yaw_degrees*Math.PI/180;
    for(const [key,want] of [['forward',[-Math.sin(rad),0,-Math.cos(rad)]],['right_vector',[-Math.cos(rad),0,Math.sin(rad)]],['up_vector',[0,1,0]]])
        if(actual[key].some((v,i)=>!Number.isFinite(v)||!near(v,want[i])))throw Error('SITUATION_ORIENTATION_READBACK_MISMATCH');
    const lo=plan.source_bounds.min,hi=plan.source_bounds.max,points=[];
    if(plan.fit==='full-body'){
        for(const x of [lo[0],hi[0]])for(const y of [lo[1],hi[1]])for(const z of [lo[2],hi[2]])points.push([x,y,z]);
    }else{
        const rad=plan.yaw_degrees*Math.PI/180,n=[Math.sin(rad),0,Math.cos(rad)],r=[-n[2],0,n[0]],
            depth=Math.abs(n[0])*(hi[0]-lo[0])/2+Math.abs(n[2])*(hi[2]-lo[2])/2;
        for(const x of [-plan.effective_half_width,plan.effective_half_width])for(const y of [plan.region_world_bottom,plan.region_world_top])
            for(const z of [-depth,depth])points.push(plan.target.map((v,i)=>v+r[i]*x+n[i]*z+(i===1?y-v:0)));
    }
    for(const point of points){
        const rel=point.map((v,i)=>v-actual.position[i]);
        const v=['right_vector','up_vector','forward'].map(k=>rel.reduce((s,x,i)=>s+x*actual[k][i],0));
        if(!(v[2]>actual.near_clip&&v[2]<actual.far_clip))throw Error('SITUATION_CLIPPED_CORNER');
        const camera=[v[0],v[1],-v[2],1],clip=Array.from({length:4},(_,i)=>camera.reduce((s,x,j)=>s+matrix[i*4+j]*x,0));
        if(!(clip[3]>0)||clip.slice(0,3).some(x=>Math.abs(x/clip[3])>1.0001))throw Error('SITUATION_CLIPPED_CORNER');
    }
    return {...actual,projection_verified:true,containment_verified:true};
}
function createCaptureFraming({core,text,cls=null}){
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
        const root=m.main.method('get_GlobalBus').invoke().method('get_ModelOrigin').invoke();
        if(!root||root.handle.isNull())throw Error('UNEXPECTED_CAPTURE_MODEL_ROOT');
        let t=m.face.method('GetFaceSMR').invoke().method('get_transform').invoke(),found=false;
        for(let i=0;i<64&&t&&!t.handle.isNull();i++,t=t.method('get_parent').invoke())
            if(t.handle.toString()===root.handle.toString()){found=true;break;}
        if(!found)throw Error('CAPTURE_FACE_OUTSIDE_MODEL_ROOT');return root;
    }
    function reference(m){
        const root=modelRoot(m),renderers=[],animators=[],owned=new Set();let nodes=0,animatorAvailable=!!cls;
        function walk(t,depth){
            if(depth>32||++nodes>4096)throw Error('CAPTURE_MODEL_HIERARCHY_LIMIT');
            const go=t.method('get_gameObject').invoke();
            if(!go.method('get_activeInHierarchy').invoke())return;
            owned.add(t.handle.toString());
            const r=go.method('GetComponent',1).overload('System.Type').invoke(core('Renderer').type.object);
            if(!r.handle.isNull()&&r.method('get_enabled').invoke())renderers.push(r);
            if(animatorAvailable)try{
                const a=go.method('GetComponent',1).overload('System.Type').invoke(cls('UnityEngine.AnimationModule','UnityEngine.Animator').type.object);
                if(!a.handle.isNull()&&a.method('get_isHuman').invoke())animators.push(a);
            }catch(_){animatorAvailable=false;}
            for(let i=0;i<t.method('get_childCount').invoke();i++)walk(t.method('GetChild').invoke(i),depth+1);
        }
        walk(root,0);
        const geometry=bounds(renderers),b=geometry.bounds,H=b.max[1]-b.min[1],landmarks={};
        for(const name of ['Head','LeftFoot']){
            landmarks[name]={available:false,world_y:null,reason:'missing or ambiguous scoped humanoid animator'};
            if(animatorAvailable&&animators.length===1)try{
                const value=cls('UnityEngine.AnimationModule','UnityEngine.HumanBodyBones').field(name).value;
                const bone=animators[0].method('GetBoneTransform').invoke(value);
                if(!bone||bone.handle.isNull()||!owned.has(bone.handle.toString()))throw Error('BONE_OUTSIDE_OWNED_ACTIVE_HIERARCHY');
                const y=xyz(bone.method('get_position').invoke())[1];if(!Number.isFinite(y))throw Error('NONFINITE_BONE');
                landmarks[name]={available:true,world_y:y,transform_id:bone.handle.toString()};
            }catch(error){landmarks[name].reason=String(error);}
        }
        if(modelRoot(m).handle.toString()!==root.handle.toString())throw Error('CAPTURE_MODEL_ROOT_CHANGED');
        return {model_token:m.token,root_id:root.handle.toString(),reference_frame:state.frame,...geometry,
            horizontal_center:[(b.min[0]+b.max[0])/2,(b.min[2]+b.max[2])/2],vertical_span_m:H,
            renderer_extent_cm:H*100,source_grounded_max_y_cm:b.max[1]*100,
            height_conventions:{renderer_extent:'maxY-minY',source_grounded_nominal:'maxY*100; ground-dependent, not extent'},landmarks};
    }
    function modelPlan(m,parsed,fixed,aspect=1){
        const ref=fixed||reference(m);
        if(ref.model_token!==m.token||ref.root_id!==modelRoot(m).handle.toString())throw Error('STALE_CAPTURE_FRAMING_REFERENCE');
        return {...regionalCameraPlan(ref.bounds,parsed,aspect),reference_frame:ref.reference_frame,source_root_id:ref.root_id,source_renderer_count:ref.renderer_count};
    }
    function situationPlan(m,profile,aspect=1){const ref=reference(m);
        return {...situationCameraPlan(ref.bounds,profile,aspect),reference_frame:ref.reference_frame,
            source_root_id:ref.root_id,source_renderer_count:ref.renderer_count};}
    function readback(cam,plan){
        const t=cam.method('get_transform').invoke(),p=xyz(t.method('get_position').invoke()),q=t.method('get_rotation').invoke();
        const [x,y,z,w]=['x','y','z','w'].map(k=>q.field(k).value),fov=cam.method('get_fieldOfView').invoke();
        const forward=[2*(x*z+w*y),2*(y*z-w*x),1-2*(x*x+y*y)];
        const intended=plan.target.map((v,i)=>(v-plan.position[i])/plan.distance);
        if(![...p,...forward,fov].every(Number.isFinite)||p.some((v,i)=>Math.abs(v-plan.position[i])>1e-4*Math.max(1,plan.distance))
            ||forward.some((v,i)=>Math.abs(v-intended[i])>1e-4)||Math.abs(fov-30)>1e-4)
            throw Error('CAPTURE_CAMERA_READBACK_MISMATCH');
        const result={...plan,position:p,forward,right_vector:[1-2*(y*y+z*z),2*(x*y+w*z),2*(x*z-w*y)],
            up_vector:[2*(x*y-w*z),1-2*(x*x+z*z),2*(y*z+w*x)],
            fov_degrees:fov,camera_readback_verified:true};
        if(plan.schema!=='vroid-situation-framing-v1')return result;
        const matrix=cam.method('get_projectionMatrix').invoke();
        return verifySituationOptics({...result,projection:cam.method('get_orthographic').invoke()?'orthographic':'perspective',
            projection_matrix:Array.from({length:16},(_,i)=>matrix.field('m'+Math.floor(i/4)+i%4).value),
            near_clip:cam.method('get_nearClipPlane').invoke(),far_clip:cam.method('get_farClipPlane').invoke()},plan);
    }
    return {bounds,reference,modelPlan,situationPlan,readback};
}
