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
import hashlib
import json
import os
import pathlib
import time
import uuid
from typing import Any

import frida

from . import closet_guard, lab_lock, edit_sequence
from .supported_builds import validate_assembly

PROJECT = pathlib.Path(__file__).resolve().parents[1]

# Load order matters: the guard runs before anything resolves a path, the bridge
# defines Il2Cpp, the main-thread host installs the queue, and the operation
# modules register into `globalThis.vroid` last.
AGENT_MODULES = (
    'attachment_lease.js',
    'native_png_decoder.js',
    'main_thread.js',
    'parameter_semantics.js',
    'color_state.js',
    'capture_quality.js',
    'capture_framing.js',
    'parameters.js',
    'textures.js',
    'wear.js',
    'body_reference.js',
    'preset_previews.js',
    'ordinary_extensions.js',
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


def script_text(config: dict | None, bridge_js: pathlib.Path, attached: bool = False) -> str:
    """Concatenate the agent into one script with the probe config in front."""
    parts = ['const ATTACHED=' + json.dumps(attached) + ';',
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


def _check_copy(subject) -> None:
    if os.name != 'nt':
        raise RuntimeError('This prototype is validated only on Windows')
    if not subject.exe.is_file() or not subject.bridge_js.is_file():
        raise FileNotFoundError('VRoid copy or frida-il2cpp-bridge is missing')
    # A junction here would redirect every native call into the real install.
    if subject.exe.resolve() != subject.exe or (subject.lab / 'app').resolve() != subject.lab / 'app':
        raise ValueError('app/ must be a physical copy, not a link')
    validate_assembly(subject.lab / 'app/GameAssembly.dll')


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
    _check_copy(subject)
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
        subject.script = subject.session.create_script(script_text(_probe_config(subject), subject.bridge_js))
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
    validate_assembly(exe.parent / 'GameAssembly.dll')
    subject.file_lock = lab_lock.acquire(subject.lab)
    subject.lab_owner = os.getpid()
    prepare_run_directory(subject)
    subject.mode, subject.target = 'attached', str(exe)
    subject.device = frida.get_local_device()
    try:
        subject.session = subject.device.attach(pid)
        subject.pid = pid
        subject.session.on('detached', lambda reason, *rest: _detached(subject, reason))
        subject.script = subject.session.create_script(script_text(None, subject.bridge_js, attached=True))
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
        return await asyncio.wait_for(asyncio.to_thread(subject.script.exports_sync.adopt), 30)
    except asyncio.TimeoutError:
        subject.uncertain = True
        raise TimeoutError('VRoid main thread did not respond; detach and retry after focusing the window')


async def call(subject, operation: str, args: dict | None = None) -> Any:
    if subject.dead or subject.script is None:
        if getattr(subject, 'mode', 'copy') == 'attached':
            raise RuntimeError('ATTACHED_VROID_DISCONNECTED: detach or attach again')
        raise RuntimeError('COPY_DISCONNECTED: restart the MCP server')
    if subject.uncertain and operation != 'status':
        raise RuntimeError('PREVIOUS_CALL_UNCERTAIN: restart; do not retry a mutation')
    timeout = SLOW_OPERATIONS.get(operation, DEFAULT_TIMEOUT_SECONDS)
    payload = args or {}
    if getattr(subject, 'mode', 'copy') == 'attached':
        if operation in {'open_texture_editor', 'open_wear_project'}:
            raise RuntimeError('ATTACHED_HISTORY_UNKNOWN: prior manual body and texture edits cannot be verified; use a fresh isolated copy for this transition')
        if operation in {'save_as', 'open_model', 'new_model', 'save_wear_project', 'wear_clear_save_path', 'import_xwear'}:
            raise RuntimeError('ATTACHED_FILE_OPERATION_REFUSED: save in VRoid; file operations belong to the isolated copy')
    if getattr(subject, 'native_png_decoder_ready', False) and operation in {
            'open_texture_editor', 'close_texture_editor', 'open_wear_project',
            'new_model', 'open_model', 'save_as', 'enter_vrm_export'}:
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
        result = await asyncio.wait_for(
            asyncio.to_thread(subject.script.exports_sync.call, operation, payload), timeout)
        edit_sequence.after_call(subject, operation, payload, result)
        return result
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


async def wait_task(subject, task: dict) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        result = await call(subject, 'task_status', task)
        if result['completed']:
            if result['faulted'] or result['canceled']:
                raise RuntimeError(result.get('error', 'Operation canceled'))
            return
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
        result.update(connected=True, mode=getattr(subject, 'mode', 'copy'), target=getattr(subject, 'target', None),
                      writes_blocked=subject.uncertain, lab=str(subject.lab),
                      crash_guard=subject.crash_guard,
                      wear_transition_guard=edit_sequence.wear_status(subject),
                      texture_editor_guard=edit_sequence.status(subject, result.get('model_token')))
        return result


def close(subject) -> dict:
    # Kill only the process this subject spawned: never a name-based kill.
    outcome = {'mode': getattr(subject, 'mode', 'copy')}
    try:
        if getattr(subject, 'mode', 'copy') == 'attached':
            if subject.script is not None and not subject.dead:
                try:
                    released = subject.script.exports_sync.release()
                    outcome['background_restored'] = bool(released.get('released'))
                    record(subject, {'event': 'released', 'result': released})
                except Exception as error:
                    outcome.update(background_restored=False, release_error=str(error))
                    record(subject, {'event': 'release-error', 'error': str(error)})
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
    finally:
        subject.dead = True
        if subject.file_lock:
            lab_lock.release(subject.file_lock)
            subject.file_lock = None
    return outcome


def run_directory(lab: pathlib.Path) -> pathlib.Path:
    stamp = time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
    return lab / 'runs' / stamp
