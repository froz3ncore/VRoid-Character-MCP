"""Read-only hair capability probe.

Enumerates the native hair parameter space of a real VRoid session (no writes,
no save) and records what the binary exposes through the current MCP surface.
Model file hash is checked before and after to prove the probe is read-only.
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
OUT = ROOT / 'projects' / 'whale-maid' / 'diagnostics' / 'hair-capability-probe-v01'
MODEL = LAB / 'saves' / 'whale_maid_03_test_base.vroid'
CATEGORIES = ['HairFront', 'HairBack', 'AllHair', 'HairTied', 'HairSideburns', 'HairAhoge', 'HairHanege']


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


async def paged(call, name, args, limit=500):
    out, offset = [], 0
    while True:
        result = await call(name, dict(args, offset=offset, limit=limit))
        out.extend(result.get('parameters', result.get('presets', [])))
        nxt = result.get('next_offset')
        if nxt is None:
            return out
        offset = nxt


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    before = hashlib.sha256(MODEL.read_bytes()).hexdigest()
    evidence = {
        'probe': 'hair-capability-probe-v01',
        'purpose': 'Read-only: distinguish VRoid product/API limits from MCP tool gaps for textured, layered hair.',
        'model': str(MODEL), 'model_sha256_before': before,
        'writes_attempted': False,
    }
    async with client_for(MODEL, 'hair-probe') as (_, call):
        token = (await call('list_face_params'))['model_token']
        evidence['model_token_issued'] = bool(token)

        # 1. Hair presets available natively.
        presets = await paged(call, 'list_hair_presets', {}, limit=200)
        evidence['hair_presets'] = {
            'count': len(presets),
            'categories': sorted({p.get('category') for p in presets if p.get('category')}),
            'sample': [p.get('id') for p in presets[:8]],
        }

        # 2. Hair structure per category (groups vs strands).
        nodes = {}
        for cat in CATEGORIES:
            try:
                result = await call('list_hair_nodes', {'category': cat})
                items = result['nodes']
                nodes[cat] = {
                    'total': len(items),
                    'groups': sum(1 for n in items if not n.get('parent')),
                    'kinds': sorted({n.get('kind') for n in items}),
                    'sample_ids': [n['id'] for n in items[:4]],
                }
            except Exception as exc:  # category may be empty on this model
                nodes[cat] = {'error': str(exc)[:200]}
        evidence['hair_nodes'] = nodes

        # 3. Full native parameter surface of one group and one strand.
        samples = {}
        for cat in CATEGORIES:
            entry = nodes.get(cat, {})
            for node_id in entry.get('sample_ids', [])[:2]:
                try:
                    params = await paged(call, 'list_parameters', {'domain': 'hair', 'category': cat, 'scope': node_id})
                    samples[f'{cat}:{node_id}'] = params
                except Exception as exc:
                    samples[f'{cat}:{node_id}'] = {'error': str(exc)[:200]}
        evidence['hair_parameter_samples'] = samples

        # 4. Colors, hair bones and general (shading/outline) surfaces.
        colors = await paged(call, 'list_parameters', {'domain': 'colors'})
        evidence['hair_color_params'] = [p['id'] for p in colors if 'hair' in p['id'].lower()]
        bones = {}
        for cat in ('HairFront', 'HairBack', 'AllHair'):
            try:
                groups = (await call('list_hair_bone_groups', {'category': cat}))['groups']
                params = await paged(call, 'list_parameters', {'domain': 'hair_bones', 'category': cat})
                bones[cat] = {'groups': len(groups), 'param_ids': [p['id'] for p in params][:20]}
            except Exception as exc:
                bones[cat] = {'error': str(exc)[:200]}
        evidence['hair_bones'] = bones
        general = await paged(call, 'list_parameters', {'domain': 'general'})
        evidence['hair_general_params'] = [p['id'] for p in general if 'hair' in p['id'].lower()]

    after = hashlib.sha256(MODEL.read_bytes()).hexdigest()
    evidence['model_sha256_after'] = after
    evidence['model_unchanged'] = before == after
    (OUT / 'hair-capability-evidence.json').write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({
        'model_unchanged': evidence['model_unchanged'],
        'hair_presets': evidence['hair_presets']['count'],
        'nodes': {k: v.get('total', v.get('error')) for k, v in evidence['hair_nodes'].items()},
        'sample_param_counts': {k: (len(v) if isinstance(v, list) else 'error')
                                for k, v in evidence['hair_parameter_samples'].items()},
        'out': str(OUT / 'hair-capability-evidence.json'),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
