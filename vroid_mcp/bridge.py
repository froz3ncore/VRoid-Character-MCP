"""Spawn, attach to and call into one disposable VRoid copy.

The plumbing lives here as functions that take the runtime object as their
subject, instead of an object that owns it. That keeps every piece of state on
`Runtime` (lab, script, lock, dead, uncertain, run directory), which is what the
unit tests stub when they simulate a native session - and it keeps Frida out of
every other module.

A native call that does not answer is treated as "unknown", never as success:
the model may already have changed, so the session is marked uncertain and
further calls are refused until a restart.
"""

from __future__ import annotations

import asyncio
from contextvars import copy_context
import hashlib
import json
import os
import pathlib
import time
import threading
import uuid
from typing import Any

import frida

from . import closet_guard, lab_lock, edit_sequence, attached_ui
from .supported_builds import BUILDS, validate_assembly, assembly_identity

PROJECT = pathlib.Path(__file__).resolve().parents[1]

# Load order matters: the guard runs before anything resolves a path, the bridge
# defines Il2Cpp, the main-thread host installs the queue, and the operation
# modules register into `globalThis.vroid` last.
AGENT_MODULES = (
    'build_profiles.js',
    'attachment_lease.js',
    'native_png_decoder.js',
    'attached_png_decoder.js',
    'main_thread.js',
    'parameter_semantics.js',
    'color_state.js',
    'capture_quality.js',
    'capture_framing.js',
    'editor_preview.js',
    'editor_capture.js',
    'capture_scope.js',
    'photo_capture.js',
    'app_frame.js',
    'parameters.js',
    'texture_layers.js',
    'texture_pixels.js',
    'advanced_materials.js',
    'texture_native.js',
    'textures.js',
    'wear.js',
    'body_reference.js',
    'preset_previews.js',
    'vrm_export.js',
    'ordinary_extensions.js',
    'attached_state.js',
    'session_workflows.js',
    'groups.js',
    'catalog.js',
    'hair_procedural.js',
    'hair_procedural_fallback.js',
    'hair_groups.js',
    'operations.js',
)
GUARD_MODULE = 'profile_guard.js'

# A dense geometry capture serializes tens of megabytes; edits stay bounded.
SLOW_OPERATIONS = {'capture_wear_reference': 120}
DEFAULT_TIMEOUT_SECONDS = 30

PROFILE_FOLDERS = (
    'Documents',
    'AppData/Local',
    'AppData/LocalLow/pixiv/VRoid Studio/custom_items',
    'AppData/LocalLow/pixiv/VRoid Studio/XWear/Closet',
    'AppData/Roaming',
    'Temp',
)

DISCONNECTED = {
    'model_ready': False,
    'connected': False,
    'writes_blocked': True,
    'reason': 'COPY_DISCONNECTED',
    'recovery': 'restart_session requires discard_unsaved=true',
}


def disconnected_status(subject) -> dict:
    result = dict(DISCONNECTED)
    if getattr(subject, 'mode', 'copy') == 'attached':
        result.update(mode='attached', reason='ATTACHED_VROID_DISCONNECTED',
                      recovery='detach or attach again; the MCP does not close the user process')
    return result


def script_text(config: dict | None, bridge_js: pathlib.Path, attached: bool = False,
                assembly_sha256: str | None = None) -> str:
    """Concatenate the agent into one script with the probe config in front."""
    build = BUILDS.get(assembly_sha256)
    parts = ['const ATTACHED=' + json.dumps(attached) + ';',
             'const VROID_ASSEMBLY_SHA256=' + json.dumps(assembly_sha256) + ';',
             'const VROID_PRODUCT_VERSION=' + json.dumps(build.version if build else None) + ';',
             'const ATTACHED_OWNER_PID=' + str(os.getpid()) + ';',
             (PROJECT / 'agent' / 'native_traps.js').read_text(encoding='utf-8')]
    if not attached:
        parts.extend(['const PROBE=' + json.dumps(config) + ';',
                      (PROJECT / 'agent' / GUARD_MODULE).read_text(encoding='utf-8')])
    parts.append(bridge_js.read_text(encoding='utf-8'))
    parts.extend((PROJECT / 'agent' / name).read_text(encoding='utf-8') for name in AGENT_MODULES)
    return '\n'.join(parts)


def record(subject, data: dict) -> None:
    subject.events.append({'time': time.time(), **data})
    with (subject.run_dir / 'bridge.jsonl').open('a', encoding='utf-8') as output:
        output.write(json.dumps(subject.events[-1], ensure_ascii=False) + '\n')


def prepare_run_directory(subject) -> None:
    subject.run_dir.mkdir(parents=True)


def _check_copy(subject) -> str:
    if os.name != 'nt':
        raise RuntimeError('This prototype is validated only on Windows')
    if not subject.exe.is_file() or not subject.bridge_js.is_file():
        raise FileNotFoundError('VRoid copy or frida-il2cpp-bridge is missing')
    # A junction here would redirect every native call into the real install.
    if subject.exe.resolve() != subject.exe or (subject.lab / 'app').resolve() != subject.lab / 'app':
        raise ValueError('app/ must be a physical copy, not a link')
    return assembly_identity(subject.lab / 'app/GameAssembly.dll')['sha256']


def _environment(subject) -> dict:
    profile = subject.lab / 'profile'
    for relative in PROFILE_FOLDERS:
        (profile / relative).mkdir(parents=True, exist_ok=True)
    temp = profile / 'Temp'
    env = dict(os.environ)
    env.update(USERPROFILE=str(profile), APPDATA=str(profile / 'AppData/Roaming'),
               LOCALAPPDATA=str(profile / 'AppData/Local'), TEMP=str(temp), TMP=str(temp))
    return env


def _probe_config(subject) -> dict:
    # One registry hive per lab path, so two labs never share preferences.
    suffix = hashlib.sha256(str(subject.lab).lower().encode()).hexdigest()[:16]
    return {'root': str(subject.lab), 'exe': str(subject.exe),
            'originalProfile': os.environ['USERPROFILE'], 'excludedPids': [],
            'registryKey': 'Software\\VRoidFaceMCP\\' + suffix}


def _detached(subject, reason, *unused) -> None:
    subject.dead = True
    record(subject, {'event': 'detached', 'reason': reason})


def start(subject) -> None:
    assembly_sha256 = _check_copy(subject)
    # Refuse before taking the lock: a process that cannot run would die mid-way
    # and leave the save state unknown.
    subject.crash_guard = closet_guard.enforce(subject.lab)
    subject.file_lock = lab_lock.acquire(subject.lab)
    subject.lab_owner = os.getpid()
    prepare_run_directory(subject)
    env = _environment(subject)
    subject.device = frida.get_local_device()
    try:
        argv = [str(subject.exe), '-logFile', str(subject.run_dir / 'Player.log'),
                '-screen-fullscreen', '0', '-screen-width', '960', '-screen-height', '720']
        subject.pid = subject.device.spawn(argv, cwd=str(subject.exe.parent), env=env, stdio='pipe')
        subject.owns_process = True
        subject.session = subject.device.attach(subject.pid)
        subject.session.on('detached', lambda reason, *rest: _detached(subject, reason))
        subject.script = subject.session.create_script(script_text(_probe_config(subject), subject.bridge_js,
                                                                  assembly_sha256=assembly_sha256))
        subject.script.on('message',
                          lambda message, data: record(subject, {'event': 'agent', 'message': message}))
        subject.script.load()
        subject.device.resume(subject.pid)
        record(subject, {'event': 'spawned-copy', 'pid': subject.pid, 'exe': str(subject.exe)})
    except BaseException:
        close(subject)
        raise


def find_open_vroid(lab: pathlib.Path) -> list[dict]:
    """Find inspectable VRoid processes, excluding all managed MCP labs."""
    candidates = []
    for process in frida.get_local_device().enumerate_processes(scope='full'):
        if process.name.lower() != 'vroidstudio.exe':
            continue
        path = process.parameters.get('path')
        if not path:
            candidates.append({'pid': process.pid, 'path': None})
            continue
        exe = pathlib.Path(path).resolve()
        # Do not claim another MCP lab's process, even when it is not our lab.
        if (exe.parent.parent / '.mcp-owner.lock').exists():
            continue
        if exe.is_relative_to(lab.resolve() / 'app'):
            continue
        candidates.append({'pid': process.pid, 'path': str(exe)})
    return sorted(candidates, key=lambda p: p['pid'])


def attach(subject, pid: int) -> None:
    if os.name != 'nt' or not subject.bridge_js.is_file():
        raise RuntimeError('Attached VRoid requires Windows and frida-il2cpp-bridge')
    target = next((p for p in find_open_vroid(subject.lab) if p['pid'] == pid), None)
    if target is None:
        raise ValueError('PID is not an eligible external VRoid process')
    if not target['path']:
        raise PermissionError('VRoid process path is unavailable; check process privileges')
    exe = pathlib.Path(target['path'])
    assembly_sha256 = assembly_identity(exe.parent / 'GameAssembly.dll')['sha256']
    subject.file_lock = lab_lock.acquire(subject.lab)
    subject.lab_owner = os.getpid()
    prepare_run_directory(subject)
    subject.mode, subject.target = 'attached', str(exe)
    subject.device = frida.get_local_device()
    try:
        subject.session = subject.device.attach(pid)
        subject.pid = pid
        subject.session.on('detached', lambda reason, *rest: _detached(subject, reason))
        subject.script = subject.session.create_script(script_text(None, subject.bridge_js, attached=True,
                                                                  assembly_sha256=assembly_sha256))
        subject.script.on('message', lambda message, data: record(subject, {'event': 'agent', 'message': message}))
        subject.script.load()
        record(subject, {'event': 'attached', 'pid': pid, 'exe': str(exe)})
    except BaseException:
        close(subject)
        raise


async def adopt(subject) -> dict:
    deadline = time.monotonic() + 30
    while True:
        health = await asyncio.to_thread(subject.script.exports_sync.health)
        if health['error']:
            raise RuntimeError(health['error'])
        if health['ready']:
            break
        if time.monotonic() > deadline:
            raise TimeoutError('Attached bridge did not become ready')
        await asyncio.sleep(.2)
    try:
        result = await _attached_rpc(subject, 'adopt', subject.script.exports_sync.adopt, (), 30)
        deadline = time.monotonic() + 30
        while True:
            png = await call(subject, 'native_png_status')
            if png.get('fatal') or not png.get('installed'):
                raise RuntimeError('ATTACHED_PNG_DECODER_UNAVAILABLE: ' + str(png))
            if not png['pending']:
                subject.native_png_decoder_ready = True
                state = await call(subject, 'status')
                subject.uncertain = bool(state.get('attached_state', {}).get('pending_edit'))
                return result
            if time.monotonic() > deadline:
                raise TimeoutError('Previous native PNG workers still running; attachment is not ready for edits')
            await asyncio.sleep(.1)
    except asyncio.TimeoutError:
        subject.uncertain = True
        raise TimeoutError('VRoid main thread did not respond; detach and retry after focusing the window')


class NativeCallNotSent(RuntimeError):
    """A host guard refused this operation before scheduling its Frida RPC."""


def pending_attached_workers(subject):
    return [name for name, done in getattr(subject, '_attached_workers', ()) if not done.is_set()]


async def _attached_rpc(subject, name, function, args, timeout):
    """Own the submitted worker even if its waiting task is canceled or times out."""
    done = threading.Event()
    def run():
        try:
            return function(*args)
        finally:
            done.set()
    previous = getattr(subject, '_attached_workers', ())
    subject._attached_workers = [(op, event) for op, event in previous if not event.is_set()] + [(name, done)]
    try:
        future = asyncio.get_running_loop().run_in_executor(None, copy_context().run, run)
    except BaseException:
        done.set()
        raise
    # A late failure is consumed even after the requesting client leaves.
    future.add_done_callback(lambda completed: None if completed.cancelled() else completed.exception())
    return await asyncio.wait_for(asyncio.shield(future), timeout)


async def call(subject, operation: str, args: dict | None = None) -> Any:
    if subject.dead or subject.script is None:
        if getattr(subject, 'mode', 'copy') == 'attached':
            raise NativeCallNotSent('ATTACHED_VROID_DISCONNECTED: detach or attach again')
        raise NativeCallNotSent('COPY_DISCONNECTED: restart the MCP server')
    attached = getattr(subject, 'mode', 'copy') == 'attached'
    if attached and operation in ('attached_review', 'attached_acknowledge', 'attached_edit_begin'):
        pending = pending_attached_workers(subject)
        if pending:
            raise NativeCallNotSent('ATTACHED_NATIVE_WORK_PENDING: ' + ', '.join(pending))
    inspectable = operation.startswith(('get_', 'list_', 'inspect_', 'search_', 'export_texture_', 'export_renderer_texture')) or operation in {
        'status', 'native_png_status', 'task_status', 'vrm_export_status', 'custom_item_state',
        'enter_category', 'custom_item_validate_poll', 'custom_item_application_state', 'preserving_preset_state', 'preserved_preset_readback',
        'attached_review', 'attached_acknowledge', 'attached_edit_finish'}
    if subject.uncertain and operation not in {'status', 'vrm_export_status'} and not (attached and inspectable):
        if attached:
            raise NativeCallNotSent('ATTACHED_EDIT_NEEDS_REVIEW: inspect get_attached_state and actual parameters, layers and files before acknowledge_attached_state; do not retry the interrupted tool')
        raise NativeCallNotSent('PREVIOUS_CALL_UNCERTAIN: restart; do not retry a mutation')
    timeout = SLOW_OPERATIONS.get(operation, DEFAULT_TIMEOUT_SECONDS)
    payload = args or {}
    if attached and operation == 'attached_edit_finish' and pending_attached_workers(subject):
        payload = {**payload, 'success':False, 'uncertain':True}
        subject.uncertain = True
    if getattr(subject, 'mode', 'copy') == 'attached':
        try:
            window = attached_ui.window_state(getattr(subject, 'pid', None))
        except OSError as error:
            raise NativeCallNotSent('ATTACHED_WINDOW_INSPECTION_FAILED: ' + str(error)) from error
        if window['blocked']:
            if operation == 'status':
                return {'model_ready': False, 'pid': subject.pid, 'current_state_unavailable': True,
                        'reason': 'ATTACHED_OS_MODAL_BLOCKED', 'window_state': window}
            raise NativeCallNotSent('ATTACHED_OS_MODAL_BLOCKED: finish the open Windows dialog in VRoid first; nothing dispatched')
        if operation in {'open_texture_editor', 'begin_clothing_edit', 'begin_hair_edit', 'open_wear_project'} and not getattr(subject, 'native_png_decoder_ready', False):
            raise RuntimeError('ATTACHED_HISTORY_UNKNOWN: prior manual body and texture edits cannot be verified; use a fresh isolated copy for this transition')
        if operation in {'open_model', 'new_model', 'wear_clear_save_path'}:
            raise RuntimeError('ATTACHED_FILE_OPERATION_REFUSED: save in VRoid; file operations belong to the isolated copy')
    if getattr(subject, 'native_png_decoder_ready', False) and operation in {
            'open_texture_editor', 'begin_clothing_edit', 'begin_hair_edit', 'close_texture_editor', 'open_wear_project',
            'new_model', 'open_model', 'replace_with_file', 'replace_with_new_character', 'save_character', 'save_as', 'enter_vrm_export'}:
        deadline = time.monotonic() + 30
        while True:
            png = await call(subject, 'native_png_status')
            if not png.get('installed') or png.get('fatal'):
                subject.uncertain = True
                raise RuntimeError('NATIVE_PNG_DECODER_UNAVAILABLE: ' + str(png))
            if png['pending'] == 0:
                break
            if time.monotonic() > deadline:
                subject.uncertain = True
                raise TimeoutError('Native PNG callbacks did not finish; transition was not attempted')
            await asyncio.sleep(.05)
    edit_sequence.before_call(subject, operation, payload)
    try:
        export = subject.script.exports_sync.call
        if operation == 'apply_registered_custom_item':
            from .preset_catalog import bind_custom_selection_export
            export = bind_custom_selection_export(export)
        if attached:
            result = await _attached_rpc(subject, operation, export, (operation, payload), timeout)
        else:
            result = await asyncio.wait_for(asyncio.to_thread(export, operation, payload), timeout)
        edit_sequence.after_call(subject, operation, payload, result)
        return result
    except asyncio.CancelledError:
        if attached and (not inspectable or operation in {'attached_edit_finish', 'attached_acknowledge'}):
            subject.uncertain = True
        raise
    except asyncio.TimeoutError:
        # No answer is not success: the model may have changed already.
        subject.uncertain = True
        raise RuntimeError('Native call timed out; result is uncertain and further calls are blocked')


async def initialize(subject, variant: str = 'F00', model_file: pathlib.Path | None = None) -> dict:
    async with subject.lock:
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            health = await asyncio.to_thread(subject.script.exports_sync.health)
            if health['error']:
                raise RuntimeError(health['error'])
            if health['ready']:
                subject.native_png_decoder_ready = bool(health.get('native_png_decoder_ready'))
                status_result = await call(subject, 'status')
                if not status_result.get('reason', '').startswith('Error: NOT_READY'):
                    break
            await asyncio.sleep(.2)
        else:
            raise TimeoutError('VRoid initialization timed out')
        if model_file is None:
            await call(subject, 'new_model', {'variant': variant})
        else:
            path = model_file.resolve()
            if not path.is_relative_to(subject.lab) or path.suffix.lower() != '.vroid' or not path.is_file():
                raise ValueError('Startup models must be .vroid files already inside the lab')
            await wait_task(subject, await call(subject, 'open_model', {'path': str(path)}))
        return await settle(subject)


async def wait_task(subject, task: dict) -> dict:
    from .task_receipt import ManagedTaskFailure
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        result = await call(subject, 'task_status', task)
        if result['completed']:
            if result['faulted'] or result['canceled']:
                raise ManagedTaskFailure(result.get('error', 'Operation canceled'),result)
            if result.get('result') is False:
                raise ManagedTaskFailure('MANAGED_TASK_FAILED: terminal Boolean result was false',result)
            return result
        await asyncio.sleep(.1)
    subject.uncertain = True
    raise TimeoutError('Managed task did not complete; restart before further changes')


async def settle(subject, after_frame: int = -1) -> dict:
    deadline = time.monotonic() + 30
    quiet = 0
    while time.monotonic() < deadline:
        result = await call(subject, 'status')
        png = result.get('png_decoder', {})
        if png.get('fatal'):
            subject.uncertain = True
            raise RuntimeError('NATIVE_PNG_DECODER_FAILED: ' + str(png['fatal']))
        idle = (result['model_ready'] and not result['updating']
                and not png.get('pending', 0)
                and not result.get('command_busy', False) and not result.get('photo_updating', False)
                and (result.get('photo_active', False) or not result.get('presets_loading', False)))
        if idle and result['frame'] >= after_frame + 2:
            quiet += 1
            if quiet >= 2:
                return result
        else:
            quiet = 0
        await asyncio.sleep(.1)
    subject.uncertain = True
    raise TimeoutError('Model did not finish updating: ' + json.dumps(result))


async def status(subject) -> dict:
    async with subject.lock:
        if subject.dead:
            return disconnected_status(subject)
        try:
            result = await call(subject, 'status')
        except frida.InvalidOperationError as error:
            if 'script has been destroyed' not in str(error):
                raise
            subject.dead = True
            return disconnected_status(subject)
        if result.get('png_decoder', {}).get('fatal'):
            subject.uncertain = True
        ui = result.get('attached_state', {})
        ui_blocked = bool(result.get('current_state_unavailable') or ui.get('dialog') or ui.get('notification')
                          or ui.get('progress_locked') or ui.get('popup_blocked')
                          or (getattr(subject, 'mode', 'copy') == 'attached' and not ui.get('active_screen')))
        result.update(connected=True, mode=getattr(subject, 'mode', 'copy'), target=getattr(subject, 'target', None),
                      writes_blocked=subject.uncertain or ui_blocked, lab=str(subject.lab),
                      crash_guard=subject.crash_guard,
                      wear_transition_guard=edit_sequence.wear_status(subject),
                      texture_editor_guard=edit_sequence.status(subject, result.get('model_token')))
        return result


def close(subject) -> dict:
    # Kill only the process this subject spawned: never a name-based kill.
    outcome = {'mode': getattr(subject, 'mode', 'copy')}
    pinned = bool(getattr(subject, '_pending_custom_item_pins', []))
    def blocked(reason, **details):
        subject.uncertain = True
        outcome.update(close_blocked=True,detached=False,reason=reason,**details)
        return outcome
    try:
        watch = getattr(subject, 'exit_watch', None)
        if watch is not None:
            try:
                if not watch.exited():
                    return blocked('GRACEFUL_EXIT_PENDING')
                watch.close()
            except Exception as error:
                return blocked('GRACEFUL_EXIT_UNCONFIRMED', error=str(error))
            subject.exit_stopped = True
            subject.exit_watch = None
            outcome['native_process_stopped'] = True
        elif getattr(subject, 'exit_stopped', False):
            outcome['native_process_stopped'] = True
        elif getattr(subject, 'mode', 'copy') == 'attached':
            pending = pending_attached_workers(subject)
            if pending and not subject.dead:
                return blocked('ATTACHED_NATIVE_WORK_PENDING', pending_work=pending)
            if (pinned or pending or subject.script is not None) and (subject.script is None or subject.dead):
                # A lost agent is not proof that the user's process stopped.
                try:
                    subject.device.get_process(subject.pid)
                except frida.ProcessNotFoundError:
                    outcome['native_process_stopped'] = True
                except Exception as error:
                    return blocked('ATTACHED_NATIVE_WORK_PENDING',release_error=str(error))
                else:
                    return blocked('ATTACHED_NATIVE_WORK_PENDING: agent unavailable; process still running')
            if subject.script is not None and not subject.dead:
                try:
                    released = subject.script.exports_sync.release()
                    if released.get('released') is not True:
                        return blocked('ATTACHED_NATIVE_WORK_PENDING',pending_work=released.get('pending_work', []),
                                       release=released)
                    outcome['background_restored'] = bool(released.get('released'))
                    record(subject, {'event': 'released', 'result': released})
                except Exception as error:
                    outcome.update(background_restored=False, release_error=str(error))
                    # Native resources may exist without a Python pin. Failed
                    # preflight cannot authorize script unload or session loss.
                    return blocked('ATTACHED_NATIVE_WORK_PENDING',release_error=str(error))
                try:
                    subject.script.unload()
                except frida.InvalidOperationError:
                    pass
            if subject.session is not None and not subject.dead:
                subject.session.detach()
            outcome['detached'] = True
        elif getattr(subject, 'owns_process', True) and subject.pid is not None and subject.device is not None and not subject.dead:
            try:
                subject.device.kill(subject.pid)
            except frida.ProcessNotFoundError:
                pass
            outcome['native_process_stopped'] = True
        elif pinned:
            if getattr(subject, 'owns_process', False) and subject.dead and subject.pid is not None and subject.device is not None:
                # Detach/disconnection is not termination. A dead owned session
                # may release its source pins only after the PID is proven absent;
                # never kill a surviving or reused PID during this recovery probe.
                try:
                    subject.device.get_process(subject.pid)
                except frida.ProcessNotFoundError:
                    outcome['native_process_stopped'] = True
                except Exception as error:
                    return blocked('NATIVE_WORK_PENDING: owned process liveness unknown',liveness_error=str(error))
                else:
                    return blocked('NATIVE_WORK_PENDING: disconnected owned process still exists')
            else:
                return blocked('NATIVE_WORK_PENDING: owned process termination not established')
    finally:
        if not outcome.get('close_blocked'):
            subject.dead = True
            if subject.file_lock:
                lab_lock.release(subject.file_lock)
                subject.file_lock = None
    return outcome


def run_directory(lab: pathlib.Path) -> pathlib.Path:
    stamp = time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
    return lab / 'runs' / stamp
