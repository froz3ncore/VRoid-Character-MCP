// Static native evidence: allowlisted pixiv-signed VRoid 2.14.0 ed65ebbc... only.
// See docs/native-evidence/2026-11-07-procedural-hair.md. Compiler ordinals are
// descriptors for that exact assembly, never cross-build semantic identifiers.
globalThis.createProceduralHairBindings = H => {
    const verified='ed65ebbc1e806db635566347a9022b9577f6b3d373db128ea23f0e862e005296';
    const owner='VRoid.Studio.HairEditor.DesignEditor.HairGroup.ViewModel.ProceduralHairGroupPropertyViewModel';
    const itemPrefix='VRoid.Studio.HairEditor.DesignEditor.Parameter.ViewModel.';
    const {prop,seq,text,pin,invokeManaged,boxArgument}=H;
    const identity=p=>['TransferableId','HairGroupId'].map(k=>text(prop(p,k))).join('/');
    function owned(object,path,engine){
        const bound=pin(prop(object,'_proceduralHairGroupPath'));
        const actual=pin(prop(object,'_engine'));
        if(identity(bound)!==identity(path)||!actual.handle.equals(engine.handle))throw Error('PROCEDURAL_CONTROL_OWNERSHIP_MISMATCH');
    }
    function delegate(item,field,name,path,engine,ownerClass){
        const d=pin(prop(item,field));
        if(!d||d.handle.isNull())return null;
        const target=pin(d.method('get_Target').invoke());
        if(!target||target.handle.isNull())return null;
        if(target.class.name!=='<>c__DisplayClass7_0'||!target.class.declaringClass?.handle.equals(ownerClass.handle))return null;
        const method=target.class.method(name);
        // Match actual native delegate code address, not labels, values, indexes
        // or compiler-name substring similarity. The hash validates this mapping.
        if(!prop(d,'method_ptr').equals(method.virtualAddress))return null;
        const accessor=pin(prop(target,'a'));
        if(accessor.class.name!=='Accessor'||!accessor.class.declaringClass?.handle.equals(ownerClass.handle))throw Error('PROCEDURAL_ACCESSOR_TYPE_MISMATCH');
        owned(accessor,path,engine);
        return target;
    }
    return ({property,path,engine})=>{
        if(H.assemblySha256!==verified)throw Error('PROCEDURAL_DESCRIPTOR_UNVERIFIED_BUILD: no procedural write attempted');
        if(property.class.type.name!==owner)throw Error('PROCEDURAL_PROPERTY_TYPE_MISMATCH');
        pin(property);owned(property,path,engine);
        const controls=[];
        for(const g of seq(prop(property,'Groups')))for(const item of seq(prop(g,'ParameterItems'))){
            pin(item);
            for(const descriptor of [
                {key:'length',type:'float',native:'Float',getter:'<CreateGroups>b__41',setter:'<CreateGroups>b__42'},
                {key:'hair_count',type:'int',native:'Int',getter:'<CreateGroups>b__51',setter:'<CreateGroups>b__52'}]){
                if(item.class.type.name!==itemPrefix+descriptor.native+'ParameterViewModel')continue;
                const getter=delegate(item,'_getter',descriptor.getter,path,engine,property.class);
                const setter=delegate(item,'_setter',descriptor.setter,path,engine,property.class);
                if(!getter||!setter||!getter.handle.equals(setter.handle))continue;
                const min=prop(item,'MinValue'),max=prop(item,'MaxValue');
                if(!Number.isFinite(min)||!Number.isFinite(max)||min>max||
                    (descriptor.type==='int'&&(!Number.isInteger(min)||!Number.isInteger(max))))throw Error('PROCEDURAL_NATIVE_RANGE_INVALID');
                const validator=pin(prop(item,'validator'));
                if(validator.method('Invoke').invoke()!==true)throw Error('PROCEDURAL_CONTROL_NOT_VALID');
                controls.push({key:descriptor.key,type:descriptor.type,min,max,value:prop(item,'Value'),
                    range_source:'native UI',binding_source:'verified assembly native delegate/accessor/parameter field mapping',
                    write(value,onInvoke){
                        owned(property,path,engine);
                        if(validator.method('Invoke').invoke()!==true)throw Error('PROCEDURAL_CONTROL_NOT_VALID');
                        const argument=boxArgument(descriptor.type,value);
                        onInvoke?.();
                        invokeManaged(item,'set_Value',[argument]);
                    }});
            }
        }
        if(controls.length!==2||new Set(controls.map(c=>c.key)).size!==2)throw Error('PROCEDURAL_EXACT_BINDINGS_UNAVAILABLE_OR_AMBIGUOUS');
        return controls;
    };
};
