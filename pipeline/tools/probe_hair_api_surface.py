"""Read-only native API surface discovery for hair authoring tools.

Uses the MCP introspection tools (search_native_classes / inspect_native_api)
to map the managed API behind hand-drawn hair strands, strand curves, hair
textures and per-strand color before implementing new tools. No writes.
"""
import asyncio
import hashlib
import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / 'VRoid-MCP'
LAB = ROOT / 'lab-test'
OUT = ROOT / 'work' / 'hair-api-discovery-v01'
MODEL = LAB / 'saves' / 'whale_maid_03_test_base.vroid'

SEARCHES = [
    ('VRoid.Studio', 'brushhair'),
    ('VRoid.Studio', 'hairstrand'),
    ('VRoid.Studio', 'hairtexture'),
    ('VRoid.Studio', 'hairdesign'),
    ('VRoidCore', 'brushhair'),
    ('VRoidCore', 'hairstrand'),
    ('VRoidCore', 'hair'),
    ('VRoidCore', 'hairtexture'),
]

# Full class names known from existing code, always inspected.
KNOWN = [
    ('VRoid.Studio', 'VRoid.Studio.HairEditor.DesignEditor.ViewModel'),
]

# Substrings that select interesting search hits for signature inspection.
INSPECT_MATCH = ('command', 'hairtexture', 'brushhairstrand', 'brushhairgroup', 'hairstrandmodel')


@asynccontextmanager
async def client_for(model, label):
    params = StdioServerParameters(
        command=sys.executable,
        args=['-m', 'vroid_mcp.server', '--lab', str(LAB), '--model', str(model)],
        cwd=str(PROJECT),
        env=dict(os.environ, TEMP=str(ROOT / 'work' / 'temp'), TMP=str(ROOT / 'work' / 'temp')))
    with (OUT / (label + '.log')).open('w', encoding='utf8') as log:
        async with stdio_client(params, errlog=log) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=240)) as client:
                await client.initialize()

                async def call(name, args=None):
                    result = await client.call_tool(name, args or {})
                    assert not result.isError, (name, result)
                    return result.structuredContent or json.loads(result.content[0].text)

                yield client, call


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    before = hashlib.sha256(MODEL.read_bytes()).hexdigest()
    evidence = {'probe': 'hair-api-discovery-v01', 'model': str(MODEL),
                'model_sha256_before': before, 'writes_attempted': False}
    async with client_for(MODEL, 'hair-api') as (_, call):
        evidence['model_token_issued'] = bool((await call('list_face_params'))['model_token'])

        searches = {}
        for assembly, substring in SEARCHES:
            try:
                searches[f'{assembly}:{substring}'] = (await call('search_native_classes',
                    {'assembly': assembly, 'substring': substring}))['matches']
            except Exception as exc:
                searches[f'{assembly}:{substring}'] = {'error': str(exc)[:200]}
        evidence['class_searches'] = searches

        targets = list(KNOWN)
        for key, matches in searches.items():
            if isinstance(matches, list):
                assembly = key.split(':', 1)[0]
                for name in matches:
                    low = name.lower()
                    if any(pat in low for pat in INSPECT_MATCH) and (assembly, name) not in targets:
                        targets.append((assembly, name))
        evidence['inspect_targets'] = [f'{a}:{n}' for a, n in targets]

        inspected = {}
        for assembly, name in targets[:30]:
            try:
                inspected[f'{assembly}:{name}'] = await call('inspect_native_api',
                    {'class_name': name, 'assembly': assembly})
            except Exception as exc:
                inspected[f'{assembly}:{name}'] = {'error': str(exc)[:200]}
        evidence['inspected'] = inspected

    after = hashlib.sha256(MODEL.read_bytes()).hexdigest()
    evidence['model_sha256_after'] = after
    evidence['model_unchanged'] = before == after
    (OUT / 'hair-api-surface.json').write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({
        'model_unchanged': evidence['model_unchanged'],
        'search_hits': {k: (len(v) if isinstance(v, list) else 'error') for k, v in searches.items()},
        'inspected': list(inspected),
        'out': str(OUT / 'hair-api-surface.json'),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
