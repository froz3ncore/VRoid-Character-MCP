"""Freeze and verify the exposed tool set without starting VRoid.

`create_server` builds the FastMCP object and registers every tool, but the
runtime is only started later in the ASGI lifespan, so listing tools here is
pure schema work.

    python tools/tool_manifest.py            # compare with tools/expected-tools.json
    python tools/tool_manifest.py --write    # regenerate the baseline
    python tools/tool_manifest.py --json out.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys

PROJECT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from vroid_mcp import toolset  # noqa: E402
from vroid_mcp.server import create_server  # noqa: E402

BASELINE = PROJECT / 'tools' / 'expected-tools.json'


def collect() -> dict:
    # The lab path is never touched during tool registration.
    server = create_server(PROJECT / 'lab', 'F00', None)
    tools = asyncio.run(server.list_tools())
    return toolset.manifest(tools)


def diff(expected: dict, actual: dict) -> list[str]:
    problems: list[str] = []
    if expected.get('schema') != actual['schema']:
        problems.append(f"schema {expected.get('schema')!r} -> {actual['schema']!r}")
    old, new = expected.get('tools', {}), actual['tools']
    for name in sorted(set(new) - set(old)):
        problems.append(f'+ {name}')
    for name in sorted(set(old) - set(new)):
        problems.append(f'- {name}')
    for name in sorted(set(old) & set(new)):
        before, after = old[name], new[name]
        if before.get('parameters') != after['parameters']:
            problems.append(f'~ {name} parameters {before.get("parameters")} -> {after["parameters"]}')
        if before.get('required') != after['required']:
            problems.append(f'~ {name} required {before.get("required")} -> {after["required"]}')
    if expected.get('tool_count') != actual['tool_count']:
        problems.append(f"tool_count {expected.get('tool_count')} -> {actual['tool_count']}")
    if expected.get('toolset_hash') != actual['toolset_hash']:
        problems.append(f"toolset_hash {expected.get('toolset_hash')} -> {actual['toolset_hash']}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--write', action='store_true', help='write the current manifest as the baseline')
    parser.add_argument('--out', default=str(BASELINE),
                        help='baseline path; this interpreter cannot always write inside the repo, '
                             'so write to a scratch path and copy it in when it cannot (default: %(default)s)')
    parser.add_argument('--json', dest='json_out', default='', help='also write the full manifest here')
    args = parser.parse_args()

    actual = collect()
    if args.write:
        target = pathlib.Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(actual, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
        print(f'wrote {target} ({actual["tool_count"]} tools, {actual["toolset_hash"]})')
        return 0
    if not BASELINE.is_file():
        print(f'missing baseline {BASELINE}; run with --write first', file=sys.stderr)
        return 2
    expected = json.loads(BASELINE.read_text(encoding='utf-8'))
    problems = diff(expected, actual)
    if args.json_out:
        pathlib.Path(args.json_out).write_text(json.dumps(actual, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    if problems:
        print('tool set drifted from the baseline:', file=sys.stderr)
        for line in problems:
            print('  ' + line, file=sys.stderr)
        return 1
    print(f'tool set matches the baseline: {actual["tool_count"]} tools, {actual["toolset_hash"]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
