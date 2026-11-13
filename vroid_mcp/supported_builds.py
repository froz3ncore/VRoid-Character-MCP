"""Exact assembly allowlist; unknown builds must not receive native calls.

Admission stays the guarded set verified on this repository: two 2.14.0
fingerprints and the pixiv-signed 2.16.0 standalone. The Steam 2.16.0
assembly identified by the BunnyBlack migration is intentionally absent.
Packages with a published metadata pin must match it, so a 2.16 DLL cannot
be paired with another release's IL2CPP metadata.
"""
import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Build:
    version: str
    distribution: str
    metadata: str | None

    @property
    def label(self) -> str:
        return f'VRoid Studio {self.version} ({self.distribution})'


METADATA_PATH = Path('VRoidStudio_Data/il2cpp_data/Metadata/global-metadata.dat')
METADATA_216 = '089fe945572695f0592e04abaae096c54f7ea74a382a3ce68440e0425b8486b8'
BUILDS = {
    '793eb5fcff3093f344ee930fbfa0c0796ed7780ac91c45bdb7ce6bd34d62fd3c': Build(
        '2.14.0', 'upstream verified build', None),
    'ed65ebbc1e806db635566347a9022b9577f6b3d373db128ea23f0e862e005296': Build(
        '2.14.0', 'pixiv-signed standalone build',
        '5c018d995e25b59677c9c4bb9171746d742ca94d9ed9c236b972ebca65493b8e'),
    'c8daa116938b40896e3a09208bbde71604a92d5ca6d86f9ff8b89fea3c1a5ad2': Build(
        '2.16.0', 'pixiv-signed standalone build', METADATA_216),
}
SUPPORTED_ASSEMBLIES = {key: build.label for key, build in BUILDS.items()}


def supported_build(digest: str) -> str:
    """Look up an assembly label. Native admission requires assembly_identity()."""
    try:
        return SUPPORTED_ASSEMBLIES[digest.lower()]
    except KeyError:
        raise ValueError('Untested VRoid binary: refusing native calls') from None


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_assembly(path: Path) -> dict:
    """Return the observed identity even when the files fail admission."""
    if path.resolve() != path.absolute():
        raise ValueError('Linked GameAssembly.dll: refusing native calls')
    value = file_sha256(path)
    result = {'sha256': value}
    build = BUILDS.get(value)
    if not build:
        return {**result, 'error': 'Untested VRoid binary: refusing native calls'}
    metadata = path.parent / METADATA_PATH
    if metadata.resolve() != metadata.absolute() or not metadata.is_file():
        return {**result, 'error': 'Missing or linked IL2CPP metadata'}
    result['metadata_sha256'] = file_sha256(metadata)
    if build.metadata and result['metadata_sha256'] != build.metadata:
        return {**result, 'expected_metadata_sha256': build.metadata,
                'error': 'IL2CPP metadata mismatch: refusing native calls'}
    # Upstream published only the original 2.14 DLL digest. Preserve that
    # route, while refusing metadata positively identified as another release.
    if not build.metadata and any(b.version != build.version and b.metadata == result['metadata_sha256']
                                  for b in BUILDS.values()):
        return {**result, 'error': 'IL2CPP metadata belongs to a different release'}
    return {**result, 'build': build.label}


def assembly_identity(path: Path) -> dict:
    result = inspect_assembly(path)
    if 'error' in result:
        raise ValueError(result['error'])
    return result


def validate_assembly(path: Path) -> str:
    return assembly_identity(path)['build']
