import asyncio
import base64
import json
import struct
import zlib

import pytest

from vroid_mcp.preset_labels import DATA, labels, name_catalog, name_preset
from vroid_mcp.preset_previews import decode_thumbnail, validate_request
from vroid_mcp.runtime import Runtime


def png(width=2, height=2):
    def chunk(kind, data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\xff\0\0\xff'*width)*height))+chunk(b'IEND',b'')


def thumbnail(preset_id='hair/example', **changes):
    return {'model_token':'token','preset_id':preset_id,'ok':True,'completed':True,
            'width':2,'height':2,'source':'native_thumbnail',
            'base64':base64.b64encode(png()).decode(),**changes}


def test_bundled_labels_are_verbatim_pinned_mit_data():
    import hashlib
    source=json.loads((DATA/'source.json').read_text(encoding='utf-8'))
    assert source['commit']=='a6b0719d01fa6cac9a857956907243d9916390b2'
    assert len(labels())==1363 and len(source['files'])==35
    assert 'MIT License' in (DATA/'LICENSE').read_text(encoding='utf-8')
    for item in source['files']:
        assert hashlib.sha256((DATA/item['file']).read_bytes()).hexdigest()==item['sha256']


def test_names_preserve_native_identity_and_existing_labels():
    resource,name=next(iter(labels().items()))
    original={'id':'face/stable-id','label':'native code','resource_name':resource,'selected':True}
    named=name_preset(original)
    assert named['name']==name and named['name_source']=='brainrom_labels'
    assert all(named[k]==v for k,v in original.items()) and 'name' not in original
    assert name_catalog({'next_offset':200,'presets':[original]})['next_offset']==200


@pytest.mark.parametrize('resource',[None,'custom/resource','missing'])
def test_unknown_or_clear_names_fall_back_without_guessing(resource):
    p=name_preset({'id':'hair/x','label':'native','resource_name':resource})
    assert p['name']=='native' and p['name_source']=='native_label' and p['name_language'] is None


@pytest.mark.parametrize('token,area,ids',[
    ('','hair',['hair/x']),('token','other',['other/x']),('token','hair',[]),
    ('token','hair',['hair/x']*2),('token','hair',['hair/'+str(i) for i in range(7)]),
    ('token','hair',['face/x']),('token','hair',[None]),('token','hair','hair/x'),
])
def test_invalid_preview_request_never_reaches_native(tmp_path,token,area,ids):
    r=Runtime(tmp_path)
    async def forbidden(*args):raise AssertionError('Invalid request reached native')
    r._call=forbidden
    with pytest.raises(ValueError):asyncio.run(r.preview_presets(token,area,ids))


@pytest.mark.parametrize('changes',[
    {'model_token':'other'},{'preset_id':'hair/other'},{'width':3},
    {'base64':'not base64'},{'base64':base64.b64encode(b'not PNG').decode()},
    {'base64':base64.b64encode(png(513,1)).decode(),'width':513,'height':1},
])
def test_thumbnail_identity_and_payload_are_validated(changes):
    with pytest.raises(ValueError):decode_thumbnail(thumbnail(**changes),'token','hair/example')


def test_thumbnail_returns_verified_hash_without_transport_data():
    import hashlib
    metadata,data=decode_thumbnail(thumbnail(),'token','hair/example')
    assert data==png() and metadata['sha256']==hashlib.sha256(data).hexdigest()
    assert 'base64' not in metadata and metadata['bytes']==len(data)


def runtime(tmp_path,native):
    r=Runtime(tmp_path)
    r._call=native
    async def settle(*args):return {'model_token':'token'}
    r._settle=settle
    return r


def test_unknown_batch_rejects_before_preparing_any_resources(tmp_path):
    async def native(operation,args):
        assert operation=='list_presets'
        return {'model_token':'token','presets':[{'id':'hair/known'}],'next_offset':None}
    with pytest.raises(ValueError,match='UNKNOWN_PRESET'):
        asyncio.run(runtime(tmp_path,native).preview_presets('token','hair',['hair/known','hair/missing']))


def test_mixed_batch_preserves_order_and_reports_clear_without_fake_image(tmp_path):
    async def native(operation,args):
        if operation=='list_presets':return {'model_token':'token','next_offset':None,'presets':[
            {'id':'hair/none','label':'None','resource_name':None},
            {'id':'hair/example','label':'Example','resource_name':'resource'}]}
        assert operation=='preset_preview_begin'
        if args['preset_id']=='hair/none':return {'model_token':'token','preset_id':'hair/none','completed':True,'ok':False,'error':'NO_PREVIEW_CLEAR'}
        return thumbnail()
    manifest,images=asyncio.run(runtime(tmp_path,native).preview_presets('token','hair',['hair/none','hair/example']))
    assert [p['id'] for p in manifest['presets']]==['hair/none','hair/example']
    assert manifest['presets'][0]['error']=='NO_PREVIEW_CLEAR' and len(images)==1
    assert images[0][0]=='hair/example' and list(tmp_path.iterdir())==[]


def test_async_preview_pagination_and_handle_cleanup(tmp_path):
    calls=[]
    async def native(operation,args):
        calls.append((operation,args))
        if operation=='list_presets':return {'model_token':'token',
            'presets':[] if args['offset']==0 else [{'id':'hair/example','label':'Example'}],
            'next_offset':200 if args['offset']==0 else None}
        if operation=='preset_preview_begin':return {'completed':False,'request_id':'request'}
        if operation=='preset_preview_poll':return thumbnail(source='native_preview')
        assert operation=='preset_preview_cancel' and args['request_id']=='request'
        return {'released':False}
    manifest,images=asyncio.run(runtime(tmp_path,native).preview_presets('token','hair',['hair/example']))
    assert images and manifest['presets'][0]['source']=='native_preview'
    assert [args['offset'] for op,args in calls if op=='list_presets']==[0,200]
    assert calls[-1][0]=='preset_preview_cancel'


def test_async_preview_wrong_identity_releases_handle(tmp_path):
    calls=[]
    async def native(operation,args):
        calls.append(operation)
        if operation=='list_presets':return {'model_token':'token','next_offset':None,'presets':[{'id':'hair/example'}]}
        if operation=='preset_preview_begin':return {'completed':False,'request_id':'request'}
        if operation=='preset_preview_poll':return thumbnail(model_token='other')
        assert operation=='preset_preview_cancel'
    with pytest.raises(ValueError,match='identity mismatch'):
        asyncio.run(runtime(tmp_path,native).preview_presets('token','hair',['hair/example']))
    assert calls[-1]=='preset_preview_cancel'
