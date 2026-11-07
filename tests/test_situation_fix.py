"""Counterexamples from the nine Task 8 findings, exercised through real gallery/store."""
import asyncio
import base64
from copy import deepcopy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_situation_gallery import Native,run,group
from test_preset_previews import png
from vroid_mcp.preset_catalog import PresetCatalog


@pytest.mark.parametrize('at',['remove_group','screenshot'])
def test_snapshot_generation_is_pinned_before_destructive_work_and_released(tmp_path,at):
    if os.name!='nt':pytest.skip('Windows sharing')
    n=Native(tmp_path);original=n.call;attempts=[]
    async def native(op,args=None):
        if op==at:
            path=next((tmp_path/'saves').glob('situation-*.vroid'))
            for action in (lambda:path.write_bytes(b'destroy'),path.unlink):
                try:action();attempts.append('allowed')
                except OSError:attempts.append('blocked')
        return await original(op,args)
    n.runtime._call=native;result=run(n)
    assert attempts and set(attempts)=={'blocked'}
    assert result['restore']['state']=='restored'
    Path(result['snapshot']['path']).write_bytes(b'released')


@pytest.mark.parametrize('change',['remove-skin','replace-skin','insert-iris'])
def test_strip_cannot_redefine_original_allowed_anatomy(tmp_path,change):
    n=Native(tmp_path);original=n.call
    async def native(op,args=None):
        value=await original(op,args)
        if op=='remove_group' and len(n.removed)==1:
            if change=='remove-skin':n.groups=[g for g in n.groups if g['id']!='skin']
            if change=='replace-skin':n.groups[0]=group('other-skin','BodySkin',False)
            if change=='insert-iris':n.groups.append(group('foreign-iris','Iris',False))
        return value
    n.runtime._call=native;result=run(n)
    assert not result['processed'] and n.capture_count==0


def test_bound_tested_slot_does_not_need_an_unrelated_clear_capability(tmp_path):
    n=Native(tmp_path);n.groups[2]['removable']=False;original=n.call
    async def native(op,args=None):
        if op=='apply_preset':n.groups=[g for g in n.groups if g['type']!='TransferableGroupType.N00.Level1.Tops']
        return await original(op,args)
    n.runtime._call=native;result=run(n)
    assert result['processed']==1 and 'top' not in n.removed


@pytest.mark.parametrize('change',['matrix-shift','missing-matrix','nan-clip','wrong-aspect','blank','transparent'])
def test_invalid_optics_or_blank_raster_never_publish_but_keep_bytes(tmp_path,change):
    n=Native(tmp_path);original=n.call
    async def native(op,args=None):
        value=await original(op,args)
        if op=='screenshot':
            f=value['framing']
            if change=='matrix-shift':f['projection_matrix'][2]=3
            if change=='missing-matrix':f.pop('projection_matrix')
            if change=='nan-clip':f['far_clip']=float('nan')
            if change=='wrong-aspect':f['aspect']=.5
            if change=='blank':value['base64']=base64.b64encode(png(512,512)).decode()
            if change=='transparent':
                from vroid_mcp.texture_mapping import png_rgba
                value['base64']=base64.b64encode(png_rgba(512,512,b'\0'*(512*512*4))).decode()
        return value
    n.runtime._call=native;result=run(n)
    assert not result['processed'] and result['errors']
    assert Path(result['rows'][0]['capture_path']).is_file()


@pytest.mark.parametrize('change',['same-engine','wrong-file'])
def test_reminted_token_or_wrong_file_cannot_prove_restoration(tmp_path,change):
    n=Native(tmp_path);original=n.call
    async def native(op,args=None):
        value=await original(op,args)
        if op=='replace_with_file':
            if change=='same-engine':n.engine='engine-old'
            else:n.file_path=str(tmp_path/'other.vroid')
        return value
    n.runtime._call=native;result=run(n)
    assert result['restore']['state']=='unconfirmed' and result['model_token'] is None


def test_partial_clear_outcomes_survive_second_clear_failure(tmp_path):
    n=Native(tmp_path);original=n.call
    async def native(op,args=None):
        if op=='remove_group' and len(n.removed)==1:raise RuntimeError('second clear lost reply')
        return await original(op,args)
    n.runtime._call=native;result=run(n)
    report=json.loads(Path(result['evidence_path']).read_text(encoding='utf-8'))
    assert report['rows'][0]['removed_slots'][0]['id']=='under'
    assert report['restore']['state']=='skipped-uncertain' and report['model_token'] is None


def test_cancelled_restore_persists_pending_recovery_and_retains_generation_pin(tmp_path):
    n=Native(tmp_path)
    async def task(*args):raise asyncio.CancelledError()
    n.runtime._task=task
    with pytest.raises(asyncio.CancelledError):run(n)
    report_path=next((tmp_path/'temp').glob('situation-*/report.json'))
    report=json.loads(report_path.read_text(encoding='utf-8'))
    try:
        assert report['restore']['state']=='pending' and report['model_token'] is None
        assert report['snapshot']['sha256'] and report['uncertain']
        if os.name=='nt':
            with pytest.raises(OSError):Path(report['snapshot']['path']).unlink()
    finally:
        for pin in getattr(n.runtime,'_pending_custom_item_pins',[]):pin.__exit__(None,None,None)
        n.runtime._pending_custom_item_pins=[]


@pytest.mark.parametrize('change',['framing','build','id','scan','annotation'])
def test_cross_process_publication_binds_scan_build_id_and_framing_but_preserves_annotation(tmp_path,change):
    n=Native(tmp_path);original=n.call
    code='''import sys
from vroid_mcp.preset_catalog import PresetCatalog
s=PresetCatalog(__import__('pathlib').Path(sys.argv[1]));mode=sys.argv[2]
if mode=='framing':s.set_framing('Clothing/Tops',yaw=90)
elif mode=='annotation':s.annotate('Clothing/Tops/N00/a','independent',label='survives')
else:
 d=s._load();rows=list(d['presets'].values());source=dict(d['source'])
 if mode=='id':rows[0]['id']='replacement-id'
 if mode=='build':source['build']='b'*64
 s.sync(rows,source,{'builtin':True,'custom':True})
'''
    async def native(op,args=None):
        value=await original(op,args)
        if op=='screenshot':subprocess.run([sys.executable,'-B','-c',code,str(tmp_path/'preset_cache'),change],check=True)
        return value
    n.runtime._call=native;result=run(n)
    assert result['processed']==int(change=='annotation')
    if change=='annotation':assert PresetCatalog(tmp_path/'preset_cache').get(n.rows[0]['resource'])['manual_label']=='survives'


def test_optional_boolean_managed_task_false_is_a_failed_terminal_receipt(tmp_path,monkeypatch):
    from vroid_mcp import bridge
    n=Native(tmp_path)
    async def call(*args):return {'completed':True,'faulted':False,'canceled':False,'result':False}
    monkeypatch.setattr(bridge,'call',call)
    with pytest.raises(RuntimeError,match='false|FAILED'):
        asyncio.run(bridge.wait_task(n.runtime,{'task_id':'failed'}))


def test_prestrip_snapshot_hash_mismatch_refuses_without_model_mutation(tmp_path):
    n=Native(tmp_path);original=n.runtime._save_as_unlocked
    async def save(*args):
        receipt=await original(*args)
        Path(receipt['path']).write_bytes(b'substituted before pin')
        return receipt
    n.runtime._save_as_unlocked=save;result=run(n)
    assert not n.removed and not any(op=='apply_preset' for op,args in n.calls)
    assert result['restore']['state']=='snapshot-changed' and result['processed']==0


@pytest.mark.parametrize('change',['id','revision','legacy-tiny','legacy-missing-proof'])
def test_builtin_reuse_requires_current_independent_native_identity_and_complete_image(tmp_path,change):
    n=Native(tmp_path);assert run(n)['processed']==1;n.token='token'
    s=PresetCatalog(tmp_path/'preset_cache');key=n.rows[0]['resource'];original=n.call
    if change=='id':n.rows[0]['id']='remapped';n.rows[0]['selectable_preset_ids']=['clothing/Tops/remapped']
    if change.startswith('legacy'):
        row=s.get(key);image=row['images']['situation']
        if change=='legacy-tiny':s.publish_image(key,png(),{k:v for k,v in image.items() if k not in ('width','height','bytes','sha256','format','path')},row['fingerprint'])
        else:
            catalog=s._load();catalog['presets'][key]['images']['situation'].pop('framing')
            with s.locked():s._write(s.path,catalog)
    async def native(op,args=None):
        value=await original(op,args)
        if change=='revision':
            if op=='list_groups' and args.get('situation_candidate'):
                value['situation_definition']['root']['revision']='2'
                value['situation_definition']['members'][0]['revision']='2'
            if op=='apply_preset':n.groups[-1]['revision']='2'
        return value
    n.runtime._call=native;result=run(n)
    assert result['processed']==1 and result['skipped']==0 and n.capture_count==2


def test_complete_same_native_revision_reuses_without_snapshot_or_render(tmp_path):
    n=Native(tmp_path);assert run(n)['processed']==1;n.token='token';n.calls=[]
    result=run(n)
    assert result['skipped']==1 and result['processed']==0 and result['restore']['state']=='not-needed'
    assert not any(op in ('save_as','remove_group','screenshot') for op,args in n.calls)


def test_unprovable_cached_revision_does_not_starve_missing_later_items(tmp_path):
    n=Native(tmp_path);n.rows.append(dict(n.rows[0],id='second',resource='Clothing/Tops/N00/z',selectable_preset_ids=['clothing/Tops/second']))
    assert run(n,limit=1)['processed']==1;n.token='token';original=n.call
    async def native(op,args=None):
        value=await original(op,args)
        if op=='list_groups' and args.get('situation_candidate',{}).get('id')=='canon-a':
            value['situation_definition']['revision_verified']=False;value['situation_definition']['members']=None
        return value
    n.runtime._call=native;result=run(n,limit=1)
    assert result['processed']==1 and result['rows'][0]['key']=='Clothing/Tops/N00/z'


def test_active_result_cannot_redefine_the_independently_prebound_tested_type(tmp_path):
    n=Native(tmp_path);original=n.call
    async def native(op,args=None):
        value=await original(op,args)
        if op=='apply_preset':n.groups[-1]['type']='TransferableGroupType.N00.Level1.Glasses'
        return value
    n.runtime._call=native;result=run(n)
    assert result['processed']==0 and n.capture_count==0


def test_partial_custom_rescan_cannot_select_historical_unobserved_registration(tmp_path):
    from test_preset_catalog import custom,SOURCE
    s=PresetCatalog(tmp_path/'preset_cache');s.sync([custom()],SOURCE,{'builtin':True,'custom':True})
    receipt=s.sync([],SOURCE,{'builtin':True,'custom':False})
    assert s.get(s.search(kind='custom')[0]['key'])['status']=='unknown'
    assert s._situation_snapshot('Custom/Tops',receipt['scan_id'])['rows']==[]


def test_offline_preferred_image_drops_stale_framing_after_independent_change(tmp_path):
    n=Native(tmp_path);assert run(n)['processed']==1
    s=PresetCatalog(tmp_path/'preset_cache');s.set_framing('Clothing/Tops',yaw=90)
    with pytest.raises(ValueError,match='UNAVAILABLE'):s.resolve_image(n.rows[0]['resource'])


def test_single_color_subject_on_transparent_background_is_not_a_uniform_frame():
    from vroid_mcp.texture_mapping import png_rgba
    from vroid_mcp.situation_proof import raster_evidence
    rgba=bytearray(512*512*4)
    for y in range(100,400):
        for x in range(200,300):rgba[(y*512+x)*4:(y*512+x)*4+4]=b'\x12\x34\x56\xff'
    assert raster_evidence(png_rgba(512,512,bytes(rgba)))['verified'] is True


def test_later_row_cannot_inherit_anatomy_changed_by_previous_set(tmp_path):
    n=Native(tmp_path);n.rows[0]['is_set_item']=True
    n.rows.append(dict(n.rows[0],id='second',resource='Clothing/Tops/N00/z',is_set_item=False,
        selectable_preset_ids=['clothing/Tops/second']))
    n.groups.append(group('original-iris','Iris',False));original=n.call
    root=group('canon-a','ClothingSet',resource=n.rows[0]['resource']);iris=group('set-iris','Iris',False,resource='set/iris')
    async def native(op,args=None):
        value=await original(op,args)
        if op=='list_groups' and args.get('situation_candidate',{}).get('id')=='canon-a':
            value['situation_definition']={'verified':True,'revision_verified':True,'root':root,'members':[root,iris]}
        if op=='apply_preset' and args['preset_id']==n.rows[0]['selectable_preset_ids'][0]:
            n.groups=[g for g in n.groups if g['type'] not in (iris['type'],root['type']) and g['id']!='canon-a']
            n.groups.extend(deepcopy([root,iris]))
        if op=='list_groups' and args.get('situation_root',{}).get('id')=='canon-a':
            value['situation_membership']={'verified':True,'revision_verified':True,'root':root,'members':[root,iris]}
        return value
    n.runtime._call=native;result=run(n)
    assert result['processed']==1 and n.capture_count==1 and len(result['rows'])==2
    assert 'ORIGINAL_ANATOMY_CHANGED' in str(result['errors'])
    assert result['restore']['state']=='restored'


def test_failure_to_acquire_generation_pin_refuses_before_any_clear(tmp_path,monkeypatch):
    import vroid_mcp.runtime_situation as module
    from contextlib import contextmanager
    @contextmanager
    def unavailable(*args):raise OSError('generation pin unavailable');yield
    monkeypatch.setattr(module,'pinned_application',unavailable)
    n=Native(tmp_path);result=run(n)
    assert not n.removed and n.capture_count==0 and result['errors']


def test_cached_set_child_revision_drift_forces_regeneration(tmp_path):
    n=Native(tmp_path);n.rows[0]['is_set_item']=True;version=['1'];original=n.call
    def members():
        return [group('canon-a','ClothingSet',resource=n.rows[0]['resource']),
                dict(group('set-top','Tops',resource='set/top'),revision=version[0])]
    async def native(op,args=None):
        value=await original(op,args)
        if op=='list_groups' and args.get('situation_candidate'):
            gs=members();value['situation_definition']={'verified':True,'revision_verified':True,'root':gs[0],'members':gs}
        if op=='apply_preset':
            n.groups=[g for g in n.groups if g['id']!='canon-a'];n.groups.extend(members())
        if op=='list_groups' and args.get('situation_root'):
            gs=members();value['situation_membership']={'verified':True,'revision_verified':True,'root':gs[0],'members':gs}
        return value
    n.runtime._call=native;assert run(n)['processed']==1
    n.token='token';version[0]='2';result=run(n)
    assert result['processed']==1 and result['skipped']==0 and n.capture_count==2
