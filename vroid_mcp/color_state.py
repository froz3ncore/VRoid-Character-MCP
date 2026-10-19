"""Report actual settled color effects, including aggregates and shared aliases."""
def attach_color_readback(result: dict, rows: list[dict]) -> dict:
    indexed={p['id']:p for p in rows if p.get('type')=='color'}
    affected=set(result.get('affected_color_parameter_ids',[]))
    verified=[]
    for applied in result.get('applied',[]):
        if 'requested_value' not in applied:continue
        affected.add(applied['id'])
        current=indexed.get(applied['id'])
        if current is None:
            raise ValueError('Applied color is missing from settled native readback')
        applied['after']=current['value']
        bindings=current.get('color_bindings',[])
        complete=(current.get('color_binding_status')=='complete' and bool(bindings)
                  and all(b.get('value_status')=='read' for b in bindings))
        match=(all(all(abs(v-w)<=1e-6 for v,w in zip(b['value'],applied['requested_value'],strict=True))
                   for b in bindings) if complete else None)
        applied['verified']=match;applied['mixed_after']=current.get('mixed')
        verified.append(match)
    result['affected_parameters']=[indexed[i] for i in sorted(affected) if i in indexed]
    result['color_verification_status']=('not_performed' if not verified else
                                         'failed' if False in verified else
                                         'partial' if None in verified or not result.get('ok') else 'complete')
    if False in verified and result.get('ok'):
        result.update(ok=False,error='NATIVE_COLOR_READBACK_MISMATCH: inspect actual colors before any further write')
    return result
