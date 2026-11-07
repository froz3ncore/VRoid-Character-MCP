"""Exact assembly allowlist; unknown builds must not receive native calls."""
import hashlib
from pathlib import Path


SUPPORTED_ASSEMBLIES = {
    '793eb5fcff3093f344ee930fbfa0c0796ed7780ac91c45bdb7ce6bd34d62fd3c':
        'VRoid Studio 2.14.0 (upstream verified build)',
    'ed65ebbc1e806db635566347a9022b9577f6b3d373db128ea23f0e862e005296':
        'VRoid Studio 2.14.0 (pixiv-signed standalone build)',
}


def supported_build(digest: str) -> str:
    try:
        return SUPPORTED_ASSEMBLIES[digest.lower()]
    except KeyError:
        raise ValueError('Untested VRoid binary: refusing native calls') from None


def assembly_identity(path: Path) -> dict:
    """Validate the same digest supplied to build-specific native descriptors."""
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    value = digest.hexdigest()
    return {'sha256': value, 'build': supported_build(value)}


def validate_assembly(path: Path) -> str:
    return assembly_identity(path)['build']
