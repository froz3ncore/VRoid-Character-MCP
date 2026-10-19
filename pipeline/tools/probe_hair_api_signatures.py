"""Read-only round-2 discovery: signatures of hair authoring API classes.

Targets the exact classes found by probe_hair_api_surface.py and records their
declared constructors, methods and fields so new MCP tools can call them with
correct arguments. No writes.
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
OUT = ROOT / 'work' / 'hair-api-signatures-v01'
MODEL = LAB / 'saves' / 'whale_maid_03_test_base.vroid'

TARGETS = [
    ('VRoidCore', 'VRoidCore.Editing.History.Command.AddBrushHairGroupCommand'),
    ('VRoidCore', 'VRoidCore.Editing.History.Command.CloneBrushHairStrandCommand'),
    ('VRoidCore', 'VRoidCore.Editing.History.Command.DeleteBrushHairStrandCommand'),
    ('VRoidCore', 'VRoidCore.Editing.History.Command.SetHairStrandCurveCommand'),
    ('VRoidCore', 'VRoidCore.Editing.History.Command.MoveBrushHairStrandControlPointCommand'),
    ('VRoidCore', 'VRoidCore.Editing.History.Command.MoveBrushHairStrandControlPointContinueCommand'),
    ('VRoidCore', 'VRoidCore.Editing.History.Command.SetHairStrandNameCommand'),
    ('VRoidCore', 'VRoidCore.Editing.History.Command.SetHairStrandIsVisibleCommand'),
    ('VRoidCore', 'VRoidCore.Editing.History.Command.SmoothBrushHairStrandsCommand'),
    ('VRoidCore', 'VRoidCore.Editing.History.Command.ModifyBrushHairStrandParameterSetCommand'),
    ('VRoidCore', 'VRoidCore.Editing.History.Command.ModifyBrushHairGroupParameterSetCommand'),
    ('VRoidCore', 'VRoidCore.Editing.History.Command.ConvertProceduralHairGroupToBrushHairGroupCommand'),
    ('VRoidCore', 'VRoidCore.Editing.Query.GetHairStrandCurveQuery'),
    ('VRoidCore', 'VRoidCore.Editing.Query.GetHairStrandControlPointQuery'),
    ('VRoidCore', 'VRoidCore.Editing.Query.GetHairStrandControlPointCountQuery'),
    ('VRoidCore', 'VRoidCore.Editing.Query.GetHairStrandMeshQuery'),
    ('VRoidCore', 'VRoidCore.Editing.Query.GetBrushHairStrandParameterSetQuery'),
    ('VRoidCore', 'VRoidCore.Editing.Query.GetBrushHairGroupParameterSetQuery'),
    ('VRoidCore', 'VRoidCore.Editing.Query.GetHairStrandNameQuery'),
    ('VRoidCore', 'VRoidCore.Common.SpecificTypes.HairTextureParameterSet'),
    ('VRoidCore', 'VRoidCore.Common.SpecificTypes.BrushHairStrandPath'),
    ('VRoidCore', 'VRoidCore.Common.SpecificTypes.BrushHairGroupPath'),
    ('VRoidCore', 'VRoidCore.Common.SpecificTypes.BrushHairParameterSet'),
    ('VRoidCore', 'VRoidCore.Common.SpecificTypes.BrushHairHairParameterSet'),
    ('VRoidCore', 'VRoidCore.Common.SpecificTypes.BrushHairGroupParameterSet'),
    ('VRoidCore', 'VRoidCore.Common.SpecificTypes.BrushHairGroupHairParameterSet'),
    ('VRoid.Studio', 'VRoid.Studio.HairEditor.DesignEditor.Material.Model.MaterialThumbnailCollectionModel'),
    ('VRoid.Studio', 'VRoid.Studio.HairEditor.DesignEditor.HairStrand.ViewModel.BrushHairStrandPropertyViewModel'),
    ('VRoid.Studio', 'VRoid.Studio.HairEditor.DesignEditor.HairGroup.ViewModel.BrushHairGroupPropertyViewModel'),
    ('VRoid.Studio', 'VRoid.Studio.HairEditor.DesignEditor.Mode.ViewModel.ModeViewModelBase'),
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
    evidence = {'probe': 'hair-api-signatures-v01', 'model': str(MODEL),
                'model_sha256_before': before, 'writes_attempted': False}
    async with client_for(MODEL, 'hair-sigs') as (_, call):
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
