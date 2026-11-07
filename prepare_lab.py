"""Create a disposable VRoid lab from a local installation.

The source installation is only read. The lab is a byte-verified copy under
`<lab>/app` plus a manifest of what was copied, so a later acceptance run can
prove it is still the same build.

    python prepare_lab.py --source "C:/Program Files/VRoid Studio" --lab D:/vroidmcp/lab-test
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import stat
import sys

from vroid_mcp.supported_builds import file_sha256, validate_assembly

APP = 'app'
MANIFEST = 'source-manifest.json'


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


def physical_mode(path: pathlib.Path) -> int:
    info = path.lstat()
    if path.resolve() != path or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ValueError(f'Installation contains a link or reparse point: {path}')
    return info.st_mode


def physical_layout(source: pathlib.Path) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
    directories, files = [], []
    def fail(error):
        raise error
    for directory, children, names in os.walk(source, onerror=fail, followlinks=False):
        parent = pathlib.Path(directory)
        physical_mode(parent)
        for name in children:
            child = parent / name
            if not stat.S_ISDIR(physical_mode(child)):
                raise ValueError(f'Installation directory changed: {child}')
            directories.append(child)
        for name in names:
            path = parent / name
            if not stat.S_ISREG(physical_mode(path)):
                raise ValueError(f'Installation file is not regular: {path}')
            files.append(path)
    return directories, sorted(files)


def inventory(source: pathlib.Path) -> list[dict]:
    _, files = physical_layout(source)
    return [{'path': str(path.relative_to(source)), 'size': path.stat().st_size, 'sha256': file_sha256(path)}
            for path in files]


def copy_and_verify(source: pathlib.Path, lab: pathlib.Path, manifest: list[dict], build: str) -> None:
    directories, files = physical_layout(source)
    if [str(path.relative_to(source)) for path in files] != [entry['path'] for entry in manifest]:
        raise ValueError('Source file inventory changed during preparation; use a new lab')
    lab.mkdir(parents=True, exist_ok=False)
    app = lab / APP
    app.mkdir()
    for directory in directories:
        (app / directory.relative_to(source)).mkdir()
    # Copy only enumerated members. New plugins cannot enter via a second
    # recursive traversal. A file replaced with a link fails validation.
    for path in files:
        physical_mode(path)
        shutil.copy2(path, app / path.relative_to(source), follow_symlinks=False)
    if inventory(app) != manifest:
        raise RuntimeError('Copy file inventory, size or hash mismatch; use a new lab')
    if check_install(lab / APP) != build:
        raise ValueError('VRoid build changed during preparation; use a new lab')
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
    copy_and_verify(source, lab, manifest, build)
    print(f'Copied and verified {len(manifest)} files into {lab} ({build})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
