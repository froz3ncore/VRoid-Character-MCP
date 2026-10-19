import pytest

from vroid_mcp.supported_builds import supported_build, validate_assembly


@pytest.mark.parametrize('digest', [
    '793eb5fcff3093f344ee930fbfa0c0796ed7780ac91c45bdb7ce6bd34d62fd3c',
    'ed65ebbc1e806db635566347a9022b9577f6b3d373db128ea23f0e862e005296',
])
def test_known_214_builds_remain_accepted(digest):
    assert '2.14.0' in supported_build(digest)


def test_previous_212_build_is_rejected():
    with pytest.raises(ValueError, match='Untested VRoid binary'):
        supported_build('475334B2C9BD76A53754EEEEEEDB523CBB95DC832033A61ED8041B7F3BF4C1FF')


def test_unknown_file_is_rejected(tmp_path):
    assembly = tmp_path / 'GameAssembly.dll'
    assembly.write_bytes(b'unknown binary')
    with pytest.raises(ValueError, match='Untested VRoid binary'):
        validate_assembly(assembly)
