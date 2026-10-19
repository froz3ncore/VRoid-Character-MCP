"""Stable identity for the tool set this server exposes.

A long-running MCP client keeps whatever tool list it fetched at connect
time.  Comparing `toolset_hash` from `get_status` with the hash the client
was built against tells the operator at a glance whether the connection is
stale, without restarting anything.

The hash is derived only from tool names and their input schemas, so it is
the same value whether it is computed inside a live server or offline from
`tools/tool_manifest.py`.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

SCHEMA = 'vroid-toolset-v1'


def _row(tool: Any) -> dict[str, Any]:
    return {'name': tool.name, 'schema': tool.inputSchema or {}}


def _blob(rows: list[dict[str, Any]]) -> bytes:
    return json.dumps(rows, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def fingerprint(tools: Iterable[Any]) -> dict[str, Any]:
    """Return the canonical identity of a tool collection."""
    rows = sorted((_row(tool) for tool in tools), key=lambda row: row['name'])
    names = [row['name'] for row in rows]
    if len(set(names)) != len(names):
        raise ValueError('Duplicate tool name in the exposed tool set')
    return {'schema': SCHEMA, 'tool_count': len(rows),
            'toolset_hash': 'sha256:' + hashlib.sha256(_blob(rows)).hexdigest(),
            'tools': rows}


def manifest(tools: Iterable[Any]) -> dict[str, Any]:
    """Full per-tool detail, suitable for `tools/expected-tools.json`."""
    base = fingerprint(tools)
    entries: dict[str, Any] = {}
    for row in base['tools']:
        schema = row['schema']
        entries[row['name']] = {'parameters': sorted((schema.get('properties') or {}).keys()),
                                'required': sorted(schema.get('required') or [])}
    return {'schema': SCHEMA, 'tool_count': base['tool_count'], 'toolset_hash': base['toolset_hash'],
            'tools': entries}


def summary(tools: Iterable[Any]) -> dict[str, Any]:
    base = fingerprint(tools)
    return {'tool_count': base['tool_count'], 'toolset_hash': base['toolset_hash'],
            'toolset_schema': base['schema']}


async def live_summary(server: Any) -> dict[str, Any]:
    return summary(await server.list_tools())
