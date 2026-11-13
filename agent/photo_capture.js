// Existing photo rendering retained, with a completed backup and mutation receipt.
function createPhotoCapture({core,quality,invokeManaged,model,cleanScope}){
    return function render(m,size,captureQuality,options={}){
        const photo=m.root.field('obsoleteLegacyPhotoBoothViewModel').value;
        if(!photo.method('get_IsActive').invoke())throw Error('PHOTO_MODE_REQUIRED');
        const camera=photo.method('get_PhotoBoothCamera').invoke(),scope=cleanScope.inspect(m);
        const sourcePixels=captureSourcePixels(camera),plan=captureQualityPlan(size,captureQuality,options);
        const projection=options.width!=null?expandCaptureProjection(captureProjectionValues(camera),sourcePixels.source_aspect,plan):null;
        const rt=core('RenderTexture'),previousActive=rt.method('get_active').invoke();
        const previousTarget=camera.method('get_targetTexture').invoke(),wasEnabled=camera.method('get_enabled').invoke();
        let backupObject=null,backup=null,backupComplete=false,liveTouched=false,capture=null;
        function owner(checkPresentation=true){
            const current=model(m.token),actual=current.root.field('obsoleteLegacyPhotoBoothViewModel').value;
            if(current.engine.handle.toString()!==m.engine.handle.toString()||current.root.handle.toString()!==m.root.handle.toString())throw Error('PHOTO_CAMERA_OWNER_CHANGED');
            if(actual.handle.toString()!==photo.handle.toString()||actual.method('get_PhotoBoothCamera').invoke().handle.toString()!==camera.handle.toString())throw Error('PHOTO_CAMERA_OWNER_CHANGED');
            if(checkPresentation)cleanScope.verify(m,scope);
        }
        try{
            backupObject=core('GameObject').alloc();backupObject.method('.ctor',1).invoke(Il2Cpp.string('MCP photo capture settings backup'));
            backup=backupObject.method('AddComponent',1).invoke(core('Camera').type.object);
            backup.method('CopyFrom').invoke(camera);backupComplete=true;
            backup.method('set_enabled').invoke(false);
            capture=quality.begin(size,captureQuality,options);owner();
            liveTouched=true;
            camera.method('set_allowMSAA').invoke(true);invokeManaged(camera,'set_targetTexture',[capture.target.handle]);
            cleanScope.apply(camera,scope);
            if(projection)writeCaptureProjection(core,camera,projection.matrix);
            invokeManaged(camera,'Render');owner();
            const base64=capture.encode();owner();
            return {model_token:m.token,view:'photo',width:plan.output_width,height:plan.output_height,mime_type:'image/png',
                base64,quality:capture.metadata,provenance:'clean_photo_camera_render',
                projection:camera.method('get_orthographic').invoke()?'orthographic':'perspective',
                framing:{...sourcePixels,...(projection?captureProjectionMetadata(projection):{}),
                    projection_matrix:captureProjectionValues(camera),source:'native_photo_camera',guide_scope:scope}};
        }finally{
            // A partial CopyFrom is never a valid rollback source. Ownership is
            // checked again before touching the live camera, never a replacement.
            let canRestore=false,ownershipError=null;
            if(backupComplete&&liveTouched)try{owner(false);canRestore=true;}catch(error){ownershipError=error;}
            captureCleanup([
                ()=>{if(canRestore)camera.method('CopyFrom').invoke(backup);},
                ()=>{if(canRestore)camera.method('set_enabled').invoke(wasEnabled);},
                ()=>{if(canRestore)invokeManaged(camera,'set_targetTexture',[previousTarget.handle]);},
                ()=>rt.method('set_active').invoke(previousActive),
                ()=>{if(backupObject)core('Object').method('DestroyImmediate',1).invoke(backupObject);},
                ()=>{if(capture)capture.dispose();},
                ()=>{if(ownershipError)throw ownershipError;},
            ]);
        }
    };
}
