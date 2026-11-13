"""Local JSON-line or batch client. Keep image bytes out of the terminal and JSON.

Adapted from shamsievartyom/VRoid-Character-MCP (cb71a749). Copy mode already
isolates protocol registry lookups, so this client does not clear or restore
the installed vroid.closet association.
"""

import argparse
import asyncio
import base64
import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from tempfile import mkdtemp
from uuid import uuid4

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import ImageContent, TextContent

from vroid_mcp.local_comparison import Comparison, compare_presets
from vroid_mcp.workflow import REFERENCE_GUIDANCE

ROOT = Path(__file__).resolve().parent
WORK = ROOT / 'work'
MAX_INLINE_CHARS = 8000


def preset_preview_files(blocks):
    # preview_presets sends a manifest followed by caption/image pairs.
    return [
        {**json.loads(caption['text']), 'path': image['path']}
        for caption, image in zip(blocks[1::2], blocks[2::2])
        if caption['type'] == 'text' and image['type'] == 'image_file'
    ]


async def run_request(client, request, variables):
    name = request['name']
    output = None
    if request.get('output'):
        output = (ROOT / request['output']).resolve()
        if not output.is_relative_to(WORK) or output.suffix.lower() != '.json':
            raise ValueError('output must name a JSON file under work/')

    arguments = dict(request.get('arguments', {}))
    if arguments.get('expected_model') == '$model':
        if '$model' not in variables:
            status = await client.call_tool('get_status')
            if status.isError or not status.content or not isinstance(status.content[0], TextContent):
                raise RuntimeError('Could not read the active model token')
            variables['$model'] = json.loads(status.content[0].text)['model_token']
        arguments['expected_model'] = variables['$model']
    if name == 'capture_review':
        arguments.setdefault('include_images', False)

    if name == '_schemas':
        result = (await client.list_tools()).model_dump(mode='json')
        success = True
    else:
        response = await client.call_tool(name, arguments)
        blocks = []
        image_dir = None
        for block in response.content:
            if isinstance(block, ImageContent):
                if image_dir is None:
                    image_dir = Path(mkdtemp(prefix='vroid-preview-', dir=WORK))
                extension = {'image/png': 'png', 'image/jpeg': 'jpg'}.get(block.mimeType, 'bin')
                path = image_dir / f'{len(blocks):02d}.{extension}'
                path.write_bytes(base64.b64decode(block.data, validate=True))
                blocks.append({'type': 'image_file', 'path': str(path), 'mimeType': block.mimeType})
            else:
                blocks.append(block.model_dump(mode='json'))
        result = {'content': blocks, 'isError': response.isError}
        if blocks and blocks[0]['type'] == 'text':
            try:
                data = json.loads(blocks[0]['text'])
            except (ValueError, TypeError):
                data = None
            if isinstance(data, dict) and data.get('ok') is False:
                result['isError'] = True
        success = not result['isError']
        if name == 'preview_presets' and success:
            result['previews'] = preset_preview_files(blocks)

    serialized = json.dumps(result, ensure_ascii=True)
    if output is None and len(serialized) > MAX_INLINE_CHARS:
        output = Path(mkdtemp(prefix='vroid-response-', dir=WORK)) / 'response.json'
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        summary = {'ok': success, 'tool': name, 'output': str(output)}
        if 'previews' in result:
            summary['previews'] = result['previews']
        if not success:
            summary['error'] = result['content'][0].get('text', '')[:500]
        print(json.dumps(summary, ensure_ascii=True), flush=True)
    else:
        print(serialized, flush=True)
    return success


async def check_save(client, lab):
    status = await client.call_tool('get_status')
    if status.isError:
        print(f'Save preflight could not read the model: {status.content[0].text[:500]}', file=sys.stderr)
        return False
    model_token = json.loads(status.content[0].text)['model_token']
    filename = f'save-check-{uuid4().hex}.vroid'
    result = await client.call_tool('save_as', {'expected_model': model_token, 'filename': filename})
    if result.isError:
        print('Save preflight failed before any edits. Check the VRoid process permissions and '
              f'temporary directory in the latest {lab / "runs"} Player.log.\n{result.content[0].text[:500]}',
              file=sys.stderr)
        return False
    (lab / 'saves' / filename).unlink()
    print('Save preflight passed.', file=sys.stderr)
    return True


async def main(args, batch, comparison):
    lab = args.lab.resolve()
    if not (lab / 'app' / 'VRoidStudio.exe').is_file():
        raise ValueError('--lab must contain app/VRoidStudio.exe')
    WORK.mkdir(exist_ok=True)
    temp = WORK / 'temp'
    temp.mkdir(exist_ok=True)
    launch = [str(ROOT / 'launch.py'), '--lab', str(lab)]
    model = None
    if args.model:
        model = (lab / 'saves' / args.model).resolve()
        if not model.is_relative_to(lab / 'saves') or not model.is_file() or model.suffix.lower() != '.vroid':
            raise ValueError('--model must name an existing .vroid file under the lab saves/')
        launch += ['--model', str(model)]
    parameters = StdioServerParameters(command=sys.executable, args=launch, cwd=str(ROOT),
                                       env={**os.environ, 'TEMP': str(temp), 'TMP': str(temp)})
    with (lab / 'client-server.log').open('a', encoding='utf-8') as log:
        async with stdio_client(parameters, errlog=log) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=180)) as client:
                await client.initialize()
                if args.check_save and not await check_save(client, lab):
                    return 1
                if comparison is not None:
                    result = await compare_presets(client, comparison, model, lab)
                    print(json.dumps(result, ensure_ascii=True), flush=True)
                    return 0
                variables = {}
                if batch is not None:
                    for request in batch:
                        if not await run_request(client, request, variables):
                            return 1
                    return 0

                print('READY', flush=True)
                while line := await asyncio.to_thread(sys.stdin.readline):
                    if line.strip() == 'EXIT':
                        break
                    try:
                        await run_request(client, json.loads(line), variables)
                    except Exception as error:
                        print(json.dumps({'ok': False, 'error': str(error)}), flush=True)
                return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lab', type=Path, default=WORK / 'vroid-lab')
    parser.add_argument('--model', help='Filename relative to the lab saves/ directory')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--batch', type=Path, help='JSON array of requests, run in order, stopping on error')
    mode.add_argument('--compare', type=Path, help='JSON preset comparison on the saved --model')
    mode.add_argument('--instructions', action='store_true', help='Print the reference workflow without starting VRoid')
    parser.add_argument('--check-save', action='store_true',
                        help='Verify native saving with a temporary copy before running requests')
    args = parser.parse_args()
    if args.instructions:
        print(REFERENCE_GUIDANCE, end='')
        raise SystemExit(0)
    batch = json.loads(args.batch.read_text(encoding='utf-8-sig')) if args.batch else None
    if args.batch and (not isinstance(batch, list) or not all(isinstance(item, dict) for item in batch)):
        parser.error('--batch expects an array of request objects')
    if args.compare and not args.model:
        parser.error('--compare requires --model')
    comparison = Comparison.model_validate_json(args.compare.read_text(encoding='utf-8-sig')) if args.compare else None
    raise SystemExit(asyncio.run(main(args, batch, comparison)))
