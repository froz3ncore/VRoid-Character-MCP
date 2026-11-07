"""Persistent catalog contracts, using actual files and cross-process locks."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


def store(tmp_path):
    from vroid_mcp.preset_catalog import PresetCatalog
    return PresetCatalog(tmp_path / 'preset_cache')


def row(resource='Clothing/Tops/N00/a', **changes):
    return dict(kind='builtin', resource=resource, category='Clothing/Tops', id='model-1/'+resource.rsplit('/',1)[-1],
                owned=True, usable=True, selectable=True, name='Native top', **changes)


def custom(path='a/x.vroidcustomitem', revision='1', **changes):
    return dict(kind='custom', resource='user/item', path=path, revision=revision,
                category='Custom/Tops', id='temporary/custom', name='Custom',
                owned=True, usable=True, selectable=True, **changes)


SOURCE = {'build': 'a'*64, 'session': 'model-1'}


def sync(s, rows, complete=None):
    return s.sync(rows, SOURCE, complete or {'builtin': True, 'custom': True})


def test_construction_and_empty_reads_are_lazy(tmp_path):
    s = store(tmp_path / 'absent')
    assert s.search() == []
    assert s.get_framing('Clothing/Tops')['distance'] == 3.3
    assert not (tmp_path / 'absent').exists()


def test_identity_annotations_and_revision_lifecycle(tmp_path):
    s = store(tmp_path)
    sync(s, [row(), custom()])
    builtin, item = s.search()[0], s.search(kind='custom')[0]
    key = item['key']
    s.annotate(key, 'Author', label='Manual', description='soft red fabric', tags=['Cute'], colors=['RED'])
    s.annotate(key, 'Author', tags=['warm'], colors=['blue'])
    changed = custom(revision='2'); changed['id'] = 'model-2/new-id'
    new_model_builtin=row();new_model_builtin['id']='model-2/new-option-token'
    sync(s, [new_model_builtin, changed])
    item = s.search(kind='custom')[0]
    assert item['key'] == key and item['label'] == 'Manual' and item['status'] == 'changed'
    assert item['tags'] == ['cute', 'warm'] and item['colors'] == ['red', 'blue']
    assert len(item['annotations']) == 2 and item['history']
    assert item['fingerprint'] != item['history'][0]['fingerprint']
    assert s.search(kind='builtin')[0]['key'] == builtin['key']
    sync(s, [row(), changed])
    assert s.search(kind='custom')[0]['status'] == 'unchanged'
    sync(s, [row()], {'builtin': True, 'custom': False})
    assert s.search(kind='custom')[0]['status'] == 'unknown'
    sync(s, [row()])
    assert not s.search(kind='custom')
    assert s.search(kind='custom', include_removed=True)[0]['status'] == 'removed'
    sync(s, [row(), changed])
    assert s.search(kind='custom')[0]['status'] == 'returned'
    s.annotate(key, 'Author', tags=[], colors=[], replace=True)
    assert s.search(kind='custom')[0]['tags'] == []
    assert s.search(kind='custom')[0]['colors'] == []
    assert store(tmp_path).search(kind='custom')[0]['label'] == 'Manual'


def test_copy_identity_uses_full_path_and_duplicate_conflicts_fail_atomically(tmp_path):
    s = store(tmp_path)
    sync(s, [custom('folder-a/x.vroidcustomitem'), custom('folder-b/x.vroidcustomitem')])
    assert len({r['key'] for r in s.search()}) == 2
    before = s.path.read_bytes()
    for invalid in ([row(), row()], [custom(), custom()], [row(resource='')]):
        with pytest.raises(ValueError): sync(s, invalid)
        assert s.path.read_bytes() == before


def test_conflicting_builtin_native_ids_fail_atomically(tmp_path):
    s=store(tmp_path);sync(s,[row()]);before=s.path.read_bytes()
    conflict=row('Clothing/Tops/N00/b');conflict['id']=row()['id']
    with pytest.raises(ValueError):sync(s,[row(),conflict])
    assert s.path.read_bytes()==before


@pytest.mark.parametrize('field,value',[('manual_label',{}),('description',[]),('tags',[{}]),
    ('annotations',[{}]),('history',[{}]),('images',{'native-icon':{'path':'../escape.png'}})])
def test_malformed_record_fields_refuse_even_unrelated_writes(tmp_path,field,value):
    s=store(tmp_path);sync(s,[row()]);data=json.loads(s.path.read_text(encoding='utf-8'))
    key=next(iter(data['presets']));data['presets'][key][field]=value
    broken=json.dumps(data).encode('utf-8');s.path.write_bytes(broken)
    with pytest.raises(ValueError):s.annotate(key,'Me',label='new')
    assert s.path.read_bytes()==broken


def test_byte_change_under_same_custom_revision_changes_fingerprint(tmp_path):
    s=store(tmp_path);sync(s,[custom(sha256='a'*64)]);old=s.search()[0]
    sync(s,[custom(sha256='b'*64)])
    assert s.get(old['key'])['status']=='changed'


def test_cached_image_symlink_escape_is_refused(tmp_path):
    from test_preset_previews import png
    s=store(tmp_path);sync(s,[row()]);item=s.search()[0]
    image=s.publish_image(item['key'],png(),{'kind':'native-icon','source':'test'},item['fingerprint'])
    destination=s.root/image['path'];destination.unlink()
    outside=tmp_path/'outside.png';outside.write_bytes(png())
    try:destination.symlink_to(outside)
    except OSError:pytest.skip('host lacks symlink privilege')
    with pytest.raises(ValueError):s.resolve_image(item['key'])


def test_all_words_combined_filters_and_limits(tmp_path):
    s = store(tmp_path)
    locked = row('Clothing/Tops/N00/b'); locked.update(owned=False, usable=False, selectable=False)
    sync(s, [row(), locked, custom()])
    key = s.search(kind='custom')[0]['key']
    s.annotate(key, 'Me', label='Soft top', description='red silk')
    assert len(s.search('soft silk', category='Custom/Tops', kind='custom', annotated_only=True,
                        status='new', include_locked=False, limit=1)) == 1
    assert s.search('soft wool') == []
    assert len(s.search(include_locked=True)) == 3
    assert len(s.search()) == 2
    for kwargs in ({'limit': True}, {'limit': 0}, {'limit': 201}, {'kind': 'bad'},
                   {'status': 'bad'}, {'category': '../../escape'}, {'query': None}, {'include_locked': 'yes'}):
        with pytest.raises(ValueError): s.search(**kwargs)
    for kwargs in ({'author': ''}, {'author': 'a', 'tags': 'bad'}, {'author': 'a', 'replace': 1}):
        with pytest.raises(ValueError): s.annotate(key, **kwargs)


@pytest.mark.parametrize('bad', [b'{', b'{}', b'{"schema":999,"presets":{}}',
                               b'{"schema":1,"presets":{"x":{}}}'])
def test_corrupt_store_is_never_overwritten(tmp_path, bad):
    s = store(tmp_path); s.root.mkdir()
    s.path.write_bytes(bad)
    with pytest.raises(ValueError): s.search()
    with pytest.raises(ValueError): sync(s, [row()])
    assert s.path.read_bytes() == bad


@pytest.mark.parametrize('field,value',[('schema',True),('source',None),('updated',[]),('fingerprint','bad'),('completeness',{})])
def test_malformed_catalog_header_is_not_rewritten(tmp_path,field,value):
    s=store(tmp_path);sync(s,[row()]);data=json.loads(s.path.read_text(encoding='utf-8'))
    data[field]=value;broken=json.dumps(data).encode('utf-8');s.path.write_bytes(broken)
    with pytest.raises(ValueError):sync(s,[row()])
    assert s.path.read_bytes()==broken


def test_failed_atomic_replace_preserves_prior_bytes(tmp_path, monkeypatch):
    s = store(tmp_path); sync(s, [row()]); before = s.path.read_bytes()
    def fail(*args): raise OSError('replacement failed')
    monkeypatch.setattr(os, 'replace', fail)
    with pytest.raises(OSError): s.annotate(s.search()[0]['key'], 'Me', label='new')
    assert s.path.read_bytes() == before
    assert not list(s.scratch.glob('*.tmp'))


def test_real_cross_process_lock_timeout_and_concurrent_annotation(tmp_path):
    s = store(tmp_path); sync(s, [row()]); key = s.search()[0]['key']
    # No temporary script or bytecode: child executes ASCII code and inherits project TEMP.
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', TEMP=str(tmp_path), TMP=str(tmp_path), TMPDIR=str(tmp_path))
    code = ('from pathlib import Path; from vroid_mcp.preset_catalog import PresetCatalog; '
            'import sys; s=PresetCatalog(Path(sys.argv[1]),lock_timeout=.1); '
            's.annotate(sys.argv[2],"child",tags=[sys.argv[3]])')
    with s.locked():
        p = subprocess.run([sys.executable, '-B', '-c', code, str(s.root), key, 'blocked'], env=env, capture_output=True)
        assert p.returncode != 0 and b'CATALOG_LOCK_TIMEOUT' in p.stderr
    children = [subprocess.Popen([sys.executable, '-B', '-c', code.replace('lock_timeout=.1', 'lock_timeout=5'),
                                str(s.root), key, str(i)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                for i in range(3)]
    assert all(p.communicate(timeout=15) == (b'', b'') and p.returncode == 0 for p in children)
    assert set(s.search()[0]['tags']) == {'0', '1', '2'}
    assert s.lock_path.exists()  # Lock files are never removed by stale-age heuristics.


def test_framing_defaults_overrides_fallback_and_reset_persist(tmp_path):
    s = store(tmp_path)
    original = s.get_framing('Clothing/Tops')
    assert original['distance_unit'] == 'region-span multiplier'
    s.set_framing('Clothing/Tops', top=.1, bottom=.7, half=.2, distance=.1, yaw=-360, fit='full-body')
    actual = store(tmp_path).get_framing('Custom/Tops')
    assert actual['resolved_category'] == 'Clothing/Tops' and actual['source'] == 'override'
    assert actual['half'] == .2 and actual['inactive_fields'] == ['top', 'bottom', 'half']
    s.reset_framing('Clothing/Tops')
    assert s.get_framing('Clothing/Tops') == original
    s.set_framing('Hair/Novel', yaw=90)
    assert s.get_framing('Hair/Novel')['top'] == 0
    s.reset_framing()
    assert s.get_framing('Hair/Novel')['source'] == 'default'
    original['top'] = .99
    assert s.get_framing('Clothing/Tops')['top'] == .12


@pytest.mark.parametrize('category,resolved',[('Custom/ArmAccessory','Clothing/AccessoryArm'),
    ('Custom/NeckAccessory','Clothing/AccessoryNeck'),('Custom/HairBack','Hair/Back'),
    ('Custom/HairFront','Hair'),('Custom/BaseHair','Hair'),('Custom/BodySkin','VRoid/Body')])
def test_custom_native_slot_names_resolve_exact_framing_equivalents(tmp_path,category,resolved):
    assert store(tmp_path).get_framing(category)['resolved_category']==resolved


def test_every_bundled_native_label_category_is_accepted(tmp_path):
    from vroid_mcp.preset_labels import labels
    from vroid_mcp.catalog_framing import category
    for resource in labels():
        parts=resource.split('/')
        if 'N00' in parts:
            index=parts.index('N00');category('/'.join(parts[index-2:index]))


@pytest.mark.parametrize('fields', [{'top': .8, 'bottom': .2}, {'half': 0}, {'half': True},
    {'distance': 100.1}, {'yaw': float('nan')}, {'yaw': 361}, {'fit': 'bad'}, {'extra': 1}])
def test_invalid_framing_never_writes(tmp_path, fields):
    s = store(tmp_path)
    with pytest.raises(ValueError): s.set_framing('Clothing/Tops', **fields)
    assert not s.root.exists()


def test_corrupt_framing_is_preserved(tmp_path):
    s = store(tmp_path); s.root.mkdir()
    p = s.root / 'framing_overrides.json'; p.write_bytes(b'{}')
    with pytest.raises(ValueError): s.get_framing('Clothing/Tops')
    with pytest.raises(ValueError): s.set_framing('Clothing/Tops', yaw=20)
    assert p.read_bytes() == b'{}'


def test_image_validation_provenance_and_stale_situation_fallback(tmp_path):
    from test_preset_previews import png
    s = store(tmp_path); sync(s, [row()]); item = s.search()[0]; key = item['key']
    native = {'kind': 'native-icon', 'source': 'native_thumbnail', 'model_token': 'model-1'}
    with pytest.raises(ValueError): s.publish_image(key, b'not png', native, item['fingerprint'])
    icon = s.publish_image(key, png(), native, item['fingerprint'])
    assert s.resolve_image(key)[0]['kind'] == 'native-icon'
    situation = {'kind': 'situation', 'verified': True, 'source': 'clean-render', 'framing': {'fit': 'region'}}
    image = s.publish_image(key, png(3, 3), situation, item['fingerprint'])
    assert s.resolve_image(key)[0]['kind'] == 'situation'
    (s.root / image['path']).unlink()
    assert s.resolve_image(key)[0]['kind'] == 'native-icon'
    (s.root / icon['path']).write_bytes(png(4, 4))
    with pytest.raises(ValueError): s.resolve_image(key)
    with pytest.raises(ValueError): s.publish_image(key, png(), native, 'stale')
    data = json.loads(s.path.read_text(encoding='utf-8'))
    data['presets'][key]['images']['native-icon']['path'] = '../outside.png'
    s.path.write_bytes(json.dumps(data).encode('utf-8'))
    with pytest.raises(ValueError): s.resolve_image(key)


def test_returned_changed_revision_records_history_and_invalidates_images(tmp_path):
    from test_preset_previews import png
    s=store(tmp_path); sync(s,[custom()]); item=s.search()[0]
    s.annotate(item['key'],'Me',label='Keep')
    s.publish_image(item['key'],png(),{'kind':'native-icon','source':'test'},item['fingerprint'])
    sync(s,[]); sync(s,[custom(revision='2')])
    returned=s.get(item['key'])
    assert returned['status']=='returned' and returned['manual_label']=='Keep'
    assert returned['history'][0]['revision']=='1' and returned['images']=={}


def test_interrupted_image_staging_never_publishes_partial_blob(tmp_path,monkeypatch):
    from test_preset_previews import png
    s=store(tmp_path); sync(s,[row()]); item=s.search()[0]; before=s.path.read_bytes()
    original=os.fsync
    def fail(fd): raise OSError('interrupted staging flush')
    monkeypatch.setattr(os,'fsync',fail)
    with pytest.raises(OSError): s.publish_image(item['key'],png(),{'kind':'native-icon','source':'test'},item['fingerprint'])
    assert s.path.read_bytes()==before
    assert not list((s.root/'images').glob('*.png'))
    monkeypatch.setattr(os,'fsync',original)
    s.publish_image(item['key'],png(),{'kind':'native-icon','source':'test'},item['fingerprint'])
    assert s.resolve_image(item['key'])[1]==png()


def test_image_provenance_cannot_replace_computed_byte_identity(tmp_path):
    from test_preset_previews import png
    s=store(tmp_path);sync(s,[row()]);item=s.search()[0]
    result=s.publish_image(item['key'],png(),{'kind':'native-icon','source':'test',
        'width':999,'height':999,'sha256':'x','path':'../outside.png'},item['fingerprint'])
    assert result['width']==2 and result['sha256']==hashlib.sha256(png()).hexdigest()
    assert s.resolve_image(item['key'])[1]==png()
