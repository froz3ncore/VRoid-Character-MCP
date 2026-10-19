// Read-only avatar geometry/skin snapshot for fitting, not a VRM export.
function createBodyReferenceApi({model,cls,core,text,invokeManaged}) {
    const names=['Body','Hand','Foot','Head','Face','Ear','EyeExtra'];
    function matrix(t){const m=t.method('get_localToWorldMatrix').invoke();return Array.from({length:4},(_,r)=>Array.from({length:4},(_,c)=>m.field('m'+r+c).value));}
    function xyz(v){return ['x','y','z'].map(k=>v.field(k).value);}
    return {operations:{capture_body_reference(args){
        if(!args.expected_model)throw Error('EXPECTED_MODEL_REQUIRED');
        const m=model(args.expected_model);
        if(m.root.field('obsoleteLegacyPhotoBoothViewModel').value.method('get_IsActive').invoke())throw Error('RETURN_TO_EDIT_MODE');
        if(m.main.field('_editModelTransform').value.method('get_IsUpdatingModel').invoke())throw Error('MODEL_UPDATING');
        const face=m.face.method('GetFaceSMR').invoke();
        const origin=face.method('get_transform').invoke().method('get_parent').invoke();
        if(text(origin.method('get_name').invoke())!=='CurrentModelOrigin')throw Error('UNEXPECTED_AVATAR_ROOT');
        const nodes=[],byAddress=new Map(),renderers=[];
        function walk(t,parent,path,depth){
            if(depth>32||nodes.length>4096)throw Error('SKELETON_LIMIT');
            const name=text(t.method('get_name').invoke());
            const id=nodes.length;byAddress.set(t.handle.toString(),id);
            nodes.push({id,parent,name,path:path+'/'+name,world_matrix:matrix(t)});
            if(names.includes(name)){
                const go=t.method('get_gameObject').invoke();
                const smr=go.method('GetComponent',1).overload('System.Type').invoke(core('SkinnedMeshRenderer').type.object);
                if(!smr.handle.isNull())renderers.push({id,name,smr,t});
            }
            for(let i=0;i<t.method('get_childCount').invoke();i++)walk(t.method('GetChild').invoke(i),id,path+'/'+name,depth+1);
        }
        walk(origin,null,'',0);
        if(!['Body','Hand','Foot','Face'].every(name=>renderers.some(r=>r.name===name)))throw Error('MISSING_BODY_RENDERER');
        const meshes=[];
        for(const {id,name,smr,t} of renderers){
            const source=smr.method('get_sharedMesh').invoke();
            const count=source.method('get_vertexCount').invoke();
            if(count>100000)throw Error('MESH_LIMIT');
            let baked=null;
            try{
                baked=core('Mesh').alloc();baked.method('.ctor').invoke();
                smr.method('BakeMesh',1).invoke(baked);
                const positions=[...baked.method('get_vertices').invoke()].map(xyz);
                const uv0=[...source.method('get_uv').invoke()].map(v=>['x','y'].map(k=>v.field(k).value));
                const weights=[...source.method('get_boneWeights').invoke()].map(v=>{
                    const fields=new Set(v.type.class.fields.map(f=>f.name));
                    function field(k){return v.field(fields.has(k)?k:'m_'+k[0].toUpperCase()+k.slice(1)).value;}
                    return {indices:[0,1,2,3].map(i=>field('boneIndex'+i)),weights:[0,1,2,3].map(i=>field('weight'+i))};
                });
                const bones=[...smr.method('get_bones').invoke()].map(b=>{
                    const mapped=byAddress.get(b.handle.toString());if(mapped===undefined)throw Error('BONE_OUTSIDE_AVATAR');return mapped;});
                const triangles=[...source.method('get_triangles').invoke()];
                if(positions.length!==count||weights.length!==count)throw Error('VERTEX_COUNT_MISMATCH');
                meshes.push({name,node_id:id,world_matrix:matrix(t),positions,uv0,triangles,bone_nodes:bones,weights,
                    position_state:'BakeMesh current edit pose; not original undeformed bind vertices'});
            }finally{if(baked)core('Object').method('DestroyImmediate',1).invoke(baked);}
        }
        // Retain only body skin bones and their ancestry; do not leak the unrelated hair graph.
        const keep=new Set([0]);
        for(const mesh of meshes)for(const id of [mesh.node_id,...mesh.bone_nodes]){
            for(let i=id;i!==null;i=nodes[i].parent)keep.add(i);
        }
        return {schema:'vroid-body-reference-v1',model_token:m.token,frame:state.frame,
            unity:Il2Cpp.unityVersion,vroid_version:'2.14.0',coordinate_system:'Unity left-handed, +Y up, +Z character front; row-major matrices',
            height_cm:m.root.method('get_BodyEditor').invoke().method('get_BodyHeight').invoke().method('GetBodyHeight').invoke()*100,
            nodes:nodes.filter(n=>keep.has(n.id)),meshes,scope:'Body/face geometry and skin reference; no textures, expressions, clothing, hair or VRM metadata; not a playable avatar'};
    }}};
}
