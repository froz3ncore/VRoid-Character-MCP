// Exact current-editor framing, reusable by catalog/situation captures.
function captureProjectionValues(camera){
    const matrix=camera.method('get_projectionMatrix').invoke();
    return Array.from({length:16},(_,i)=>matrix.field('m'+Math.floor(i/4)+i%4).value);
}
function writeCaptureProjection(core,camera,values){
    if(!Array.isArray(values)||values.length!==16||!values.every(Number.isFinite))throw Error('INVALID_CAPTURE_PROJECTION');
    const matrix=core('Matrix4x4').alloc().unbox();
    values.forEach((v,i)=>{matrix.field('m'+Math.floor(i/4)+i%4).value=v;});
    camera.method('set_projectionMatrix').invoke(matrix);
}
function captureProjectionMetadata({matrix,...metadata}){return metadata;}
function expandCaptureProjection(source,sourceAspect,plan){
    if(!Array.isArray(source)||source.length!==16||!source.every(Number.isFinite)||!Number.isFinite(sourceAspect)||sourceAspect<=0)throw Error('INVALID_SOURCE_PROJECTION');
    const outputAspect=plan.output_width/plan.output_height;
    const sx=Math.min(1,sourceAspect/outputAspect),sy=Math.min(1,outputAspect/sourceAspect);
    return {matrix:source.map((v,i)=>v*(i<4?sx:i<8?sy:1)),source_projection_matrix:[...source],
        projection_policy:'contain_source_frustum_expand_without_crop',clip_scale:[sx,sy],source_aspect:sourceAspect,
        output_aspect:outputAspect,render_target_aspect:plan.render_width/plan.render_height,
        render_viewport:[0,0,plan.render_width,plan.render_height],
        output_resample_scale:[plan.output_width/plan.render_width,plan.output_height/plan.render_height]};
}
function createEditorCapture({core,preview,quality}){
    const vector=(v,n)=>['x','y','z','w'].slice(0,n).map(k=>v.field(k).value);
    function snapshot(camera){const transform=camera.method('get_transform').invoke();
        const result={render_position:vector(transform.method('get_position').invoke(),3),
            render_rotation:vector(transform.method('get_rotation').invoke(),4),
            projection_matrix:captureProjectionValues(camera),
            projection:camera.method('get_orthographic').invoke()?'orthographic':'perspective',
            source_aspect:camera.method('get_aspect').invoke(),fov_degrees:camera.method('get_fieldOfView').invoke(),
            orthographic_size:camera.method('get_orthographicSize').invoke()};
        if(![...result.render_position,...result.render_rotation,...result.projection_matrix,result.source_aspect,
            result.fov_degrees,result.orthographic_size].every(Number.isFinite))throw Error('NONFINITE_EDITOR_CAMERA_STATE');
        return result;
    }
    return function render(args){
        const plan=captureQualityPlan(args.size===undefined?512:args.size,args.quality,args);
        const owner=preview.verify(args.expected_model),source=owner.camera,before=snapshot(source);
        if(preview.adapter.cameraState(owner).rotating)throw Error('EDITOR_CAMERA_ROTATION_PENDING');
        let holder=null,capture=null;
        try{
            holder=core('GameObject').alloc();holder.method('.ctor',1).invoke(Il2Cpp.string('MCP live editor capture'));
            const camera=holder.method('AddComponent',1).invoke(core('Camera').type.object);
            camera.method('CopyFrom').invoke(source);camera.method('set_enabled').invoke(false);
            const sourceTransform=source.method('get_transform').invoke(),target=camera.method('get_transform').invoke();
            target.method('set_position').invoke(sourceTransform.method('get_position').invoke());
            target.method('set_rotation').invoke(sourceTransform.method('get_rotation').invoke());
            capture=quality.begin(args.size===undefined?512:args.size,args.quality,args);
            camera.method('set_allowMSAA').invoke(true);camera.method('set_targetTexture').invoke(capture.target);
            // Camera.targetTexture uses the entire RT; Unity ignores rect and
            // pixelRect here. Expand only the clone's optical projection so the
            // original frustum fits without crop or distorted subject proportions.
            // Scale to final pixel aspect, including per-axis SSAA cap resampling.
            const fit=expandCaptureProjection(before.projection_matrix,before.source_aspect,plan);
            writeCaptureProjection(core,camera,fit.matrix);
            const actual=snapshot(camera);
            for(const key of ['render_position','render_rotation'])
                if(actual[key].some((v,i)=>Math.abs(v-before[key][i])>1e-5*Math.max(1,Math.abs(v))))throw Error('LIVE_CAMERA_COPY_READBACK_MISMATCH');
            if(actual.projection_matrix.some((v,i)=>Math.abs(v-fit.matrix[i])>1e-5*Math.max(1,Math.abs(v))))throw Error('LIVE_CAMERA_PROJECTION_READBACK_MISMATCH');
            if(actual.projection!==before.projection)throw Error('LIVE_CAMERA_PROJECTION_READBACK_MISMATCH');
            preview.verify(args.expected_model);camera.method('Render').invoke();preview.verify(args.expected_model);
            if(JSON.stringify(snapshot(source))!==JSON.stringify(before))throw Error('LIVE_CAMERA_CHANGED_DURING_CAPTURE');
            return {model_token:owner.token,view:'current_editor',width:plan.output_width,height:plan.output_height,
                mime_type:'image/png',base64:capture.encode(),quality:capture.metadata,
                provenance:'clean_current_editor_render',projection:actual.projection,
                framing:{...preview.adapter.cameraState(owner),...actual,...captureProjectionMetadata(fit),
                    projection_property_scope:'native camera property getters; effective optics use projection_matrix',
                    camera_readback_verified:true,ui_visibility:'unchanged'}};
        }finally{captureCleanup([
            ()=>{if(holder)core('Object').method('DestroyImmediate',1).invoke(holder);},
            ()=>{if(capture)capture.dispose();},
        ]);}
    };
}
