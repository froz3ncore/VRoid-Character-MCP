import os
import subprocess
import pytest
from vroid_mcp.wear_paths import wear_input,wear_destination


@pytest.mark.parametrize('name',['../x.xroid','..\\x.xroid','C:\\x.xroid','C:x.xroid',
    'a:stream.xroid','CON.xroid','con .xroid','LPT1.xroid','COM¹.xroid',
    'CONIN$.xroid','.xroid','x.xroid ','x.xroid.','x?.xroid','x\n.xroid','x\x7f.xroid','x.png',''])
def test_reject_names(tmp_path,name):
    with pytest.raises(ValueError):wear_destination(tmp_path,name)


def test_input_and_new_destination(tmp_path):
    folder=tmp_path/'saves';folder.mkdir()
    source=folder/'围裙.XWEAR';source.write_bytes(b'original')
    assert wear_input(tmp_path,source.name,('.xwear',))==source
    assert wear_destination(tmp_path,'新装配.XROID')==folder/'新装配.XROID'
    assert source.read_bytes()==b'original'


def test_existing_preserved_and_wrong_input_rejected(tmp_path):
    target=wear_destination(tmp_path,'saved.xroid');target.write_bytes(b'keep')
    with pytest.raises(FileExistsError):wear_destination(tmp_path,target.name)
    assert target.read_bytes()==b'keep'
    with pytest.raises(ValueError):wear_input(tmp_path,target.name,('.xwear',))
    with pytest.raises(FileNotFoundError):wear_input(tmp_path,'missing.xwear',('.xwear',))
    directory=tmp_path/'saves'/'directory.xwear';directory.mkdir()
    with pytest.raises(FileNotFoundError):wear_input(tmp_path,directory.name,('.xwear',))


def test_target_symlink_rejected_even_when_dangling(tmp_path):
    folder=tmp_path/'saves';folder.mkdir();link=folder/'link.xroid'
    try:link.symlink_to(tmp_path/'missing.xroid')
    except OSError as error:pytest.skip('Windows symlink privilege unavailable: '+str(error))
    with pytest.raises(ValueError):wear_destination(tmp_path,link.name)
    with pytest.raises(ValueError):wear_input(tmp_path,link.name,('.xroid',))


@pytest.mark.skipif(os.name!='nt',reason='Windows junction boundary')
def test_saves_junction_escape_rejected(tmp_path):
    lab=tmp_path/'lab';lab.mkdir();outside=tmp_path/'outside';outside.mkdir()
    link=lab/'saves'
    result=subprocess.run(['cmd','/c','mklink','/J',str(link),str(outside)],capture_output=True)
    if result.returncode:pytest.skip('Junction creation unavailable')
    (outside/'input.xwear').write_bytes(b'keep')
    with pytest.raises(ValueError):wear_input(lab,'input.xwear',('.xwear',))
    with pytest.raises(ValueError):wear_destination(lab,'output.xroid')
    assert not (outside/'output.xroid').exists()
