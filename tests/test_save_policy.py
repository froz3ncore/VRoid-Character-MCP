import pytest

from vroid_mcp.runtime import save_destination

UNSAFE = ['../old.vroid', r'C:\old.vroid', 'a/b.vroid', 'a:stream.vroid', 'CON.vroid', 'LPT1.vroid',
          '.vroid', 'old.vroid ', 'old.png', 'a?.vroid', 'a*.vroid', 'a|b.vroid', 'a\n.vroid']


@pytest.mark.parametrize('filename', UNSAFE)
def test_unsafe_save_names_are_rejected(tmp_path, filename):
    with pytest.raises((ValueError, FileExistsError)):
        save_destination(tmp_path, filename)


def test_an_existing_model_is_never_overwritten(tmp_path):
    saves = tmp_path / 'saves'
    saves.mkdir()
    original = saves / 'character.vroid'
    original.write_bytes(b'keep this character')
    with pytest.raises(FileExistsError):
        save_destination(tmp_path, 'character.vroid')
    assert original.read_bytes() == b'keep this character'


def test_a_new_name_lands_in_saves_with_unicode_intact(tmp_path):
    destination = save_destination(tmp_path, '測試角色.vroid')
    assert destination == tmp_path / 'saves' / '測試角色.vroid'
