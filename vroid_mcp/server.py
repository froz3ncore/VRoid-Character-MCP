"""MCP server factory for one disposable VRoid copy.

The tools themselves live in per-domain modules (`tools_wear`, `tools_parameters`,
`tools_hair`, `tools_accessories`, `tools_capture`, `texture_tools`). This module
owns the pieces that cannot move: the process lifecycle, the gate that starts
Unity on the first tool call, and the two tools that operate on the session
itself.

`restart_session` replaces the runtime object, so the domains receive a
RuntimeHandle rather than the object: a restarted session is visible to every
already-registered tool.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from functools import wraps
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from . import (toolset, tools_accessories, tools_capture, tools_hair, tools_parameters,
               tools_wear, tools_ordinary, bridge)
from .runtime import Runtime
from .runtime_handle import RuntimeHandle
from .texture_tools import register_texture_tools

INSTRUCTIONS = (
    'This server normally drives one disposable VRoid Studio copy through its managed API. '
    'attach_open_vroid explicitly switches to an existing user-opened process; edits then affect '
    'the real unsaved session and its own profile, and the lab guard is not loaded. '
    'detach_open_vroid leaves that process running. Save attached character files in VRoid itself; '
    'save_custom_items writes new items to that window\'s native closet. Attached texture entry '
    'uses Unity-owned callbacks that survive host exit. Dialogs block writes. An interrupted '
    'edit requires get_attached_state, inspection, and acknowledge_attached_state before resuming. '
    'Start with list_face_params and pass the model_token it returns as expected_model. '
    'list_parameters covers the face, body, clothing, colours, expressions, general, hair, '
    'hair-bone, accessory and photo domains: hair needs a category and a node scope, an '
    'accessory needs its instance, and an expression may take its id as scope. '
    'list_hair_nodes yields the hair scopes and list_accessories the accessory instances. '
    'Values are typed: float, int, bool, enum index, RGBA colour, vector3, quaternion or '
    'curve control points. set_height takes a measured centimetre target and verifies it. '
    'Write with set_parameters only after a fresh list, because a preset change or a hair '
    'structure change invalidates the ids you were holding. '
    'capture_review before and after an edit returns native multi-view images with the '
    'parameter differences, and those images must be inspected before judging appearance. '
    'Dress-up is separate from ordinary editing: get_wear_status yields the wear_token that '
    'open_wear_project, import_xwear, set_wear_fit, set_wear_animation and save_wear_project '
    'take as expected_wear, and the item list must be relisted after an import. '
    'get_wear_snapshot and capture_wear_review describe the actual assembly, and the preview '
    'has to be stopped before fitting or saving. Parameter editing and capture_review never '
    'act on the assembly. '
    'Preset lists carry stable ids and descriptive English names where known; keep the native '
    'ids. Parameter lists keep the native labels and write ids and add semantic bindings with '
    'an exact-key English correction where known: a semantic key may repeat and is never a '
    'write id. '
    'Colour entries expose the real binding values, mixed aggregates and shared aliases: use '
    'the separate left and right eye ids for heterochromia, note that BothEyes writes both, '
    'and read affected_parameter_ids before touching a shared colour. '
    'preview_presets returns native thumbnails for one to six ids. '
    'export_wear_vrm writes the actual assembly with restrictive native metadata defaults. '
    'export_vrm exports an ordinary edit model to the lab with its native metadata and permissions. '
    'Nothing here uses desktop input or a freehand brush; texture tools work with native '
    'regions, layers and UV export plus PNG layer import. '
    'Batches follow native history, so one edit may need several undo steps.'
)
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
EDIT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)


def create_server(lab: Path, variant: str, model_file: Path | None = None) -> FastMCP:
    runtime = RuntimeHandle(Runtime(lab))
    state = {'initialized': False}
    session_gate = asyncio.Lock()

    async def initialize_runtime() -> None:
        if state['initialized']:
            return
        try:
            await asyncio.to_thread(runtime.current.start)
            await runtime.current.initialize(variant, model_file)
            state['initialized'] = True
        except BaseException as failure:
            await asyncio.to_thread(runtime.current.close)
            runtime.rebind(Runtime(lab))
            raise

    @asynccontextmanager
    async def lifespan(server):
        try:
            yield runtime.current
        finally:
            await asyncio.to_thread(runtime.current.close)

    mcp = FastMCP('VRoid Character MCP', lifespan=lifespan, instructions=INSTRUCTIONS)

    def ready_tool(**options):
        """Register the tool now, launch the app on first use."""
        def register(function):
            @wraps(function)
            async def ready(*args, **kwargs):
                async with session_gate:
                    await initialize_runtime()
                    current = runtime.current
                    edit = options.get('annotations') and not options['annotations'].readOnlyHint
                    receipt = None
                    if current.mode == 'attached' and edit:
                        receipt = await current._call('attached_edit_begin', {'tool': function.__name__})
                    try:
                        result = await function(*args, **kwargs)
                    except BaseException:
                        if receipt:
                            try:
                                finished = await current._call('attached_edit_finish', {
                                    'id': receipt['id'], 'success': False, 'uncertain': current.uncertain})
                                current.uncertain |= finished['needs_review']
                            except BaseException:
                                current.uncertain = True
                        raise
                    if receipt:
                        if isinstance(result, dict) and result.get('ok') is False:
                            current.uncertain = True
                        try:
                            finished = await current._call('attached_edit_finish', {
                                'id': receipt['id'], 'success': not current.uncertain, 'uncertain': current.uncertain})
                            current.uncertain |= finished['needs_review']
                        except BaseException:
                            current.uncertain = True
                            raise
                    return result
            return mcp.tool(**options)(ready)
        return register

    @mcp.tool(annotations=DESTRUCTIVE)
    async def attach_open_vroid(pid: int | None = None, discard_copy_unsaved: bool = False) -> dict:
        """Attach to a user-opened VRoid process without closing it on detach.

        Edits act on that real session, including its unsaved model. If the MCP
        copy is running, explicitly set discard_copy_unsaved after saving it.
        Multiple candidate processes require a PID. Other MCP labs are excluded.
        Attached mode does not load the lab isolation guard. Save character files
        in VRoid itself; custom item saves use the target window's profile.
        """
        async with session_gate:
            candidates = await asyncio.to_thread(bridge.find_open_vroid, lab)
            if pid is None:
                if len(candidates) != 1:
                    raise ValueError('Select one eligible VRoid PID: ' + str(candidates))
                pid = candidates[0]['pid']
            if not any(item['pid'] == pid and item['path'] for item in candidates):
                raise ValueError('No eligible inspectable VRoid process for this PID')
            current = runtime.current
            if state['initialized'] and current.mode == 'attached' and current.pid == pid and not current.dead:
                return await current.status()
            if state['initialized'] and current.mode == 'copy' and not current.dead and not discard_copy_unsaved:
                raise ValueError('Save the running MCP copy or explicitly set discard_copy_unsaved=true')
            # Validate the executable before touching the current session.
            target = next(item for item in candidates if item['pid'] == pid)
            await asyncio.to_thread(bridge.validate_assembly, Path(target['path']).parent / 'GameAssembly.dll')
            await asyncio.to_thread(current.close)
            runtime.rebind(Runtime(lab))
            state['initialized'] = False
            try:
                await asyncio.to_thread(runtime.current.attach, pid)
                adopted = await runtime.current.adopt()
                state['initialized'] = True
                return {**await runtime.current.status(), 'adopted': adopted,
                        'notice': 'Editing the real VRoid session; isolation guard is not loaded.'}
            except BaseException:
                await asyncio.to_thread(runtime.current.close)
                runtime.rebind(Runtime(lab))
                raise

    @mcp.tool(annotations=EDIT)
    async def detach_open_vroid() -> dict:
        """Detach from the user-opened VRoid without closing its process or saving it."""
        async with session_gate:
            if runtime.current.mode != 'attached':
                return {'detached': False, 'mode': runtime.current.mode}
            closed = await asyncio.to_thread(runtime.current.close)
            runtime.rebind(Runtime(lab))
            state['initialized'] = False
            return {'detached': True, 'mode': 'copy', 'release': closed, 'next': 'Next normal tool call starts a new copy'}

    @mcp.tool(annotations=DESTRUCTIVE)
    async def restart_session(discard_unsaved: bool = False) -> dict:
        """Recreate only this MCP-owned VRoid copy, discarding its unsaved changes.

        Requires explicit discard_unsaved=true. Save first when you can; this is not
        a way to silently drop a user's work. The new model token invalidates every
        id issued before it. It also recovers from COPY_DISCONNECTED or an uncertain
        native call, and other VRoid processes are never touched.
        """
        async with session_gate:
            if runtime.current.mode == 'attached':
                closed = await asyncio.to_thread(runtime.current.close)
                runtime.rebind(Runtime(lab))
                state['initialized'] = False
                return {'detached': True, 'mode': 'copy', 'release': closed, 'next': 'Next normal tool call starts a new copy'}
            if discard_unsaved is not True:
                raise ValueError('Explicit discard_unsaved=true required; this discards the MCP copy unsaved changes')
            await asyncio.to_thread(runtime.current.close)
            runtime.rebind(Runtime(lab))
            state['initialized'] = False
            await initialize_runtime()
            return await runtime.current.status()

    @ready_tool(annotations=READ_ONLY)
    async def get_status() -> dict:
        """Report the copy, current model, background work and model update state.

        The response also carries tool_count and toolset_hash, so a client that
        cached an older tool list can tell whether it needs to reload instead of
        guessing.
        """
        status = await runtime.current.status()
        try:
            status.update(await toolset.live_summary(mcp))
        except Exception as error:  # tool enumeration must never hide model state
            status['toolset_error'] = str(error)
        return status

    @mcp.tool(annotations=READ_ONLY)
    async def get_attached_state() -> dict:
        """Inspect the attached window and any interrupted edit, producing a fresh recovery token.

        Inspect parameters, layers and created files before acknowledging an
        interrupted operation. This never retries or reverses the operation.
        Dialogs and active native work must finish before review.
        """
        async with session_gate:
            if runtime.current.mode != 'attached':
                raise RuntimeError('ATTACHED_ONLY')
            return await runtime.current._call('attached_review')

    @mcp.tool(annotations=EDIT)
    async def acknowledge_attached_state(recovery_token: str) -> dict:
        """Resume attached edits after reviewing the actual state and interrupted tool.

        Use the fresh token from get_attached_state. A changed model, history,
        file association or busy state invalidates it. No operation is replayed.
        """
        async with session_gate:
            if runtime.current.mode != 'attached':
                raise RuntimeError('ATTACHED_ONLY')
            result = await runtime.current._call('attached_acknowledge', {'recovery_token': recovery_token})
            runtime.current.uncertain = False
            return result

    for module in (tools_wear, tools_parameters, tools_hair, tools_accessories, tools_capture, tools_ordinary):
        module.register(ready_tool, runtime, lab, READ_ONLY, EDIT)
    register_texture_tools(ready_tool, runtime, lab, READ_ONLY, EDIT)
    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Local VRoid character MCP; always launches a designated copy.')
    parser.add_argument('--lab', required=True, type=Path,
                        help='Directory containing a physical app/VRoidStudio.exe copy')
    parser.add_argument('--variant', choices=['F00', 'M00'], default='F00')
    parser.add_argument('--model', type=Path,
                        help='Optional .vroid already inside the lab; otherwise creates a new model')
    args = parser.parse_args()
    create_server(args.lab, args.variant, args.model).run(transport='stdio')


if __name__ == '__main__':
    main()
