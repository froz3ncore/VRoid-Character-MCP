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


def script_text(config: dict, bridge_js: pathlib.Path) -> str:
    """Concatenate the agent into one script with the probe config in front."""
    parts = ['const PROBE=' + json.dumps(config) + ';',
             (PROJECT / 'agent' / GUARD_MODULE).read_text(encoding='utf-8'),
             bridge_js.read_text(encoding='utf-8')]
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


async def call(subject, operation: str, args: dict | None = None) -> Any:
    if subject.dead or subject.script is None:
        raise RuntimeError('COPY_DISCONNECTED: restart the MCP server')
    if subject.uncertain and operation != 'status':
        raise RuntimeError('PREVIOUS_CALL_UNCERTAIN: restart; do not retry a mutation')
    timeout = SLOW_OPERATIONS.get(operation, DEFAULT_TIMEOUT_SECONDS)
    payload = args or {}
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
        idle = (result['model_ready'] and not result['updating']
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
            return dict(DISCONNECTED)
        try:
            result = await call(subject, 'status')
        except frida.InvalidOperationError as error:
            if 'script has been destroyed' not in str(error):
                raise
            subject.dead = True
            return dict(DISCONNECTED)
        result.update(connected=True, writes_blocked=subject.uncertain, lab=str(subject.lab),
                      crash_guard=subject.crash_guard,
                      texture_editor_guard=edit_sequence.status(subject, result.get('model_token')))
        return result


def close(subject) -> None:
    # Kill only the process this subject spawned: never a name-based kill.
    try:
        if subject.pid is not None and subject.device is not None and not subject.dead:
            try:
                subject.device.kill(subject.pid)
            except frida.ProcessNotFoundError:
                pass
    finally:
        subject.dead = True
        if subject.file_lock:
            lab_lock.release(subject.file_lock)
            subject.file_lock = None


def run_directory(lab: pathlib.Path) -> pathlib.Path:
    stamp = time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
    return lab / 'runs' / stamp
