"""Read-only native domain check against one prepared lab.

This is the optional native stage of `tools/run_checks.ps1`. It starts the MCP
server (which owns the lab copy and launches VRoid Studio), then exercises one
read-only call per domain so a renamed or unregistered tool is caught before a
character session, and closes everything again.

    python tools/check_native_domains.py --lab <prepared lab> --json out.json

It never writes to the model, never saves, and refuses to start when the
`vroid.closet` crash key is present or another server owns the lab.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys
import time

PROJECT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / 'tools'))

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

from vroid_mcp import closet_guard, lab_lock  # noqa: E402
import vrm_inspect  # noqa: E402

ALL_DOMAINS = ['face-body', 'clothing-wear', 'texture-makeup', 'hair', 'vrm']


def _text(result) -> dict:
    if result.structuredContent:
        return result.structuredContent
    return json.loads(result.content[0].text)


async def _domain(call, name: str, model_token: str, lab: pathlib.Path) -> dict:
    started = time.monotonic()
    detail: dict = {}
    try:
        if name == 'face-body':
            face = _text(await call('list_face_params'))
            body = _text(await call('list_body_params'))
            height = _text(await call('get_height'))
            detail = {'face_parameters': len(face.get('parameters') or face.get('entries') or []),
                      'body_parameters': len(body.get('parameters') or body.get('entries') or []),
                      'height_cm': height.get('centimeters')}
            if not detail['body_parameters']:
                raise RuntimeError('no body parameters returned')
        elif name == 'clothing-wear':
            presets = _text(await call('list_clothing_presets', {'limit': 5}))
            templates = _text(await call('list_shoe_templates', {'expected_model': model_token}))
            wear = _text(await call('get_wear_status'))
            detail = {'clothing_presets': len(presets.get('presets') or []),
                      'shoe_templates': len(templates.get('templates') or []),
                      'dress_up_active': wear.get('active')}
            if not detail['shoe_templates']:
                raise RuntimeError('no native shoe templates returned')
        elif name == 'texture-makeup':
            renderers = _text(await call('inspect_texture_renderers', {'expected_model': model_token}))
            regions = _text(await call('list_texture_regions', {'expected_model': model_token}))
            detail = {'renderers': len(renderers.get('renderers') or []),
                      'regions': len(regions.get('regions') or [])}
            if not detail['regions']:
                raise RuntimeError('no texture regions returned')
        elif name == 'hair':
            materials = _text(await call('list_hair_materials',
                                         {'expected_model': model_token, 'category': 'HairFront'}))
            nodes = _text(await call('list_hair_nodes', {'category': 'HairFront'}))
            node_count = len(nodes.get('nodes') or [])
            detail = {'hair_materials': len(materials.get('materials') or []),
                      'hair_nodes': node_count,
                      'note': 'a fresh new model has no hair groups; nodes only appear after a preset or add_brush'}
            if not detail['hair_materials']:
                raise RuntimeError('no shared hair materials returned')
        elif name == 'vrm':
            candidates = sorted((p for p in lab.rglob('*.vrm') if p.is_file()),
                                key=lambda p: p.stat().st_mtime, reverse=True)
            if not candidates:
                return {'domain': name, 'status': 'skipped', 'reason': 'no .vrm in the lab yet',
                        'seconds': round(time.monotonic() - started, 2)}
            report = vrm_inspect.inspect(candidates[0])
            detail = {'path': report['path'], 'humanoid_bones': report['humanoid']['count'],
                      'expressions': len(report['expressions']['preset']),
                      'spring_chains': report['spring_bone']['chains'],
                      'findings': report['findings']}
            if not report['ok']:
                raise RuntimeError('VRM inspection failed: ' + '; '.join(report['findings']))
        else:
            raise RuntimeError('unknown domain')
    except Exception as error:  # a failed domain must not hide the others
        return {'domain': name, 'status': 'fail', 'error': str(error),
                'seconds': round(time.monotonic() - started, 2), 'detail': detail}
    return {'domain': name, 'status': 'pass', 'seconds': round(time.monotonic() - started, 2), 'detail': detail}


async def run(lab: pathlib.Path, domains: list[str], report_path: pathlib.Path | None) -> int:
    lab = lab.resolve()
    report: dict = {'schema': 'vroid-native-domains-v1', 'lab': str(lab), 'domains': domains,
                    'started': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'checks': []}
    exe = lab / 'app' / 'VRoidStudio.exe'
    if not exe.is_file():
        report.update(status='blocked', reason=f'no VRoid Studio copy at {exe}', checks=[])
        return _finish(report, report_path, 2)
    if closet_guard.present():
        report.update(status='blocked', reason='VROID_CLOSET_CRASH_KEY',
                      recovery='python -m vroid_mcp.closet_guard --clear --lab ' + str(lab))
        return _finish(report, report_path, 2)
    current = lab_lock.probe(lab)
    if current:
        report.update(status='blocked', reason=f'lab is owned by another MCP process (pid {current})')
        return _finish(report, report_path, 2)

    env = dict(os.environ)
    scratch = PROJECT.parent / 'work' / 'temp'
    scratch.mkdir(parents=True, exist_ok=True)
    env.update(TEMP=str(scratch), TMP=str(scratch))
    params = StdioServerParameters(command=sys.executable, args=['-m', 'vroid_mcp.server', '--lab', str(lab)],
                                   cwd=str(PROJECT), env=env)
    log_path = (report_path.parent if report_path else PROJECT.parent / 'work') / 'native-domains-server.log'
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open('w', encoding='utf-8') as log:
        async with stdio_client(params, errlog=log) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()

                async def call(name: str, args: dict | None = None):
                    result = await client.call_tool(name, args or {})
                    if result.isError:
                        raise RuntimeError(f'{name}: {result.content[0].text if result.content else "tool error"}')
                    return result

                status = _text(await call('get_status'))
                token = status.get('model_token') or ''
                report['tool_count'] = status.get('tool_count')
                report['toolset_hash'] = status.get('toolset_hash')
                report['model_token_present'] = bool(token)
                for domain in domains:
                    report['checks'].append(await _domain(call, domain, token, lab))

    failures = [c for c in report['checks'] if c['status'] == 'fail']
    report['status'] = 'fail' if failures else 'pass'
    return _finish(report, report_path, 1 if failures else 0)


def _finish(report: dict, report_path: pathlib.Path | None, code: int) -> int:
    report['finished'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({k: report.get(k) for k in ('status', 'reason', 'tool_count', 'toolset_hash')},
                     ensure_ascii=False))
    for check in report.get('checks', []):
        print(f"  {check['domain']:<15} {check['status']:<8} "
              f"{check.get('error') or check.get('reason') or json.dumps(check.get('detail'), ensure_ascii=False)}")
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description='Read-only native domain check')
    parser.add_argument('--lab', required=True, help='prepared lab directory that owns a VRoid Studio copy')
    parser.add_argument('--domains', default=','.join(ALL_DOMAINS),
                        help='comma separated subset of: ' + ', '.join(ALL_DOMAINS))
    parser.add_argument('--json', dest='json_out', default='', help='write the domain report here')
    args = parser.parse_args()
    domains = [d.strip() for d in args.domains.split(',') if d.strip()]
    unknown = [d for d in domains if d not in ALL_DOMAINS]
    if unknown:
        parser.error('unknown domains: ' + ', '.join(unknown))
    report_path = pathlib.Path(args.json_out) if args.json_out else None
    return asyncio.run(run(pathlib.Path(args.lab), domains, report_path))


if __name__ == '__main__':
    raise SystemExit(main())
