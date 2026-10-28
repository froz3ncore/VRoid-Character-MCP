"""Same-process body -> texture -> Dress-up -> VRM acceptance on an exclusive lab.

Use an exclusive prepared lab; all models and diagnostic texture layers are generated
in that lab. No private outfit or user model is required. A second process only
verifies persistence AFTER the continuous-editing sequence has completed.
"""
from __future__ import annotations
import argparse
import asyncio
from datetime import timedelta
import hashlib
import json
import os
import struct
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from vroid_mcp.bounded_paint import decode_rgba_png
from vroid_mcp.texture_mapping import png_rgba
import vrm_inspect


async def run(lab, out, variant, cycles):
    lab, out = lab.resolve(), out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    scratch = out / 'temp'; scratch.mkdir()
    os.environ['TEMP'] = os.environ['TMP'] = str(scratch)
    report = {'variant': variant, 'cycles': cycles, 'checks': {}}
    prefix = 'continuous-' + uuid.uuid4().hex[:12]
    def passed(name, value=True):
        report['checks'][name] = value
        print('PASS ' + name, flush=True)

    async def session(body, model=None):
        args = ['-m', 'vroid_mcp.server', '--lab', str(lab), '--variant', variant]
        if model: args += ['--model', str(model)]
        params = StdioServerParameters(command=sys.executable, args=args, cwd=str(ROOT), env=dict(os.environ))
        log_name = 'cold-server.log' if model else 'continuous-server.log'
        with (out / log_name).open('w', encoding='utf8') as log:
            async with stdio_client(params, errlog=log) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=180)) as client:
                    await client.initialize()
                    async def call(name, args=None):
                        result = await client.call_tool(name, args or {}, read_timeout_seconds=timedelta(seconds=180))
                        if result.isError: raise RuntimeError(name + ': ' + str(result.content))
                        return result.structuredContent or json.loads(result.content[0].text)
                    await body(call)

    async def layer_pixels(call, token, region_id, layer_id):
        exported = await call('export_texture_layer', {'expected_model': token,
            'region_id': region_id, 'layer_id': layer_id})
        width, height, rgba = decode_rgba_png(Path(exported['path']).read_bytes())
        return {'width': width, 'height': height, 'rgba_sha256': hashlib.sha256(rgba).hexdigest()}

    async def continuous(call):
        status = await call('get_status')
        assert status['png_decoder']['installed'] and status['png_decoder']['fatal'] is None
        token, pid = status['model_token'], status['pid']
        report['continuous_pid'] = pid
        presets = await call('list_hair_presets')
        hair = next(p for p in presets['presets'] if p['category'] == 'HairSet' and p['owned'])
        await call('apply_hair_preset', {'expected_model': token, 'preset_id': hair['id']})
        for cycle in range(cycles):
            value = .15 + .1 * cycle
            await call('set_body_params', {'expected_model': token,
                'changes': [{'id': 'body/WholeBody/002', 'value': value}]})
            regions = (await call('list_texture_regions', {'expected_model': token}))['regions']
            report['available_regions'] = [r['part'] for r in regions]
            parts = [p for p in ['Cheek', 'BodySkin', 'Iris', 'Eyelid', 'FaceSkin', 'Eyebrow', 'EyeWhite']
                     if p in report['available_regions']][:4]
            assert len(parts) >= 2, report['available_regions']
            report['cycled_regions'] = parts
            for part in parts:
                region = next(r for r in regions if r['part'] == part)
                await call('open_texture_editor', {'expected_model': token, 'region_id': region['region_id']})
                await call('close_texture_editor', {'expected_model': token})
        passed('body_to_texture_without_restart', cycles * len(parts))
        report['body_value'] = value
        regions = (await call('list_texture_regions', {'expected_model': token}))['regions']
        paint_part = 'Cheek' if any(r['part'] == 'Cheek' for r in regions) else 'FaceSkin'
        report['paint_part'] = paint_part
        cheek = next(r for r in regions if r['part'] == paint_part)
        await call('open_texture_editor', {'expected_model': token, 'region_id': cheek['region_id'], 'bake_colors': True})
        layers = (await call('list_texture_layers', {'expected_model': token, 'region_id': cheek['region_id']}))['layers']
        sample = await call('export_texture_layer', {'expected_model': token,
            'region_id': cheek['region_id'], 'layer_id': layers[0]['layer_id']})
        width, height, _ = decode_rgba_png(Path(sample['path']).read_bytes())
        rgba = bytearray(width * height * 4)
        for y in range(height // 3, height // 3 + 16):
            for x in range(width // 3, width // 3 + 16):
                rgba[4*(y*width+x):4*(y*width+x)+4] = bytes([170, 40, 110, 160])
        png = png_rgba(width, height, rgba)
        (lab / 'saves' / (prefix + '-marker.png')).write_bytes(png)
        name = 'Continuous editing diagnostic'
        await call('import_texture_layer', {'expected_model': token, 'region_id': cheek['region_id'],
            'image_id': json.dumps(layers[0]['image'], separators=(',', ':')), 'filename': prefix + '-marker.png',
            'layer_name': name, 'expected_png_sha256': hashlib.sha256(png).hexdigest()})
        layers = (await call('list_texture_layers', {'expected_model': token, 'region_id': cheek['region_id']}))['layers']
        marker = next(l for l in layers if l.get('Name', l.get('name')) == name)
        pixels = await layer_pixels(call, token, cheek['region_id'], marker['layer_id'])
        assert pixels['rgba_sha256'] == hashlib.sha256(rgba).hexdigest()
        report['pixels'] = pixels
        passed('native_import_exact_rgba', pixels)
        await call('close_texture_editor', {'expected_model': token})
        renderers = await call('inspect_texture_renderers', {'expected_model': token})
        face = next(r for r in renderers['renderers'] if r['name'] == 'Face')
        skin = [m for m in face['materials'] if 'skin' in m.get('name', '').lower()]
        assert len(skin) == 1
        renderer_texture = await call('export_renderer_texture', {'expected_model': token,
            'mesh_name': 'Face', 'material_slot': skin[0]['slot']})
        rw, rh, rp = decode_rgba_png(Path(renderer_texture['path']).read_bytes())
        report['face_texture'] = {'width': rw, 'height': rh, 'rgba_sha256': hashlib.sha256(rp).hexdigest()}
        saved = await call('save_as', {'filename': prefix + '.vroid', 'expected_model': token})
        report['model'] = saved
        wear = await call('get_wear_status')
        wear = await call('open_wear_project', {'filename': prefix + '.vroid',
            'expected_wear': wear['wear_token'], 'discard_unsaved': True})
        assert wear['active'] and (await call('get_status'))['pid'] == pid
        passed('texture_to_wear_same_pid', pid)
        report['xroid'] = await call('save_wear_project', {'filename': prefix + '.xroid',
            'expected_wear': wear['wear_token']})
        exported = await call('export_wear_vrm', {'filename': prefix + '.vrm',
            'expected_wear': wear['wear_token'], 'title': 'Continuous editing ' + variant,
            'author': 'VRoid Character MCP acceptance'})
        report['vrm'] = exported
        inspected = vrm_inspect.inspect(lab / 'saves' / (prefix + '.vrm'))
        assert inspected['ok'], inspected['findings']
        # Verify the renderer texture actually survives the PNG-loading path
        # into the exported VRM, independently of the editable-layer round trip.
        vrm_path = lab / 'saves' / (prefix + '.vrm')
        doc = vrm_inspect.read_glb(vrm_path)
        materials = [m for m in doc['materials'] if 'face' in m.get('name', '').lower()
                     and 'skin' in m.get('name', '').lower()]
        assert len(materials) == 1
        tex = materials[0]['pbrMetallicRoughness']['baseColorTexture']['index']
        image = doc['images'][doc['textures'][tex]['source']]
        view = doc['bufferViews'][image['bufferView']]
        raw = vrm_path.read_bytes(); offset = 12
        while offset < len(raw):
            length, kind = struct.unpack_from('<II', raw, offset)
            if kind == 0x004E4942: break
            offset += 8 + length
        start = offset + 8 + view.get('byteOffset', 0)
        ew, eh, ep = decode_rgba_png(raw[start:start + view['byteLength']])
        vrm_pixels = {'width': ew, 'height': eh, 'rgba_sha256': hashlib.sha256(ep).hexdigest()}
        assert vrm_pixels == report['face_texture'], (vrm_pixels, report['face_texture'])
        passed('vrm_face_texture_exact_rgba', vrm_pixels)
        (out / 'vrm-inspection.json').write_text(json.dumps(inspected, indent=2), encoding='utf8')
        status = await call('get_status')
        assert status['pid'] == pid and not status['png_decoder']['pending'] and not status['png_decoder']['fatal']
        passed('same_process_xroid_and_vrm_export', status['png_decoder'])

    async def cold(call):
        status = await call('get_status')
        assert status['pid'] != report['continuous_pid']
        token = status['model_token']
        body = await call('list_body_params')
        assert abs(next(p['value'] for p in body['parameters'] if p['id'] == 'body/WholeBody/002') - report['body_value']) < 1e-6
        region = next(r for r in (await call('list_texture_regions', {'expected_model': token}))['regions'] if r['part'] == report['paint_part'])
        layers = (await call('list_texture_layers', {'expected_model': token, 'region_id': region['region_id']}))['layers']
        marker = next(l for l in layers if l.get('Name', l.get('name')) == 'Continuous editing diagnostic')
        pixels = await layer_pixels(call, token, region['region_id'], marker['layer_id'])
        assert pixels == report['pixels']
        passed('cold_persistence_body_and_pixels', pixels)
    try:
        await session(continuous)
        await session(cold, Path(report['model']['path']))
        report['passed'] = True
    except BaseException as error:
        report.update(passed=False, error=repr(error))
        raise
    finally:
        (out / 'checks.json').write_text(json.dumps(report, indent=2), encoding='utf8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lab', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--variant', choices=['F00', 'M00'], default='F00')
    parser.add_argument('--cycles', type=int, choices=range(1, 6), default=3)
    args = parser.parse_args()
    asyncio.run(run(args.lab, args.out, args.variant, args.cycles))


if __name__ == '__main__': main()
