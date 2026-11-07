// ed65-only native managed modifiers and immutable UI bounds, statically verified
// from ProceduralHairGroupPropertyViewModel.CreateGroups. No JS delegate/callback
// is handed to native history; native Action constructors retain native captures.
globalThis.createProceduralHairFallback = H => {
    const hash='ed65ebbc1e806db635566347a9022b9577f6b3d373db128ea23f0e862e005296';
    const ownerName='VRoid.Studio.HairEditor.DesignEditor.HairGroup.ViewModel.ProceduralHairGroupPropertyViewModel';
    const parameterSet='VRoidCore.Common.SpecificTypes.ProceduralHairGroupParameterSet';
    const {cls,pin,prop,invokeManaged,boxArgument}=H;
    const signature=(method,params,returns)=>method.parameters.length===params.length&&
        method.parameters.every((p,i)=>p.type.name===params[i])&&(!returns||method.returnType.name===returns);
    const bad=()=>Error('PROCEDURAL_NATIVE_MODIFIER_SIGNATURE_UNVERIFIED');
    return ({path,configured})=>{
        if(H.assemblySha256!==hash)throw Error('PROCEDURAL_DESCRIPTOR_UNVERIFIED_BUILD');
        const owner=cls('VRoid.Studio',ownerName);
        const commandClass=cls('VRoidCore','VRoidCore.Editing.History.Command.ModifyProceduralHairGroupParameterSetCommand');
        const ctor=commandClass.method('.ctor',4),p=ctor.parameters;
        if(p.length!==4||p[0].type.name!=='System.String'||p[1].type.name!=='VRoidCore.Common.SpecificTypes.ProceduralHairGroupPath'||
            p[3].type.name!=='System.Boolean')throw bad();
        const actionClass=p[2].type.class;
        if(!signature(actionClass.method('Invoke',1),[parameterSet],'System.Void')||
            !signature(actionClass.method('.ctor',2),['System.Object','System.IntPtr']))throw bad();
        return [
            {key:'length',type:'float',nativeType:'System.Single',capture:'<>c__DisplayClass7_15',method:'<CreateGroups>b__97',min:Math.fround(.1),max:1},
            {key:'hair_count',type:'int',nativeType:'System.Int32',capture:'<>c__DisplayClass7_20',method:'<CreateGroups>b__102',min:1,max:20},
        ].map(d=>{
            const captureClass=owner.nestedClasses.find(c=>c.name===d.capture);
            if(!captureClass||!captureClass.declaringClass.handle.equals(owner.handle)||
                captureClass.field('v').type.name!==d.nativeType||captureClass.method('.ctor',0).parameters.length!==0)throw bad();
            const method=captureClass.method(d.method,1);
            if(!signature(method,[parameterSet],'System.Void')||method.virtualAddress.isNull())throw bad();
            return {key:d.key,type:d.type,min:d.min,max:d.max,value:configured[d.key],native_route:'command',
                range_source:'statically verified native CreateGroups UI bounds; exact ed65 assembly',
                binding_source:'native managed modifier '+d.capture+'.'+d.method,
                write(value,onInvoke){
                    const converted=d.type==='float'?Math.fround(value):value;
                    if(!Number.isFinite(converted)||converted<d.min||converted>d.max||
                        (d.type==='int'&&!Number.isInteger(converted)))throw Error('PROCEDURAL_NATIVE_RANGE');
                    H.validate();
                    const capture=pin(captureClass.alloc());invokeManaged(capture,'.ctor',[]);
                    capture.field('v').value=converted;
                    const action=pin(actionClass.alloc());
                    const argument=H.boxMethodInfo(method);
                    invokeManaged(action,'.ctor',[capture.handle,argument]);
                    const target=pin(action.method('get_Target').invoke());
                    if(!target.handle.equals(capture.handle)||!prop(action,'method_ptr').equals(method.virtualAddress))throw bad();
                    const command=pin(commandClass.alloc());
                    invokeManaged(command,'.ctor',[Il2Cpp.string('mcp').handle,path.handle,action.handle,boxArgument('bool',true)]);
                    onInvoke?.();H.execute(command);
                }};
        });
    };
};
