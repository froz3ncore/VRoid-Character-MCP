import asyncio
import json
import zipfile

import pytest

from vroid_mcp.runtime import Runtime


def subject(tmp_path):
    runtime = Runtime(tmp_path)
    async def settle(*args): return {'model_token': 'live'}
    runtime._settle = settle
    return runtime


def binding(id='exact', type='float', **extra):
    return dict(id=id, type=type, units='native_vm', value=0., min=-1., max=1.,
                editable=True, binding_keys=['native-key'], **extra)


@pytest.mark.parametrize('changes', [
    [{'id': 'label', 'type': 'float', 'units': 'native_vm', 'value': .2}],
    [{'id': 'exact', 'type': 'float', 'units': 'native_vm', 'value': True}],
    [{'id': 'exact', 'type': 'float', 'units': 'percent', 'value': .2}],
    [{'id': 'exact', 'type': 'float', 'units': 'native_vm', 'value': float('nan')}],
    [{'id': 'exact', 'type': 'float', 'units': 'native_vm', 'value': 2.}],
])
def test_invalid_group_batch_has_no_native_writes(tmp_path, changes):
    runtime = subject(tmp_path)
    calls = []
    async def call(op, args):
        calls.append(op)
        assert op == 'list_group_parameters'
        return {'model_token': 'live', 'parameters': [binding()]}
    runtime._call = call
    with pytest.raises(ValueError):
        asyncio.run(runtime.set_group_parameters('live', 'group', changes))
    assert calls == ['list_group_parameters']


def test_overlap_prevalidates_every_change(tmp_path):
    from vroid_mcp.group_validation import validate_changes
    rows = [binding(), binding('alias')]
    with pytest.raises(ValueError, match='OVERLAPPING'):
        validate_changes(rows, [dict(id=row['id'], type='float', units='native_vm', value=.1) for row in rows])


@pytest.mark.parametrize('type,value,valid', [('bool', 1, False), ('bool', True, True),
    ('color', [.1, .2, .3, 1.], True), ('color', [0, 0, 0, 2], False),
    ('color', [0, 0, True, 1], False), ('float', .25, True)])
def test_strict_typed_values(type, value, valid):
    from vroid_mcp.group_validation import validate_changes
    change = dict(id='exact', type=type, units='native_vm', value=value)
    if valid:
        assert validate_changes([binding(type=type)], [change]) == [change]
    else:
        with pytest.raises(ValueError): validate_changes([binding(type=type)], [change])


def test_group_partial_result_settles_and_reads_actual_values(tmp_path):
    runtime = subject(tmp_path)
    calls = []
    async def call(op, args):
        calls.append(op)
        if op == 'list_group_parameters': return {'model_token': 'live', 'parameters': [binding()]}
        return {'model_token': 'live', 'ok': False, 'partial': True, 'applied': [], 'frame': 3}
    runtime._call = call
    result = asyncio.run(runtime.set_group_parameters('live', 'g', [dict(id='exact', type='float', units='native_vm', value=.2)]))
    assert not result['ok'] and result['readback']['parameters'][0]['value'] == 0
    assert calls == ['list_group_parameters', 'set_group_parameters', 'list_group_parameters']


@pytest.mark.parametrize('observation',['match','different','removed','lost-proof'])
def test_item_slider_receipt_requires_fresh_exact_native_readback(tmp_path, observation):
    runtime = subject(tmp_path)
    row = dict(id='item/g/hem', type='float', units='native_item_blendshape', min=0, max=100,
               editable=True, value=37.5, item_slider=True, binding_keys=['group:g/template:skirt/hem'])
    calls = []
    async def call(op, args):
        calls.append(op)
        if op == 'set_group_parameters':
            return dict(model_token='live', ok=True, frame=2, applied=[{'id':row['id'],'requested':58.75}])
        observations = [row]
        if len(calls)>1:
            observations = [] if observation=='removed' else [dict(row, editable=observation!='lost-proof',
                value=37.5 if observation=='different' else 58.75)]
        return dict(model_token='live', parameters=observations)
    runtime._call = call
    change = dict(id=row['id'],type='float',units=row['units'],value=58.75)
    result = asyncio.run(runtime.set_group_parameters('live','g',[change]))
    assert result['ok'] is (observation=='match')
    assert result['settled'] and result['applied'] and calls.count('set_group_parameters') == 1
    assert result['item_readback'][0]['verified'] is (observation=='match')


def test_custom_zip_checks_and_registered_byte_identity(tmp_path):
    from vroid_mcp.custom_item_file import inspect_custom_item, resolve_registered
    path = tmp_path / 'copy.vroidcustomitem'
    meta = {'rootTransferableGroupId': 'g', 'rootTransferableGroupTypeId': 'type'}
    with zipfile.ZipFile(path, 'w') as archive: archive.writestr('v1customitem/meta.json', json.dumps(meta))
    source = tmp_path / 'registered.vroidcustomitem'
    source.write_bytes(path.read_bytes())
    row = dict(id='g', group_type='type', path=str(source), resource_name='user/g', revision='r',
               custom_resource_name='user/custom', custom_revision='c', registered=True)
    info = inspect_custom_item(path)
    snapshot = dict(files=[row], base_path=str(tmp_path))
    assert resolve_registered(info, snapshot, None)[0]['path'] == str(source)
    source.write_bytes(b'changed')
    with pytest.raises(ValueError, match='UNREGISTERED'): resolve_registered(info, snapshot, None)


@pytest.mark.parametrize('entry', ['../bad', '/bad', 'C:/bad', 'v1customitem/../bad', 'a\\..\\bad'])
def test_custom_zip_rejects_traversal(tmp_path, entry):
    from vroid_mcp.custom_item_file import inspect_custom_item
    path = tmp_path / 'bad.vroidcustomitem'
    with zipfile.ZipFile(path, 'w') as archive: archive.writestr(entry, '{}')
    with pytest.raises(ValueError): inspect_custom_item(path)


def test_removal_prevalidates_all_and_preserves_partial_outcomes(tmp_path):
    runtime = subject(tmp_path)
    calls = []
    groups = [dict(id='a', type='T', removable=True), dict(id='b', type='T', removable=False)]
    async def call(op, args):
        calls.append(op)
        return {'model_token': 'live', 'groups': groups, 'membership_complete': True}
    runtime._call = call
    with pytest.raises(ValueError, match='NONREMOVABLE'):
        asyncio.run(runtime.remove_items('live', 'T'))
    assert calls == ['list_groups']


@pytest.mark.parametrize('height,weight,variant', [(True, None, 'F00'), (0, None, 'F00'),
    (170, -1, 'F00'), (170, float('nan'), 'F00'), (170, None, 'unknown')])
def test_body_size_inputs_reject_before_dispatch(tmp_path, height, weight, variant):
    runtime = subject(tmp_path)
    async def call(*args): raise AssertionError('must not dispatch')
    runtime._call = call
    with pytest.raises(ValueError): asyncio.run(runtime.set_body_size('live', height, weight, variant))


def test_silhouette_uses_exact_pair_and_live_feedback(tmp_path):
    runtime = subject(tmp_path)
    controls = {'scale': .2, 'figure': 0., 'waist': -.1}
    rows = [binding(id, **{'semantic_bindings': [{'key': key} for key in keys]}) for id, keys in [
        ('scale', ['Level2WholeBody_WholeBodyScaleShrink', 'Level2WholeBody_WholeBodyScaleMag']),
        ('figure', ['Level2WholeBody_FigureHeightFemale', 'Level2WholeBody_FigureSlenderFemale']),
        ('waist', ['Level2Waist_WaistScaleShrink', 'Level2Waist_WaistScaleMag'])]]
    for row in rows: row.update(value=controls[row['id']], binding_keys=[row['id']])
    for row in rows:
        row.update(type='CombinedBoneTransformParameterViewModel', semantic_kind='combined',
            semantic_group='TransferableGroupType.N00.Level1.' + ('Waist' if row['id'] == 'waist' else 'WholeBody'))
    async def call(op, args):
        if op == 'status': return {'model_token':'live','model_variant':'F00'}
        if op == 'list_body_params': return {'model_token': 'live', 'parameters': rows}
        if op == 'get_height': return {'live_centimeters': 160 + 20*controls['figure']}
        if op == 'set_body_params':
            for change in args['changes']:
                controls[change['id']] = change['value']
                next(row for row in rows if row['id'] == change['id'])['value'] = change['value']
            return {'ok': True, 'frame': 2}
        raise AssertionError(op)
    runtime._call = call
    result = asyncio.run(runtime.set_body_size('live', 170, 65))
    assert result['ok'] and result['measured_cm'] == pytest.approx(170)
    assert controls['scale'] == 0 and controls['figure'] == pytest.approx(.5)
    assert result['weight_is_heuristic'] and 'BMI' in result['weight_convention']


def test_preserve_native_dispatch_cancellation_marks_uncertain(tmp_path):
    runtime = subject(tmp_path)
    async def call(*args): raise asyncio.CancelledError()
    runtime._call = call
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(runtime.apply_preset('clothing', 'live', 'preset', True))
    assert runtime.uncertain


def test_custom_native_validation_cancellation_retains_task(tmp_path, monkeypatch):
    from contextlib import nullcontext
    from vroid_mcp import runtime_groups
    runtime = subject(tmp_path)
    path = tmp_path / 'item.vroidcustomitem'
    path.touch()
    root = tmp_path / 'profile'
    root.mkdir()
    registered = root / path.name
    registered.touch()
    info = dict(metadata={}, sha256='hash')
    row = dict(path=str(registered))
    monkeypatch.setattr(runtime_groups, 'file_input', lambda *a, **k:path)
    monkeypatch.setattr(runtime_groups, 'inspect_custom_item', lambda *a, **k:info)
    monkeypatch.setattr(runtime_groups, 'resolve_registered', lambda *a:(row,registered.stat()))
    monkeypatch.setattr(runtime_groups, 'pinned_application', lambda *a:nullcontext())
    calls = []
    async def call(op, args):
        calls.append(op)
        if op == 'custom_item_state': return dict(model_token='live',base_path=str(root),files=[])
        if op == 'custom_item_validate_begin': return dict(model_token='live',request_id='r',completed=False)
        if op == 'custom_item_validate_poll': raise asyncio.CancelledError()
        if op == 'custom_item_validate_release': raise AssertionError('inflight task released')
    runtime._call = call
    with pytest.raises(asyncio.CancelledError): asyncio.run(runtime.apply_custom_item('live', 'item.vroidcustomitem'))
    assert runtime.uncertain and 'custom_item_validate_release' not in calls


def test_group_model_identity_mismatch_blocks_native_write(tmp_path):
    runtime = subject(tmp_path)
    async def call(op, args):
        assert op == 'list_group_parameters'
        return {'model_token':'old','parameters':[binding()]}
    runtime._call = call
    with pytest.raises(ValueError, match='STALE_MODEL'):
        asyncio.run(runtime.set_group_parameters('live','g',[dict(id='exact',type='float',units='native_vm',value=.2)]))


def test_silhouette_restores_after_nonconvergence_and_reports_failed_restoration(tmp_path):
    for fail_restore in (False, True):
        runtime = subject(tmp_path)
        controls = {'scale':.2,'figure':.1,'waist':-.1}
        rows = []
        for id, keys, group in [
            ('scale',['Level2WholeBody_WholeBodyScaleShrink','Level2WholeBody_WholeBodyScaleMag'],'WholeBody'),
            ('figure',['Level2WholeBody_FigureHeightFemale','Level2WholeBody_FigureSlenderFemale'],'WholeBody'),
            ('waist',['Level2Waist_WaistScaleShrink','Level2Waist_WaistScaleMag'],'Waist')]:
            rows.append(dict(id=id,value=controls[id],min=-1,max=1,editable=True,
                type='CombinedBoneTransformParameterViewModel',semantic_kind='combined',
                semantic_group='TransferableGroupType.N00.Level1.'+group,
                semantic_bindings=[{'key':key} for key in keys]))
        async def call(op,args):
            if op == 'status': return dict(model_token='live',model_variant='F00')
            if op == 'list_body_params': return dict(model_token='live',parameters=rows)
            if op == 'get_height': return dict(live_centimeters=160)
            if op == 'set_body_params':
                if fail_restore and len(args['changes']) == 3: return dict(ok=False,error='restore failed')
                for c in args['changes']:
                    controls[c['id']] = c['value']
                    next(row for row in rows if row['id']==c['id'])['value']=c['value']
                return dict(ok=True,frame=1)
        runtime._call=call
        result=asyncio.run(runtime.set_body_size('live',180))
        assert not result['ok']
        if fail_restore: assert runtime.uncertain and result['restoration_error']
        else: assert result['restored'] and controls == {'scale':.2,'figure':.1,'waist':-.1}


def test_silhouette_refuses_binding_in_unrelated_group(tmp_path):
    from vroid_mcp.silhouette import paired_control
    row = dict(semantic_bindings=[{'key':'negative'},{'key':'positive'}],editable=True,min=-1,max=1,
               semantic_group='unrelated',semantic_kind='combined',type='CombinedBoneTransformParameterViewModel')
    with pytest.raises(ValueError): paired_control([row],'negative','positive','WholeBody')


@pytest.mark.parametrize('observed', ['M00', None])
def test_silhouette_refuses_wrong_or_unknown_native_variant_before_write(tmp_path, observed):
    runtime=subject(tmp_path)
    async def call(op,args):
        assert op=='status'
        return dict(model_token='live',model_variant=observed)
    runtime._call=call
    with pytest.raises(ValueError,match='VARIANT_MISMATCH'):
        asyncio.run(runtime.set_body_size('live',170,variant='F00'))


def test_preset_search_owned_default_and_explicit_preserve_delegation(tmp_path):
    runtime = subject(tmp_path)
    calls=[]
    async def call(op,args):
        calls.append((op,args))
        return {'presets':[],'categories':[]}
    runtime._call=call
    asyncio.run(runtime.list_presets('hair',search='blue',owned_only=False))
    assert calls[0][1]['search']=='blue' and calls[0][1]['owned_only'] is False
    calls.clear()
    asyncio.run(runtime.list_presets('hair'))
    assert calls[0][1]['owned_only'] is True


def test_removal_reports_first_success_then_uncertain_failure_without_retry(tmp_path):
    runtime=subject(tmp_path)
    groups=[dict(id='a',type='T',removable=True),dict(id='b',type='T',removable=True)]
    removed=[]
    async def call(op,args):
        if op=='list_groups': return dict(model_token='live',groups=[g for g in groups if g['id'] not in removed],membership_complete=True)
        if op=='remove_group':
            if args['group_id']=='b': raise RuntimeError('native failure')
            removed.append('a')
            return dict(frame=1,expected_removed_ids=['a'])
    runtime._call=call
    result=asyncio.run(runtime.remove_items('live','T'))
    assert result['partial'] and not result['ok'] and runtime.uncertain
    assert [row['removed'] for row in result['outcomes']]==[True,False]


def test_custom_zip_rejects_duplicate_names_and_nonobject_metadata(tmp_path):
    from vroid_mcp.custom_item_file import inspect_custom_item
    for name,body in [('duplicate',{}),('badmeta',[])]:
        path=tmp_path/(name+'.vroidcustomitem')
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr('v1customitem/meta.json',json.dumps(body))
            if name=='duplicate': archive.writestr('V1CUSTOMITEM/META.JSON','{}')
        with pytest.raises(ValueError): inspect_custom_item(path)


def test_new_tools_registered_without_app_launch(tmp_path):
    from vroid_mcp import server
    mcp=server.create_server(tmp_path,'F00')
    names=set(mcp._tool_manager._tools)
    assert {'list_groups','list_group_parameters','set_group_parameters','list_sections','list_categories',
        'enter_category','remove_items','apply_custom_item','set_body_size'} <= names


def test_uncertain_native_application_keeps_validated_file_pinned(tmp_path, monkeypatch):
    from contextlib import contextmanager
    from vroid_mcp import custom_item_file
    runtime=subject(tmp_path)
    calls=[]
    @contextmanager
    def pin(path):
        calls.append('pinned')
        try: yield
        finally: calls.append('released')
    monkeypatch.setattr(custom_item_file,'pinned_file',pin)
    with custom_item_file.pinned_application(runtime,tmp_path/'item'):
        runtime.uncertain=True
    assert calls==['pinned']
    runtime._pending_custom_item_pins.pop().__exit__(None,None,None)
    assert calls==['pinned','released']


def test_silhouette_partial_command_settles_before_restoration(tmp_path):
    runtime=subject(tmp_path)
    rows=[]
    for id,keys,group in [('scale',['WholeBodyScaleShrink','WholeBodyScaleMag'],'WholeBody'),
        ('figure',['FigureHeightFemale','FigureSlenderFemale'],'WholeBody'),
        ('waist',['WaistScaleShrink','WaistScaleMag'],'Waist')]:
        rows.append(dict(id=id,value=0.,min=-1,max=1,editable=True,type='CombinedBoneTransformParameterViewModel',
            semantic_kind='combined',semantic_group='TransferableGroupType.N00.Level1.'+group,
            semantic_bindings=[{'key':'Level2'+group+'_'+key} for key in keys]))
    events=[]
    async def settle(*args):
        events.append(('settle',args))
        return {'model_token':'live'}
    async def call(op,args):
        if op=='status': return dict(model_token='live',model_variant='F00')
        if op=='list_body_params': return dict(model_token='live',parameters=rows)
        if op=='set_body_params':
            if len(args['changes'])==2:
                events.append(('partial',7))
                return dict(ok=False,partial=True,frame=7)
            assert ('settle',('live',7)) in events
            return dict(ok=True,frame=8)
        raise AssertionError(op)
    runtime._settled_for=settle
    runtime._call=call
    result=asyncio.run(runtime.set_body_size('live',170))
    assert not result['ok'] and result.get('restored'),result


def test_removal_does_not_confirm_absence_from_failed_inventory(tmp_path):
    runtime=subject(tmp_path)
    groups=[dict(id='a',type='T',removable=True),dict(id='b',type='T',removable=True)]
    removals=[]
    async def call(op,args):
        if op=='list_groups':
            if not removals: return dict(model_token='live',groups=groups,membership_complete=True,errors=[])
            return dict(model_token='live',groups=[],membership_complete=False,
                source_completeness={'active':False,'active_leaf':False,'stored':False},
                errors=[dict(source='active',error='native enumeration failed')])
        if op=='remove_group':
            removals.append(args['group_id'])
            return dict(frame=1,expected_removed_ids=[args['group_id']])
    runtime._call=call
    result=asyncio.run(runtime.remove_items('live','T'))
    assert not result['ok'] and result['uncertain'] and runtime.uncertain
    assert removals==['a']
    assert result['outcomes'][0]['removed'] is False and result['outcomes'][0]['unconfirmed']
    assert result['outcomes'][0]['discovery_errors'][0]['source']=='active'
    assert result['outcomes'][1]['skipped']


@pytest.mark.parametrize('failure',['poll_error','model_change','cleanup_error'])
def test_custom_validation_preserves_primary_failure_and_pending_lifetimes(tmp_path,monkeypatch,failure):
    from contextlib import contextmanager
    from vroid_mcp import runtime_groups, custom_item_file
    runtime=subject(tmp_path)
    runtime.mode='attached'
    registered=tmp_path/'registered.vroidcustomitem'
    registered.touch()
    events=[]
    @contextmanager
    def pin(path):
        events.append('pin_acquired')
        try: yield
        finally: events.append('pin_released')
    monkeypatch.setattr(custom_item_file,'pinned_file',pin)
    monkeypatch.setattr(runtime_groups,'file_input',lambda *a,**k:registered)
    monkeypatch.setattr(runtime_groups,'inspect_custom_item',lambda *a,**k:dict(metadata={},sha256='hash'))
    monkeypatch.setattr(runtime_groups,'resolve_registered',lambda *a:(dict(path=str(registered)),registered.stat()))
    async def no_sleep(*args): pass
    monkeypatch.setattr(runtime_groups.asyncio,'sleep',no_sleep)
    async def call(op,args):
        events.append(op)
        if op=='custom_item_state':return dict(model_token='live',base_path=str(tmp_path),files=[])
        if op=='custom_item_validate_begin':return dict(model_token='live',request_id='pending',completed=False)
        if op=='custom_item_validate_poll':
            if failure=='poll_error': raise RuntimeError('PRIMARY_POLL_FAILURE')
            if failure=='model_change': return dict(model_token='new-model',completed=False)
            return dict(model_token='live',completed=True,compatible=False,error='PRIMARY_INCOMPATIBLE')
        if op=='custom_item_validate_release':raise RuntimeError('SECONDARY_CLEANUP_FAILURE')
        raise AssertionError(op)
    runtime._call=call
    expected={'poll_error':'PRIMARY_POLL_FAILURE','model_change':'STALE_MODEL','cleanup_error':'PRIMARY_INCOMPATIBLE'}[failure]
    try:
        with pytest.raises((RuntimeError,ValueError),match=expected) as raised:
            asyncio.run(runtime.apply_custom_item('live','registered.vroidcustomitem'))
        assert runtime.uncertain and 'pin_released' not in events
        if failure!='cleanup_error': assert 'custom_item_validate_release' not in events
        else:
            assert 'SECONDARY_CLEANUP_FAILURE' in str(raised.value.__notes__)
            assert runtime._custom_item_cleanup_errors[-1]['error']=='SECONDARY_CLEANUP_FAILURE'
    finally:
        for pending in getattr(runtime,'_pending_custom_item_pins',[]): pending.__exit__(None,None,None)


@pytest.mark.parametrize('failure',[False,True])
def test_attached_close_retains_pending_custom_lifetime_until_terminal_cleanup(tmp_path,monkeypatch,failure):
    from types import SimpleNamespace
    from vroid_mcp import bridge
    runtime=subject(tmp_path)
    runtime.mode='attached'
    runtime.pid=123
    events=[]
    class Pin:
        def __exit__(self,*args):events.append('pin_released')
    pin=Pin()
    runtime._pending_custom_item_pins=[pin]
    pending=True
    def release():
        events.append('release')
        if pending and failure:raise RuntimeError('PRIMARY_RELEASE_FAILURE')
        return dict(released=not pending,release_blocked=pending,pending_work=['native custom load'] if pending else [])
    script=SimpleNamespace(exports_sync=SimpleNamespace(release=release),unload=lambda:events.append('unload'))
    session=SimpleNamespace(detach=lambda:events.append('detach'))
    runtime.script,runtime.session=script,session
    runtime.device=SimpleNamespace(kill=lambda *a:events.append('KILL_FORBIDDEN'))
    monkeypatch.setattr(bridge,'record',lambda *a:None)
    result=runtime.close()
    assert result['close_blocked'] and not result['detached']
    assert not runtime.dead and runtime.script is script and runtime.session is session
    assert runtime._pending_custom_item_pins==[pin] and events==['release']
    if failure: assert result['release_error']=='PRIMARY_RELEASE_FAILURE'
    pending=False
    result=runtime.close()
    assert result['detached'] and runtime.dead
    assert events==['release','release','unload','detach','pin_released']
    assert runtime._pending_custom_item_pins==[]


def test_owned_copy_custom_pin_released_only_after_process_termination(tmp_path):
    from types import SimpleNamespace
    runtime=subject(tmp_path)
    runtime.pid=123
    runtime.owns_process=True
    events=[]
    class Pin:
        def __exit__(self,*args):events.append('pin_released')
    runtime._pending_custom_item_pins=[Pin()]
    runtime.device=SimpleNamespace(kill=lambda pid:events.append(('owned_kill',pid)))
    result=runtime.close()
    assert result['native_process_stopped'] and events==[('owned_kill',123),'pin_released']


def test_custom_application_waits_for_native_lifetime_receipt_before_release(tmp_path,monkeypatch):
    from contextlib import contextmanager
    from vroid_mcp import runtime_groups,custom_item_file
    runtime=subject(tmp_path);runtime.mode='attached'
    registered=tmp_path/'item.vroidcustomitem';registered.touch()
    row=dict(id='g',path=str(registered),resource_name='resource',revision='r')
    events=[];observations=[]
    @contextmanager
    def pin(path):
        events.append('pin_acquired')
        try:yield
        finally:events.append('pin_released')
    monkeypatch.setattr(custom_item_file,'pinned_file',pin)
    monkeypatch.setattr(runtime_groups,'file_input',lambda *a,**k:registered)
    monkeypatch.setattr(runtime_groups,'inspect_custom_item',lambda *a,**k:dict(metadata={},sha256='hash'))
    monkeypatch.setattr(runtime_groups,'resolve_registered',lambda *a:(row,registered.stat()))
    async def no_sleep(*args):pass
    monkeypatch.setattr(runtime_groups.asyncio,'sleep',no_sleep)
    async def call(op,args):
        events.append(op)
        if op=='custom_item_state':return dict(model_token='live',base_path=str(tmp_path),files=[])
        if op=='custom_item_validate_begin':return dict(model_token='live',request_id='r',completed=False)
        if op=='custom_item_validate_poll':return dict(model_token='live',completed=True,compatible=True)
        if op=='apply_registered_custom_item':return dict(frame=1)
        if op=='list_groups':return dict(model_token='live',membership_complete=True,
            groups=[dict(id='g',active=True,resource_name='resource',revision='r')])
        if op=='custom_item_application_state':
            observations.append(1)
            assert 'pin_released' not in events
            return dict(model_token='live',completed=len(observations)==3)
        if op=='custom_item_validate_release':
            assert len(observations)==3
            return dict(released=True)
        raise AssertionError(op)
    runtime._call=call
    result=asyncio.run(runtime.apply_custom_item('live','item.vroidcustomitem'))
    assert result['applied'] and result['native_completion']['completed']
    assert events[-2:]==['custom_item_validate_release','pin_released']


@pytest.mark.parametrize('liveness',['absent','alive','unknown'])
def test_disconnected_owned_copy_proves_process_absence_before_releasing_pins(tmp_path,liveness):
    from vroid_mcp import bridge
    runtime=subject(tmp_path)
    runtime.dead=True;runtime.owns_process=True;runtime.pid=123
    events=[]
    class Pin:
        def __exit__(self,*args):events.append('pin_released')
    class Device:
        def get_process(self,pid):
            events.append(('probe',pid))
            if liveness=='absent':raise bridge.frida.ProcessNotFoundError('already exited')
            if liveness=='unknown':raise RuntimeError('process state unavailable')
            return object()
        def kill(self,*args):raise AssertionError('disconnected liveness is not authority to kill')
    runtime.device=Device();pin=Pin();runtime._pending_custom_item_pins=[pin]
    result=runtime.close()
    if liveness=='absent':
        assert result.get('native_process_stopped') and not result.get('close_blocked')
        assert events==[('probe',123),'pin_released'] and runtime._pending_custom_item_pins==[]
    else:
        assert result['close_blocked'] and runtime._pending_custom_item_pins==[pin]
        assert events==[('probe',123)]
