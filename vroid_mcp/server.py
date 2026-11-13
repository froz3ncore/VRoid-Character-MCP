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

from anyio import CancelScope
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from . import (toolset, tools_accessories, tools_capture, tools_hair, tools_parameters,
               tools_wear, tools_ordinary, tools_groups, tools_catalog, bridge)
from .runtime import Runtime
from .exception_notes import add_exception_note
from .runtime_handle import RuntimeHandle
from . import batch, tools_help, tools_session
from .runtime_session import UNKNOWN_MODEL_FIELDS
from .texture_tools import register_texture_tools
from .workflow import REFERENCE_GUIDANCE

INSTRUCTIONS = (
    'This server normally drives one disposable VRoid Studio copy through its managed API. '
    'attach_open_vroid explicitly switches to an existing user-opened process; edits then affect '
    'the real unsaved session and its own profile, and the lab guard is not loaded. '
    'detach_open_vroid leaves that process running. save_as creates a new lab copy while preserving '
    'the attached character file association and dirty state. save_character saves in place with '
    'a verified backup; save_character_as creates and associates a new file. new_character '
    'requires explicit discard and follows native exit sequencing. Attached file IO accepts absolute paths. '
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
) + REFERENCE_GUIDANCE
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
EDIT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)


async def _finish_owned(operation):
    """Hold the caller's session gate through the full lifecycle transaction."""
    worker = asyncio.create_task(operation)
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError as cancelled:
        with CancelScope(shield=True):
            while not worker.done():
                try:
                    await asyncio.shield(worker)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
        if not worker.cancelled() and worker.exception() is not None:
            add_exception_note(cancelled, 'Session worker failed: ' + str(worker.exception()))
        raise


class _VRoidServer(FastMCP):
    async def call_tool(self, name, arguments):
        # The SDK's default argument model drops extras before invoking the
        # registered function. Check the original write request first.
        tool = self._tool_manager.get_tool(name)
        if tool and tool.annotations and tool.annotations.readOnlyHint is False:
            batch.check_argument_names(tool, arguments)
        return await super().call_tool(name, arguments)


def create_server(lab: Path, variant: str, model_file: Path | None = None) -> FastMCP:
    runtime = RuntimeHandle(Runtime(lab))
    state = {'initialized': False, 'retained_pending': None, 'stopped': False}
    gate = batch.SessionGate()
    session_gate = gate.hold

    def retain_pending(phase, failure, cleanup):
        state['retained_pending'] = {'phase': phase, 'error': str(failure), 'cleanup': cleanup}

    def rebind_runtime():
        if getattr(runtime.current, 'exit_stopped', False):
            state['stopped'] = True
        runtime.rebind(Runtime(lab))
        state.update(initialized=False, retained_pending=None)

    async def close_runtime(phase='teardown', failure=None, *, rebind=True):
        async def finish():
            try:
                closed = await asyncio.to_thread(runtime.current.close)
            except BaseException as error:
                retain_pending(phase, failure or error, {'cleanup_error': str(error)})
                if failure is not None:
                    add_exception_note(failure, 'Session cleanup failed; runtime retained: ' + str(error))
                raise
            if closed.get('close_blocked'):
                if failure is not None:
                    retain_pending(phase, failure, closed)
                    add_exception_note(failure, 'NATIVE_WORK_PENDING; runtime retained: ' + str(closed))
            elif rebind:
                rebind_runtime()
            return closed
        # Rebinding/retaining belongs to the owned operation too. The client
        # can disappear after release succeeds but before its result is delivered.
        return await _finish_owned(finish())

    async def cleanup_failed(phase, failure):
        try:
            with CancelScope(shield=True):
                await close_runtime(phase, failure)
        except BaseException:
            # close_runtime already reconciled the exact worker result. Preserve
            # the original failure, including any notes from blocked cleanup.
            raise failure

    async def initialize_runtime(explicit=False) -> None:
        if state['retained_pending'] is not None:
            raise RuntimeError('SESSION_CLEANUP_PENDING: inspect get_status and explicitly close the retained session; automatic initialization is blocked')
        if getattr(runtime.current, 'exit_watch', None):
            raise RuntimeError('GRACEFUL_EXIT_PENDING')
        if (state['stopped'] or getattr(runtime.current, 'exit_stopped', False)) and not explicit:
            raise RuntimeError('SESSION_STOPPED: use restart_session to start another copy')
        if state['initialized']:
            return
        try:
            await _finish_owned(asyncio.to_thread(runtime.current.start))
            await runtime.current.initialize(variant, model_file)
            state['initialized'] = True
        except BaseException as failure:
            await cleanup_failed('initialization', failure)
            raise

    @asynccontextmanager
    async def lifespan(server):
        primary = None
        try:
            yield runtime.current
        except BaseException as error:
            primary = error
            raise
        finally:
            try:
                async with session_gate():
                    closed = await close_runtime(rebind=False)
                if closed.get('close_blocked'):
                    raise RuntimeError('NATIVE_WORK_PENDING: runtime/session retained: ' + str(closed))
            except BaseException as cleanup_error:
                if primary is None:
                    raise
                add_exception_note(primary, 'Session shutdown incomplete; runtime retained: ' + str(cleanup_error))

    mcp = _VRoidServer('VRoid Character MCP', lifespan=lifespan, instructions=INSTRUCTIONS)

    def ready_tool(**options):
        """Register the tool now, launch the app on first use."""
        owned_disposable = options.pop('owned_disposable', False)
        def register(function):
            @wraps(function)
            async def ready(*args, **kwargs):
                async with session_gate():
                    if owned_disposable:
                        # Refuse before initialization, dirty-state bookkeeping
                        # or an attached edit receipt can touch a real session.
                        from inspect import signature
                        bound = signature(function).bind(*args, **kwargs)
                        if runtime.current.mode != 'copy':
                            raise ValueError('OWNED_COPY_REQUIRED')
                        from .runtime_situation import validate_situation_request
                        bound.apply_defaults()
                        validate_situation_request(**bound.arguments)
                    # A failed, uninitialized session can still own native work.
                    # Status is a synthetic recovery receipt in that state; every
                    # ordinary tool is blocked before startup or native dispatch.
                    synthetic = (state['retained_pending'] is not None or state['stopped']
                                 or getattr(runtime.current,'exit_watch',None) or getattr(runtime.current,'exit_stopped',False))
                    if not (synthetic and function.__name__ == 'get_status'):
                        await initialize_runtime()
                    current = runtime.current
                    edit = (options.get('annotations') and not options['annotations'].readOnlyHint
                            and function.__name__ not in {'editor_camera', 'face_preview', 'sync_preset_cache'})
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
                        definite_hair_prewrite = (function.__name__ in {'scale_brush_hair', 'clone_brush_hair', 'set_procedural_hair'}
                            and isinstance(result, dict) and result.get('dispatch_state') == 'prewrite_rejected'
                            and result.get('native_invocation_attempted') is False
                            and result.get('attached_prewrite_verified') is True
                            and result.get('uncertain') is False)
                        rejected_history = (function.__name__ in {'undo','redo'} and isinstance(result,dict)
                                            and result.get('dispatched') is False)
                        if isinstance(result, dict) and result.get('ok') is False and not (definite_hair_prewrite or rejected_history):
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
        async with session_gate():
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
            closed = await close_runtime()
            if closed.get('close_blocked'):
                return {**closed, 'attached': False}
            try:
                await _finish_owned(asyncio.to_thread(runtime.current.attach, pid))
                adopted = await runtime.current.adopt()
                state['initialized'] = True
                status = await runtime.current.status()
                state['stopped'] = False
                return {**status, 'adopted': adopted,
                        'notice': 'Editing the real VRoid session; isolation guard is not loaded.'}
            except BaseException as failure:
                await cleanup_failed('adoption', failure)
                raise

    def after_detach(closed):
        next_action = ('Use restart_session(discard_unsaved=true) to start a new copy' if state['stopped']
                       else 'Next normal tool call starts a new copy')
        return {'detached': True, 'mode': 'copy', 'release': closed, 'next': next_action}

    @mcp.tool(annotations=EDIT)
    async def detach_open_vroid() -> dict:
        """Detach from the user-opened VRoid without closing its process or saving it."""
        async with session_gate():
            if runtime.current.mode != 'attached':
                return {'detached': False, 'mode': runtime.current.mode}
            closed = await close_runtime()
            if closed.get('close_blocked'):
                return closed
            return after_detach(closed)

    @mcp.tool(annotations=DESTRUCTIVE)
    async def restart_session(discard_unsaved: bool = False) -> dict:
        """Recreate only this MCP-owned VRoid copy, discarding its unsaved changes.

        Requires explicit discard_unsaved=true. Save first when you can; this is not
        a way to silently drop a user's work. The new model token invalidates every
        id issued before it. It also recovers from COPY_DISCONNECTED or an uncertain
        native call, and other VRoid processes are never touched.
        """
        async with session_gate():
            if (runtime.current.mode == 'attached' and not getattr(runtime.current,'exit_stopped',False)
                    and not getattr(runtime.current,'exit_watch',None)):
                closed = await close_runtime()
                if closed.get('close_blocked'):
                    return closed
                return after_detach(closed)
            if discard_unsaved is not True:
                raise ValueError('Explicit discard_unsaved=true required; this discards the MCP copy unsaved changes')
            closed = await close_runtime()
            if closed.get('close_blocked'):
                return closed
            await initialize_runtime(explicit=True)
            state['stopped'] = False
            return await runtime.current.status()

    @ready_tool(annotations=READ_ONLY)
    async def get_status() -> dict:
        """Report the copy, current model, background work and model update state.

        The response also carries tool_count and toolset_hash, so a client that
        cached an older tool list can tell whether it needs to reload instead of
        guessing.
        """
        if state['retained_pending'] is None and getattr(runtime.current,'exit_watch',None):
            closed = runtime.current.close()
            if closed.get('native_process_stopped'):
                state['stopped'] = True
        if state['retained_pending'] is not None:
            status = {'mode': runtime.current.mode, 'pid': getattr(runtime.current, 'pid', None),
                'model_ready': False, 'writes_blocked': True, 'pending_session': True,
                'reason': 'SESSION_CLEANUP_PENDING', 'retained_session': state['retained_pending'],
                'recovery': 'Explicit detach_open_vroid for attached sessions, or restart_session(discard_unsaved=true) for an owned copy; cleanup must succeed before another session starts'}
        elif state['stopped'] or getattr(runtime.current,'exit_stopped',False) or getattr(runtime.current,'exit_watch',None):
            # An outstanding exact-process watch belongs to this runtime. An
            # older no-auto-start latch alone cannot prove the watched process exited.
            stopped = not bool(getattr(runtime.current,'exit_watch',None))
            status = {'mode':runtime.current.mode, 'pid':runtime.current.pid, 'model_ready':False,
                      'writes_blocked':True, 'stopped':stopped, 'connected':False if stopped else None,
                      'reason':'SESSION_STOPPED' if stopped else 'GRACEFUL_EXIT_PENDING'}
        else:
            status = await runtime.current.status()
        status = {**UNKNOWN_MODEL_FIELDS, **status}
        status['in_place_save_supported'] = runtime.current.mode == 'attached'
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
        Dialogs, import tasks, VRM export and registered-item loading/selection
        must finish before review. If their original agent was lost, process
        exit may be the only available proof that native work has stopped.
        """
        async with session_gate():
            if getattr(runtime.current, 'exit_watch', None) or getattr(runtime.current, 'exit_stopped', False):
                raise RuntimeError('GRACEFUL_EXIT_IN_PROGRESS_OR_STOPPED: inspect get_status')
            if runtime.current.mode != 'attached':
                raise RuntimeError('ATTACHED_ONLY')
            return await runtime.current._call('attached_review')

    @mcp.tool(annotations=EDIT)
    async def acknowledge_attached_state(recovery_token: str) -> dict:
        """Resume attached edits after reviewing the actual state and interrupted tool.

        Use the fresh token from get_attached_state. A changed model, history,
        file association or busy state invalidates it. No operation is replayed.
        """
        async with session_gate():
            if getattr(runtime.current, 'exit_watch', None) or getattr(runtime.current, 'exit_stopped', False):
                raise RuntimeError('GRACEFUL_EXIT_IN_PROGRESS_OR_STOPPED: inspect get_status')
            if runtime.current.mode != 'attached':
                raise RuntimeError('ATTACHED_ONLY')
            result = await runtime.current._call('attached_acknowledge', {'recovery_token': recovery_token})
            if result.get('acknowledged') is not True:
                raise RuntimeError('ATTACHED_ACKNOWLEDGMENT_UNCONFIRMED')
            if getattr(runtime.current, '_pending_custom_item_pins', None):
                runtime.current.release_source_pins()
            runtime.current.uncertain = False
            return result

    for module in (tools_wear, tools_parameters, tools_hair, tools_accessories, tools_capture, tools_ordinary, tools_groups):
        module.register(ready_tool, runtime, lab, READ_ONLY, EDIT)
    register_texture_tools(ready_tool, runtime, lab, READ_ONLY, EDIT)
    def offline_tool(**options):
        def register(function):
            @wraps(function)
            async def serialized(*args, **kwargs):
                async with session_gate():
                    return await function(*args, **kwargs)
            return mcp.tool(**options)(serialized)
        return register

    async def transition(operation, args):
        async with session_gate():
            if not state['initialized'] or state['stopped'] or state['retained_pending']:
                raise RuntimeError('SESSION_NOT_ACTIVE: observe the active session first')
            result = await runtime.current.session_transition(operation, args)
            if operation == 'exit_vroid':
                state.update(stopped=True, initialized=False)
            return result

    def unsafe_batch_state():
        current = runtime.current
        return bool(current.dead or getattr(current, 'uncertain', False) or state['retained_pending']
                    or getattr(current, 'exit_watch', None))

    tools_catalog.register(offline_tool, ready_tool, runtime, lab, READ_ONLY, EDIT)
    tools_session.register(mcp, transition, DESTRUCTIVE)
    batch.register(mcp, gate, unsafe_batch_state, DESTRUCTIVE)
    tools_help.register(mcp, READ_ONLY)
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
