import pytest

from vroid_mcp import supported_builds

from vroid_mcp.supported_builds import assembly_identity, supported_build, validate_assembly


STEAM_216 = '3334b166e298682eeda1ca1c5ca568b12f7085b76cc629668fe8b192af816bd8'
METADATA_216 = '089fe945572695f0592e04abaae096c54f7ea74a382a3ce68440e0425b8486b8'
PIXIV_214 = 'ed65ebbc1e806db635566347a9022b9577f6b3d373db128ea23f0e862e005296'
PIXIV_216 = 'c8daa116938b40896e3a09208bbde71604a92d5ca6d86f9ff8b89fea3c1a5ad2'
METADATA_214 = '5c018d995e25b59677c9c4bb9171746d742ca94d9ed9c236b972ebca65493b8e'
UPSTREAM_214 = '793eb5fcff3093f344ee930fbfa0c0796ed7780ac91c45bdb7ce6bd34d62fd3c'


@pytest.mark.parametrize('assembly,metadata,version', [
    (STEAM_216, METADATA_216, '2.16.0'),
    (PIXIV_216, METADATA_216, '2.16.0'),
    (PIXIV_216, METADATA_214, None),
    (PIXIV_214, METADATA_214, '2.14.0'),
    (STEAM_216, METADATA_214, None),
    (PIXIV_214, METADATA_216, None),
    (STEAM_216, 'unknown metadata', None),
    (UPSTREAM_214, METADATA_216, None),
    (UPSTREAM_214, 'legacy metadata without a published pin', '2.14.0'),
])
def test_assembly_and_metadata_pair(tmp_path, monkeypatch, assembly, metadata, version):
    # Tiny stand-ins for the copyrighted artifacts. Only replace hashing.
    monkeypatch.setattr(supported_builds, 'file_sha256', lambda path: path.read_text(encoding='ascii'))
    dll = tmp_path / 'GameAssembly.dll'
    dat = tmp_path / 'VRoidStudio_Data/il2cpp_data/Metadata/global-metadata.dat'
    dat.parent.mkdir(parents=True)
    dll.write_bytes(assembly.encode('ascii'))
    dat.write_bytes(metadata.encode('ascii'))
    if version is None:
        with pytest.raises(ValueError, match='metadata'):
            validate_assembly(dll)
    else:
        result = assembly_identity(dll)
        assert version in result['build']
        assert result['metadata_sha256'] == metadata


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
