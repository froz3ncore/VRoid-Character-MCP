"""Custom metadata/hash/icon must all describe one protected file generation."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import zipfile

import pytest

from vroid_mcp.custom_item_file import inspect_custom_item
from vroid_mcp.preset_catalog import PresetCatalog
from vroid_mcp.runtime import Runtime


def archive(path,identity,side):
    from test_preset_previews import png
    with zipfile.ZipFile(path,'w') as output:
        output.writestr('v1customitem/meta.json',json.dumps({'rootTransferableGroupId':identity,'rootTransferableGroupTypeId':'Tops'}).encode('utf-8'))
        output.writestr('thumbnails/thumbnail.png',png(side,side))


@pytest.mark.parametrize('icons',[False,True])
def test_archive_replacement_cannot_mix_native_identity_hash_and_icon(tmp_path,monkeypatch,icons):
    path=tmp_path/'registered.vroidcustomitem';other=tmp_path/'replacement.vroidcustomitem'
    archive(path,'A',2);archive(other,'B',3)
    digestA=hashlib.sha256(path.read_bytes()).hexdigest();digestB=hashlib.sha256(other.read_bytes()).hexdigest()
    original=zipfile.ZipFile.close;attempted=[]
    def close_then_replace(z):
        original(z)
        if not attempted:
            attempted.append(True)
            try:os.replace(other,path)
            except PermissionError:pass  # Windows pin denies replacement until this generation closes.
    monkeypatch.setattr(zipfile.ZipFile,'close',close_then_replace)
    item={'kind':'custom','id':'A','resource':'user/A','category':'Custom/Tops','owned':True,'usable':True,
          'selectable':True,'path':str(path),'revision':'1','group_type':'Tops','registered':True}
    r=Runtime(tmp_path)
    async def settle(*args):return {'model_token':'token'}
    async def native(op,args):
        if op=='preset_catalog_begin':return {'request_id':'scan'}
        if op=='preset_catalog_release':return {'released':True}
        if op=='preset_catalog_poll':return dict(completed=True,model_token='token',build='a'*64,
            areas=['face','body','hair','clothing'],builtin_complete=True,custom_complete=True,rows=[item])
        raise AssertionError(op)
    r._call,r._settle=native,settle
    result=asyncio.run(r.sync_preset_cache('token',icons))
    s=PresetCatalog(tmp_path/'preset_cache');records=s.search()
    assert attempted
    if os.name=='nt':assert records  # A protected valid archive remains usable.
    if records:
        assert records[0]['id']=='A' and records[0]['sha256']==digestA and records[0]['sha256']!=digestB
        if records[0]['images']:assert s.resolve_image(records[0]['key'])[0]['width']==2
    else:assert result['complete']['custom'] is False


def test_custom_inspection_hash_is_streamed_from_the_archive_descriptor(tmp_path,monkeypatch):
    path=tmp_path/'registered.vroidcustomitem';archive(path,'A',2)
    expected=hashlib.sha256(path.read_bytes()).hexdigest()
    def forbidden(*args):raise AssertionError('whole-path read separates hash generation')
    monkeypatch.setattr(Path,'read_bytes',forbidden)
    assert inspect_custom_item(path)['sha256']==expected


@pytest.mark.parametrize('mismatch',['id','type','hash'])
def test_custom_icon_rechecks_decoded_group_identity_with_hash(tmp_path,monkeypatch,mismatch):
    from vroid_mcp import runtime_catalog
    from test_preset_previews import png
    path=tmp_path/'registered.vroidcustomitem';archive(path,'A',2)
    actual=inspect_custom_item(path);calls=[]
    def inspection(*args,**kwargs):
        calls.append(kwargs)
        changed=len(calls)>1
        return {**actual,'sha256':'b'*64 if changed and mismatch=='hash' else actual['sha256'],
                'metadata':{'rootTransferableGroupId':'B' if changed and mismatch=='id' else 'A',
                            'rootTransferableGroupTypeId':'Bottoms' if changed and mismatch=='type' else 'Tops'},'icon':png()}
    monkeypatch.setattr(runtime_catalog,'inspect_custom_item',inspection)
    r=Runtime(tmp_path)
    item={'kind':'custom','id':'A','resource':'user/A','category':'Custom/Tops','owned':True,'usable':True,
          'selectable':True,'path':str(path),'revision':'1','group_type':'Tops','registered':True}
    async def settle(*args):return {'model_token':'token'}
    async def native(op,args):
        if op=='preset_catalog_begin':return {'request_id':'scan'}
        if op=='preset_catalog_release':return {'released':True}
        return dict(completed=True,model_token='token',build='a'*64,areas=['face','body','hair','clothing'],
                    builtin_complete=True,custom_complete=True,rows=[item])
    r._call,r._settle=native,settle
    assert asyncio.run(r.sync_preset_cache('token',True))['images']==0
    assert not PresetCatalog(tmp_path/'preset_cache').search()[0]['images']
