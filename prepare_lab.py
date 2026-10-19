"""Create a disposable VRoid lab from a local installation.

The source installation is only read. The lab is a byte-verified copy under
`<lab>/app` plus a manifest of what was copied, so a later acceptance run can
prove it is still the same build.

    python prepare_lab.py --source "C:/Program Files/VRoid Studio" --lab D:/vroidmcp/lab-test
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import sys

from vroid_mcp.supported_builds import validate_assembly

APP = 'app'
MANIFEST = 'source-manifest.json'


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_directories(source: pathlib.Path, lab: pathlib.Path) -> None:
    if lab == source or lab.is_relative_to(source) or source.is_relative_to(lab):
        raise ValueError('The lab and the source installation must be separate directories')
    if lab.exists():
        raise FileExistsError('The lab already exists; a new lab is required and nothing is replaced')


def check_install(source: pathlib.Path) -> str:
    executable = source / 'VRoidStudio.exe'
    assembly = source / 'GameAssembly.dll'
    if not executable.is_file() or not assembly.is_file():
        raise FileNotFoundError(f'Not a VRoid Studio installation: {source}')
    return validate_assembly(assembly)


def inventory(source: pathlib.Path) -> list[dict]:
    files = sorted(path for path in source.rglob('*') if path.is_file())
    for path in source.rglob('*'):
        if path.resolve() != path:
            raise ValueError(f'The source contains a link or junction, inspect it first: {path}')
    return [{'path': str(path.relative_to(source)), 'size': path.stat().st_size, 'sha256': digest(path)}
            for path in files]


def copy_and_verify(source: pathlib.Path, lab: pathlib.Path, manifest: list[dict]) -> None:
    lab.mkdir(parents=True, exist_ok=False)
    shutil.copytree(source, lab / APP, copy_function=shutil.copy2)
    for entry in manifest:
        copied = lab / APP / entry['path']
        if digest(copied) != entry['sha256']:
            raise RuntimeError(f'Copy hash mismatch: {entry["path"]}')
    (lab / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', required=True, type=pathlib.Path,
                        help='VRoid Studio installation to copy (read only)')
    parser.add_argument('--lab', required=True, type=pathlib.Path,
                        help='new lab directory; must not exist')
    args = parser.parse_args(argv)

    source = args.source.resolve()
    lab = args.lab.resolve()
    check_directories(source, lab)
    build = check_install(source)
    manifest = inventory(source)
    copy_and_verify(source, lab, manifest)
    print(f'Copied and verified {len(manifest)} files into {lab} ({build})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
