// Binding-key extraction adapted from brainrom/vroid-studio-mcp (MIT), a6b0719.
// Copyright (c) 2026 Ilya Chelyadin and vroid-studio-mcp contributors.
// Full notice: vroid_mcp/data/parameter_labels/LICENSE and NOTICE.
globalThis.createParameterSemantics = ({text}) => {
    const layouts={
        BoneTransformParameterViewModel:[['value','_path']],
        BlendShapeTransformParameterViewModel:[['value','_path']],
        CombinedBoneTransformParameterViewModel:[['negative','_pathNegative'],['positive','_pathPositive']],
        CombinedBlendShapeTransformParameterViewModel:[['negative','_negativeBlendShapePath'],['positive','_positiveBlendShapePath']]
    };
    function field(o,name){try{return o.tryField(name)?.value??null;}catch(_){return null;}}
    function string(v){return typeof v==='string'?v:v instanceof Il2Cpp.String?text(v):null;}
    function bindingKey(path,depth=0){
        if(!path||path.handle.isNull()||depth>2)return null;
        const getter=path.tryMethod('get_Key',0);
        if(getter)return string(getter.invoke());
        // Clothing wraps the real editable key in TemplateContentPathBase<T>.
        return bindingKey(field(path,'editableElementPath'),depth+1);
    }
    function templateDescriptor(path){
        if(!path||path.handle.isNull())return null;
        const fields={};let c=path.class;
        for(let depth=0;c&&depth<4;depth++,c=c.parent){
            for(const f of c.fields||[]){
                if(f.isStatic)continue;
                const v=field(path,f.name),s=string(v);
                if(s!==null)fields[f.name]=s;
                else if(typeof v==='number'||typeof v==='boolean')fields[f.name]=v;
            }
        }
        return {type:path.class.name,fields};
    }
    function translationKey(o){
        try{
            const direct=o.tryMethod('get_TranslationKey',0);
            if(direct){const key=string(direct.invoke());if(key)return key;}
            // In this verified build the label delegate captures the exact message key.
            const translate=field(o,'_translateLabel');
            if(translate&&!translate.handle.isNull()){
                const target=translate.method('get_Target',0).invoke();
                if(target&&!target.handle.isNull())return string(field(target,'translationKey'));
            }
        }catch(_){}
        return null;
    }
    return function metadata(p){
        const layout=layouts[p.class.name]||[];
        const bindings=layout.map(([role,name])=>{
            const path=field(p,name);let key=null,pathType=null,template=null;
            try{
                if(path&&!path.handle.isNull()){
                    pathType=path.class.name;
                    key=bindingKey(path);
                    template=templateDescriptor(field(path,'templatePath'));
                }
            }catch(_){}
            return {role,key,path_type:pathType,template};
        });
        const complete=bindings.length>0&&bindings.every(b=>!!b.key);
        return {semantic_key:complete?bindings.map(b=>b.key).join('|'):null,
            semantic_group:string(field(p,'_transferableGroupType')),
            semantic_kind:layout.length===2?'combined':layout.length===1?'single':'unavailable',
            semantic_status:complete?'complete':bindings.some(b=>b.key)?'partial':'unavailable',
            semantic_bindings:bindings,translation_key:translationKey(p)};
    };
};
