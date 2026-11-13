"""Compose the registered SDK tools under one task-owned session gate."""
import asyncio
import base64
import json
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Annotated

from mcp.types import CallToolResult, ImageContent, TextContent
from pydantic import Field, StrictBool


class SessionGate:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.holder = None
        self.owner = ContextVar('vroid_session_gate_owner', default=None)

    @asynccontextmanager
    async def hold(self):
        task = asyncio.current_task()
        owner = self.owner.get()
        if owner is task:
            yield
            return
        if owner is not None and owner is self.holder:
            raise RuntimeError('SESSION_GATE_CHILD_TASK: nested work belongs to another task')
        async with self.lock:
            self.holder = task
            token = self.owner.set(task)
            try:
                yield
            finally:
                self.owner.reset(token)
                self.holder = None


EXCLUDED = frozenset({
    'run_batch', 'restart_session', 'attach_open_vroid', 'detach_open_vroid',
    'acknowledge_attached_state', 'return_to_main_menu', 'exit_vroid',
    'create_from_menu', 'open_from_menu', 'new_character', 'open_character',
    'open_current_in_wear', 'open_wear_project', 'build_preset_thumbnails',
})
IMAGE_LIMIT = 8
BYTE_LIMIT = 16 * 1024 * 1024


def check_argument_names(tool, arguments):
    if arguments.keys() - tool.parameters.get('properties', {}).keys():
        raise ValueError('UNKNOWN_TOOL_ARGUMENT: ' + tool.name)


def _plan(mcp, operations):
    if not isinstance(operations, list) or not 1 <= len(operations) <= 200:
        raise ValueError('BATCH_SIZE: expected 1..200 operations')
    plan = []
    for index, op in enumerate(operations):
        if (not isinstance(op, dict) or op.keys() != {'tool', 'args'}
                or not isinstance(op['tool'], str) or not isinstance(op['args'], dict)):
            raise ValueError(f'BATCH_SHAPE at {index}: expected tool and object args')
        name = op['tool']
        tool = mcp._tool_manager.get_tool(name)
        if tool is None or name in EXCLUDED:
            raise ValueError(f'BATCH_TOOL_UNAVAILABLE at {index}: {name}')
        check_argument_names(tool, op['args'])
        if name in {'set_group_parameters', 'set_hair_material_color', 'colorize', 'recolor_texture_layer'}:
            meta = tool.fn_metadata
            meta.arg_model.model_validate(meta.pre_parse_json(op['args']))
        plan.append((tool, op['args']))
    return plan


def _failed(value):
    return isinstance(value, dict) and (value.get('ok') is False or bool(value.get('error'))
                                         or value.get('success') is False or _unsafe_result(value))


def _unsafe_result(value):
    return isinstance(value, dict) and (value.get('uncertain') is True or value.get('connected') is False
                                         or value.get('pending_session') is True)


def _read_text(text):
    try:
        return json.loads(text)
    except ValueError:
        return text


def register(mcp, gate, unsafe, edit):
    @mcp.tool(annotations=edit, structured_output=False)
    async def run_batch(operations: Annotated[list[dict], Field(min_length=1, max_length=200)],
                        stop_on_error: StrictBool = True, include_images: StrictBool = True
                        ) -> list[TextContent | ImageContent]:
        """Run 1..200 ordered {tool,args} calls. Nontransactional. Indices are zero-based.

        Validate all names/shapes first. Validate arguments and current model at each
        call. executed includes failed attempted calls. Uncertain sessions stop immediately.
        """
        plan = _plan(mcp, operations)
        results, images = [], []
        image_bytes = failed = 0
        stopped = stop_reason = None
        async with gate.hold():
            for index, (tool, args) in enumerate(plan):
                if unsafe():
                    stopped = index
                    stop_reason = 'session_unavailable'
                    break
                row = {'index': index, 'tool': tool.name, 'ok': True, 'result': [], 'images': []}
                unsafe_result = False
                try:
                    converted = await mcp.call_tool(tool.name, args)
                    if isinstance(converted, CallToolResult):
                        row['ok'] = not converted.isError
                        blocks = converted.content
                    else:
                        # Structured results can duplicate every byte of legacy images.
                        blocks = converted[0] if isinstance(converted, tuple) else converted
                    for block in blocks:
                        if isinstance(block, TextContent):
                            value = _read_text(block.text)
                            row['result'].append(value)
                            if _failed(value):
                                row['ok'] = False
                                unsafe_result |= _unsafe_result(value)
                        elif isinstance(block, ImageContent):
                            remaining = BYTE_LIMIT - image_bytes
                            if (include_images and len(images) < IMAGE_LIMIT
                                    and len(block.data) <= 4 * ((remaining + 2) // 3)):
                                size = len(base64.b64decode(block.data, validate=True))
                                if size <= remaining:
                                    row['images'].append({'index': len(images), 'bytes': size})
                                    images.append(block)
                                    image_bytes += size
                                    continue
                            row['images'].append({'omitted': True})
                except Exception as error:
                    row.update(ok=False, error=str(error))
                results.append(row)
                failed += int(not row['ok'])
                unavailable = unsafe() or unsafe_result
                if unavailable or (stop_on_error and not row['ok']):
                    stopped = index
                    stop_reason = 'session_unavailable' if unavailable else 'operation_failed'
                    break
        receipt = {'transactional': False, 'requested': len(plan), 'executed': len(results),
                   'failed': failed, 'stopped_at': stopped, 'stop_reason': stop_reason, 'results': results}
        return [TextContent(type='text', text=json.dumps(receipt, ensure_ascii=False)), *images]
