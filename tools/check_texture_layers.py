"""Native raster-layer acceptance via real MCP stdio on an exclusive prepared lab.

Writes test-only layers/files to that lab, then cold-reopens the saved character.
No existing user window is selected. --out must be a new evidence directory.
The reusable exercise() also runs inside the isolated attached-session fixture.
"""
import argparse
import asyncio
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from vroid_mcp.bounded_paint import decode_rgba_png
from vroid_mcp.texture_mapping import png_rgba


async def exercise(call, lab, token, region_id, prefix, render=True):
    (lab/'saves').mkdir(exist_ok=True)
    args = {'expected_model': token, 'region_id': region_id}
    checks = {}
    async def listing():
        return await call('list_texture_layers', args)
    async def pixels(row):
        result = await call('export_texture_layer', {**args, 'layer_id': row['layer_id']})
        w, h, data = decode_rgba_png(Path(result['path']).read_bytes())
        return {'width': w, 'height': h, 'rgba_sha256': hashlib.sha256(data).hexdigest()}
    async def histories():
        for op in ('undo', 'redo'):
            await call(op, {'expected_model': token})
    initial = await listing()
    original = {row['layer_id']: await pixels(row) for row in initial['layers']}
    # One image per fixture. The tools independently reject cross-image stacks.
    source = initial['layers'][0]
    sample = original[source['layer_id']]
    image_id = initial['images'][0]['image_id']
    for name, color in [('A', [180,80,40,180]), ('B', [40,120,200,180])]:
        rgba = bytes(color)*(sample['width']*sample['height'])
        png = png_rgba(sample['width'], sample['height'], rgba)
        filename = prefix+'-'+name+'.png'
        (lab/'saves'/filename).write_bytes(png)
        imported = await call('import_texture_layer', {**args, 'image_id': image_id,
            'filename': filename, 'layer_name': prefix+'-'+name,
            'expected_png_sha256': hashlib.sha256(png).hexdigest()})
        original[imported['layer']['layer_id']] = {'width': sample['width'], 'height': sample['height'],
                                                  'rgba_sha256': hashlib.sha256(rgba).hexdigest()}
    state = await listing()
    a = next(row for row in state['layers'] if row['Name'] == prefix+'-A')
    b = next(row for row in state['layers'] if row['Name'] == prefix+'-B')
    assert state['images'][0]['layer_ids'][-2:] == [a['layer_id'], b['layer_id']]
    checks['enumeration_is_bottom_to_top'] = True
    rename_args = {**args, 'layer_id': a['layer_id'], 'expected_state_sha256': a['state_sha256'], 'name': prefix+'-Renamed'}
    renamed = await call('rename_texture_layer', rename_args)
    assert renamed['history_command_count'] == 1
    await call('undo', {'expected_model': token})
    assert next(row for row in (await listing())['layers'] if row['layer_id']==a['layer_id'])['Name']==prefix+'-A'
    await call('redo', {'expected_model': token})
    checks['rename_native_undo_redo'] = True
    fresh = next(row for row in (await listing())['layers'] if row['layer_id']==a['layer_id'])
    no_op = await call('rename_texture_layer', {**rename_args, 'expected_state_sha256': fresh['state_sha256']})
    assert no_op['history_command_count'] == 0
    checks['same_name_no_history_command'] = True

    renderer = None
    if render:
        face = next(row for row in (await call('inspect_texture_renderers', {'expected_model': token}))['renderers'] if row['name']=='Face')
        skin = [m for m in face['materials'] if 'skin' in m.get('name','').lower()]
        assert len(skin) == 1
        renderer = {'expected_model': token, 'mesh_name': 'Face', 'material_slot': skin[0]['slot']}
    async def composite():
        if not renderer: return None
        result = await call('export_renderer_texture', renderer)
        return hashlib.sha256(decode_rgba_png(Path(result['path']).read_bytes())[2]).hexdigest()
    before_order = await composite()
    image = (await listing())['images'][0]
    order = image['layer_ids'][:-2] + list(reversed(image['layer_ids'][-2:]))
    reordered = await call('reorder_texture_layers', {**args, 'image_id': image_id,
        'expected_stack_sha256': image['stack_sha256'], 'layer_ids': order})
    assert reordered['history_command_count']==1 and reordered['images'][0]['layer_ids']==order
    after_order = await composite()
    await call('undo', {'expected_model': token})
    assert (await listing())['images'][0]['layer_ids']==image['layer_ids']
    await call('redo', {'expected_model': token})
    assert (await listing())['images'][0]['layer_ids']==order
    checks['reorder_single_command_and_undo_redo'] = True
    if render:
        assert before_order != after_order, 'Layer order read back but actual composition did not change'
        checks['reorder_changes_actual_renderer_texture'] = {'before': before_order, 'after': after_order}

    before_blend = await composite()
    modes = (await listing())['composition_modes']
    for mode in modes:
        fresh = next(row for row in (await listing())['layers'] if row['layer_id']==a['layer_id'])
        result = await call('set_texture_layer_blend', {**args, 'layer_id': a['layer_id'],
            'expected_state_sha256': fresh['state_sha256'], 'composition_mode': mode['id']})
        assert result['layer']['CompositionMode']==mode['id']
    checks['all_native_blend_modes_readback'] = len(modes)
    fresh = next(row for row in (await listing())['layers'] if row['layer_id']==a['layer_id'])
    await call('set_texture_layer_blend', {**args, 'layer_id': a['layer_id'],
        'expected_state_sha256': fresh['state_sha256'], 'composition_mode': 'CompositionMultiply'})
    after_blend = await composite()
    await call('undo', {'expected_model': token})
    assert next(row for row in (await listing())['layers'] if row['layer_id']==a['layer_id'])['CompositionMode']!='CompositionMultiply'
    await call('redo', {'expected_model': token})
    assert next(row for row in (await listing())['layers'] if row['layer_id']==a['layer_id'])['CompositionMode']=='CompositionMultiply'
    checks['blend_native_undo_redo'] = True
    if render:
        assert before_blend != after_blend, 'Blend mode read back but actual composition did not change'
        checks['blend_changes_actual_renderer_texture'] = {'before': before_blend, 'after': after_blend}
    state = await listing()
    fresh_b = next(row for row in state['layers'] if row['layer_id']==b['layer_id'])
    deleted = await call('delete_texture_layer', {**args, 'layer_id': b['layer_id'],
        'expected_state_sha256': fresh_b['state_sha256'], 'expected_stack_sha256': state['images'][0]['stack_sha256']})
    assert b['layer_id'] not in [row['layer_id'] for row in deleted['layers']]
    await call('undo', {'expected_model': token})
    restored = next(row for row in (await listing())['layers'] if row['layer_id']==b['layer_id'])
    assert await pixels(restored) == original[b['layer_id']]
    await call('redo', {'expected_model': token})
    assert b['layer_id'] not in [row['layer_id'] for row in (await listing())['layers']]
    checks['delete_undo_restores_exact_pixels_and_redo_removes'] = True
    final = await listing()
    snapshot = []
    for row in final['layers']:
        px = await pixels(row)
        assert px == original[row['layer_id']]
        snapshot.append({key: row[key] for key in ('Name','Opacity','Visibility','CompositionMode')} | px)
    checks['all_surviving_source_pixels_preserved'] = len(snapshot)
    return {'checks': checks, 'snapshot': snapshot, 'region_id': region_id}


async def run(lab, out, variant):
    out.mkdir(parents=True, exist_ok=False)
    report = {'variant': variant, 'checks': {}}
    prefix = 'layer-check-'+uuid.uuid4().hex[:8]
    async def session(body, model=None):
        args = ['-m','vroid_mcp.server','--lab',str(lab),'--variant',variant]
        if model: args += ['--model', str(model)]
        params = StdioServerParameters(command=sys.executable, args=args, cwd=str(ROOT), env=dict(os.environ))
        with (out/('cold-server.log' if model else 'server.log')).open('w',encoding='utf8') as log:
            async with stdio_client(params, errlog=log) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=180)) as client:
                    await client.initialize()
                    async def call(name, arguments=None):
                        result = await client.call_tool(name, arguments or {}, read_timeout_seconds=timedelta(seconds=180))
                        if result.isError: raise RuntimeError(name+': '+str(result.content))
                        return result.structuredContent or json.loads(result.content[0].text)
                    await body(call)
    async def author(call):
        token = (await call('list_face_params'))['model_token']
        report['native_image_api'] = await call('inspect_native_api', {
            'assembly':'VRoidCore','class_name':'VRoidCore.Common.SpecificTypes.Model','filter':'EditableImage'})
        regions = (await call('list_texture_regions', {'expected_model':token}))['regions']
        region = next(r for r in regions if r['part']==('Cheek' if any(x['part']=='Cheek' for x in regions) else 'FaceSkin'))
        report['part'] = region['part']
        await call('open_texture_editor', {'expected_model':token,'region_id':region['region_id'],'bake_colors':True})
        result = await exercise(call, lab, token, region['region_id'], prefix)
        report.update(snapshot=result['snapshot']); report['checks'].update(result['checks'])
        await call('close_texture_editor', {'expected_model':token})
        report['saved'] = await call('save_as', {'expected_model':token,'filename':prefix+'.vroid'})
    async def cold(call):
        token = (await call('list_face_params'))['model_token']
        region = next(r for r in (await call('list_texture_regions', {'expected_model':token}))['regions'] if r['part']==report['part'])
        layers = (await call('list_texture_layers', {'expected_model':token,'region_id':region['region_id']}))['layers']
        snapshot = []
        for row in layers:
            result = await call('export_texture_layer', {'expected_model':token,'region_id':region['region_id'],'layer_id':row['layer_id']})
            w,h,rgba = decode_rgba_png(Path(result['path']).read_bytes())
            snapshot.append({key:row[key] for key in ('Name','Opacity','Visibility','CompositionMode')} |
                {'width':w,'height':h,'rgba_sha256':hashlib.sha256(rgba).hexdigest()})
        assert snapshot == report['snapshot']
        report['checks']['cold_reopen_preserves_order_names_blend_and_pixels'] = True
    try:
        await session(author)
        await session(cold, Path(report['saved']['path']))
        report['passed'] = True
    except BaseException as error:
        report.update(passed=False,error=repr(error));raise
    finally:
        (out/'checks.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({'passed':True,'variant':variant,'checks':len(report['checks'])}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lab',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--variant',choices=['F00','M00'],default='F00')
    args=parser.parse_args()
    asyncio.run(run(args.lab,args.out,args.variant))
