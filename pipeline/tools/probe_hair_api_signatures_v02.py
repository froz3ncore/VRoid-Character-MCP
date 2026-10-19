"""Read-only round-3 discovery: value types behind hair curve/material APIs."""
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
OUT = ROOT / 'work' / 'hair-api-signatures-v02'
MODEL = LAB / 'saves' / 'whale_maid_03_test_base.vroid'

TARGETS = [
    ('VRoidCore', 'VRoidCore.Common.SpecificTypes.ControlPoint'),
    ('VRoidCore', 'VRoidCore.Common.Types.Curve'),
    ('VRoidCore', 'VRoidCore.Common.SpecificTypes.Guide'),
    ('VRoidCore', 'VRoidCore.Common.SpecificTypes.HairMaterialReference'),
    ('VRoidCore', 'VRoidCore.Common.SpecificTypes.SharedHairMaterialPath'),
    ('VRoidCore', 'VRoidCore.Common.SpecificTypes.BrushHairGroupletPath'),
    ('VRoidCore', 'VRoidCore.Common.SpecificTypes.HairMaterial'),
    ('VRoid.Studio', 'VRoid.Studio.HairEditor.DesignEditor.ActionHandler'),
    ('VRoid.Studio', 'VRoid.Studio.HairEditor.DesignEditor.Material.Model.MaterialThumbnail'),
]


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
    evidence = {'probe': 'hair-api-signatures-v02', 'model': str(MODEL),
                'model_sha256_before': before, 'writes_attempted': False}
    async with client_for(MODEL, 'hair-sigs2') as (_, call):
        evidence['model_token_issued'] = bool((await call('list_face_params'))['model_token'])
        inspected = {}
        for assembly, name in TARGETS:
            try:
                inspected[f'{assembly}:{name}'] = await call('inspect_native_api',
                    {'class_name': name, 'assembly': assembly})
            except Exception as exc:
                inspected[f'{assembly}:{name}'] = {'error': str(exc)[:200]}
        evidence['inspected'] = inspected
    after = hashlib.sha256(MODEL.read_bytes()).hexdigest()
    evidence['model_sha256_after'] = after
    evidence['model_unchanged'] = before == after
    (OUT / 'hair-api-signatures.json').write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf8')
    ok = [k for k, v in inspected.items() if isinstance(v, dict) and 'error' not in v]
    print(json.dumps({'model_unchanged': evidence['model_unchanged'],
                      'inspected_ok': len(ok), 'failed': [k for k in inspected if k not in ok],
                      'out': str(OUT / 'hair-api-signatures.json')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
