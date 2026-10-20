"""One manifest for the source that the delivered tool set was built from.

Earlier rounds kept a separate snapshot directory per cosmetics round (17, 19
and 153 files). This walks the current source tree instead and records every
tracked source file with its SHA-256, plus the tool set identity, so a reader
can verify a checkout against a single file. Version 2 hashes source bytes
with CRLF normalized to LF so Git's Windows checkout conversion is harmless.
Historical version 1 manifests still use exact on-disk bytes.

    python tools/source_manifest.py --write --out <scratch>/source-manifest.json

Compare an existing manifest with the working tree:

    python tools/source_manifest.py --check pipeline/source-manifest.json
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import pathlib
import sys

PROJECT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from vroid_mcp import toolset  # noqa: E402
from vroid_mcp.server import create_server  # noqa: E402

ROOTS = ['agent', 'tools', 'vroid_mcp', 'tests', 'pipeline/tools', 'pipeline/blender-addons']
SUFFIXES = {'.py', '.js', '.ps1', '.toml', '.json', '.md'}
SKIP_PARTS = {'__pycache__', 'node_modules', '.venv', 'data', 'pipeline'}
SKIP_NAMES = {'expected-tools.json', 'TOOLS.md'}


def _candidates() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for name in ('launch.py', 'prepare_lab.py', 'pyproject.toml', 'package.json', 'SCOPE.md',
                 'CHANGELOG.md', 'README.md', 'README.zh-CN.md', 'README.zh-TW.md', 'LICENSE', 'NOTICE',
                 'LICENSING.md', 'UPSTREAM.json', 'BLENDER_SETUP.zh-CN.md'):
        path = PROJECT / name
        if path.is_file():
            files.append(path)
    for root in ROOTS:
        base = PROJECT / root
        if not base.is_dir():
            continue
        for path in base.rglob('*'):
            if not path.is_file() or path.suffix not in SUFFIXES:
                continue
            relative = path.relative_to(PROJECT)
            if relative.name in SKIP_NAMES:
                continue
            if any(part in SKIP_PARTS for part in relative.parts[1:-1]):
                continue
            files.append(path)
    return sorted(set(files), key=lambda p: p.relative_to(PROJECT).as_posix())


def build(*, normalize_line_endings: bool = True) -> dict:
    entries = []
    for path in _candidates():
        raw = path.read_bytes()
        if normalize_line_endings:
            raw = raw.replace(b'\r\n', b'\n')
        entries.append({'path': path.relative_to(PROJECT).as_posix(), 'bytes': len(raw),
                        'sha256': hashlib.sha256(raw).hexdigest()})
    server = create_server(PROJECT / 'lab', 'F00', None)
    base = toolset.fingerprint(asyncio.run(server.list_tools()))
    return {'schema': ('vroid-source-manifest-v2' if normalize_line_endings
                       else 'vroid-source-manifest-v1'),
            'note': 'Replaces the per-round 17 / 19 / 153 file snapshots; verify a checkout with '
                    '--check. Assets, renders and native evidence stay local. '
                    + ('SHA-256 and byte counts normalize CRLF to LF.'
                       if normalize_line_endings else 'SHA-256 uses exact on-disk bytes.'),
            'file_count': len(entries),
            'total_bytes': sum(entry['bytes'] for entry in entries),
            'tool_count': base['tool_count'],
            'toolset_hash': base['toolset_hash'],
            'files': entries}


def check(manifest_path: pathlib.Path) -> int:
    expected = json.loads(manifest_path.read_text(encoding='utf-8'))
    if expected.get('schema') not in {'vroid-source-manifest-v1', 'vroid-source-manifest-v2'}:
        print('unsupported source manifest schema', file=sys.stderr)
        return 1
    actual = build(normalize_line_endings=expected['schema'] == 'vroid-source-manifest-v2')
    current = {entry['path']: entry['sha256'] for entry in actual['files']}
    recorded = {entry['path']: entry['sha256'] for entry in expected['files']}
    problems = []
    for field in ('tool_count', 'toolset_hash'):
        if actual[field] != expected.get(field):
            problems.append('changed: ' + field)
    for path in sorted(set(recorded) - set(current)):
        problems.append('missing: ' + path)
    for path in sorted(set(current) - set(recorded)):
        problems.append('new: ' + path)
    for path in sorted(set(current) & set(recorded)):
        if current[path] != recorded[path]:
            problems.append('changed: ' + path)
    for line in problems:
        print(line, file=sys.stderr)
    if problems:
        print(f'{len(problems)} source difference(s) against {manifest_path}', file=sys.stderr)
        return 1
    print(f'source matches {manifest_path}: {len(current)} files, '
          f"{expected['tool_count']} tools {expected['toolset_hash']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='One source manifest for the delivered tool set')
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--out', default=str(PROJECT / 'pipeline' / 'source-manifest.json'))
    parser.add_argument('--check', default='', help='verify the working tree against this manifest')
    args = parser.parse_args()
    if args.check:
        return check(pathlib.Path(args.check))
    if not args.write:
        parser.error('pass --write or --check')
    data = build()
    target = pathlib.Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"wrote {target}: {data['file_count']} files, {data['total_bytes']} bytes, "
          f"{data['tool_count']} tools {data['toolset_hash']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
