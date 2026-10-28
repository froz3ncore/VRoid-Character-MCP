import asyncio
import hashlib
import zipfile
import pytest
from vroid_mcp.file_paths import file_input, file_destination
from vroid_mcp.runtime import Runtime


def test_absolute_paths_require_attachment_and_no_overwrite(tmp_path):
    source=tmp_path/'model.vroid';source.write_bytes(b'original')
    with pytest.raises(ValueError):file_input(tmp_path,str(source),('.vroid',))
    assert file_input(tmp_path,str(source),('.vroid',),True)==source
    with pytest.raises(FileExistsError):file_destination(tmp_path,str(source),'.vroid',True)
    with pytest.raises(ValueError):file_destination(tmp_path,str(tmp_path/'missing'/'new.vroid'),'.vroid',True)


def test_new_character_refuses_without_discard_before_any_native_call(tmp_path):
    r=Runtime(tmp_path);r.mode='attached'
    async def bad(*a):raise AssertionError('must not dispatch')
    r._call=bad
    with pytest.raises(ValueError,match='EXPLICIT_DISCARD'):
        asyncio.run(r.new_character('model','F00',False))


def test_in_place_save_preserves_exact_original_before_dispatch(tmp_path):
    r=Runtime(tmp_path);r.mode='attached'
    target=tmp_path/'original.vroid';target.write_bytes(b'original bytes')
    original=target.read_bytes()
    async def settled(*a):return {'attached_state':{'file_path':str(target),'command_revision':3}}
    async def call(op,args):
        assert op=='save_character' and args['path']==str(target)
        backups=list((tmp_path/'saves').glob('before-save-*.vroid'))
        assert len(backups)==1 and backups[0].read_bytes()==original
        with zipfile.ZipFile(target,'w') as z:z.writestr('model','updated')
        return {'saved':True}
    r._settled_for,r._call=settled,call
    result=asyncio.run(r.save_character('model'))
    assert result['previous_sha256']==hashlib.sha256(original).hexdigest()
    assert result['sha256']!=result['previous_sha256']
