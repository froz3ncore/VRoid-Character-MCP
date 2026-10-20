"""Bounded, non-launching installation checks using only the standard library.

The only optional output is the report explicitly requested by the caller.
An available lab is a point-in-time observation, not a reservation. In
particular, recorded PIDs never substitute for checking the OS file lock.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

from . import __version__, closet_guard, lab_lock
from .supported_builds import SUPPORTED_ASSEMBLIES

REQUIRED_PACKAGES = {'frida': '17.16.0', 'mcp': '1.30.0'}
ROOT = Path(__file__).resolve().parents[1]


def inspect_lock(lab: Path) -> dict:
    """Check an existing sentinel without creating it or rewriting its owner."""
    path = lab_lock.lock_path(lab)
    if not path.exists():
        return {'state': 'unreserved', 'recorded_pid': None}
    if path.resolve() != path.absolute():
        raise ValueError('The lab lock is a link; inspect the lab paths first')
    if os.name != 'nt':
        return {'state': 'unknown', 'recorded_pid': lab_lock.owner(lab)}
    import msvcrt

    with path.open('r+b') as handle:
        recorded = lab_lock._read_owner(handle)
        if recorded == 'unknown' or set(recorded) == {'0'}:
            recorded = None
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise
            return {'state': 'busy', 'recorded_pid': recorded}
        else:
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    return {'state': 'available', 'recorded_pid': recorded}


def inspect_registry() -> dict:
    """Keep absent, present and unreadable separate; never honor auto-clear env."""
    if os.name != 'nt':
        return {'state': 'unavailable', 'key': 'HKCU\\' + closet_guard.KEY}
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, closet_guard.KEY):
            pass
    except FileNotFoundError:
        state = 'absent'
    except OSError as error:
        return {'state': 'unreadable', 'key': 'HKCU\\' + closet_guard.KEY,
                'error': str(error)}
    else:
        state = 'present'
    return {'state': state, 'key': 'HKCU\\' + closet_guard.KEY}


def probe_asyncio(timeout: float = 5) -> dict:
    """Isolate loop construction: restricted loopback can hang socketpair()."""
    code = 'import asyncio; asyncio.run(asyncio.sleep(0)); print("ASYNCIO_OK")'
    try:
        result = subprocess.run([sys.executable, '-I', '-c', code],
                                capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {'state': 'timeout', 'timeout_seconds': timeout}
    except OSError as error:
        return {'state': 'unavailable', 'error': str(error)}
    return {'state': 'ok' if result.returncode == 0 and 'ASYNCIO_OK' in result.stdout
            else 'failed', 'returncode': result.returncode,
            'error': result.stderr.strip()[-1200:]}


def probe_imports(timeout: float = 10) -> dict:
    try:
        result = subprocess.run([sys.executable, '-c', 'import frida; import mcp'],
                                capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {'state': 'timeout', 'timeout_seconds': timeout}
    except OSError as error:
        return {'state': 'unavailable', 'error': str(error)}
    return {'state': 'ok' if result.returncode == 0 else 'failed',
            'returncode': result.returncode, 'error': result.stderr.strip()[-1200:]}


def build_report(*, lab: Path | None = None, source: Path | None = None,
                 repo: Path = ROOT) -> dict:
    if (lab is None) == (source is None):
        raise ValueError('Choose exactly one prepared lab or source installation')
    rows = []

    def add(code, status, message, recovery='', **detail):
        rows.append({'code': code, 'status': status, 'message': message,
                     'recovery': recovery, 'detail': detail})

    def check(code, operation, recovery):
        try:
            operation()
        except (OSError, ValueError, KeyError, TypeError) as error:
            add(code, 'blocked', str(error), recovery)

    add('platform', 'pass' if os.name == 'nt' and struct.calcsize('P') == 8 else 'blocked',
        'Windows x64 is required', 'Use a 64-bit Python interpreter on Windows.',
        platform=sys.platform, pointer_bits=struct.calcsize('P') * 8)
    add('python', 'pass' if sys.version_info >= (3, 10) else 'blocked',
        'Python 3.10 or newer is required', 'Create .venv with Python 3.10 or newer.',
        executable=sys.executable, version=sys.version.split()[0])
    for name, required in REQUIRED_PACKAGES.items():
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            actual = None
        add('dependency.' + name, 'pass' if actual == required else 'blocked',
            'Pinned Python dependency',
            'Install requirements.txt using the same interpreter that runs launch.py.',
            required=required, installed=actual)
    imported = probe_imports()
    add('dependency.imports', 'pass' if imported['state'] == 'ok' else 'blocked',
        'Import Python runtime dependencies without attaching to VRoid',
        'Check the reported import error and reinstall requirements in this interpreter.',
        **imported)

    def bridge():
        package = repo / 'node_modules/frida-il2cpp-bridge'
        wanted = json.loads((repo / 'package.json').read_text(encoding='utf8'))[
            'dependencies']['frida-il2cpp-bridge']
        actual = json.loads((package / 'package.json').read_text(encoding='utf8'))['version']
        if wanted != actual or not (package / 'dist/index.js').is_file():
            raise ValueError('Missing or mismatched frida-il2cpp-bridge runtime')
        add('dependency.bridge', 'pass', 'JavaScript bridge is installed', installed=actual)
    check('dependency.bridge', bridge, 'Run npm ci in the repository root.')

    loop = probe_asyncio()
    add('environment.asyncio', 'pass' if loop['state'] == 'ok' else 'blocked',
        'Construct and close an isolated Python asynchronous event loop',
        'Run this command in a normal terminal with local loopback permitted. '
        'A timeout alone does not establish a defect in the project.', **loop)

    selected = Path(lab if lab is not None else source).absolute()
    physical = selected.resolve() == selected
    add('paths.physical', 'pass' if physical else 'blocked',
        'The application must be a physical directory',
        'Choose a physical installation or prepare a new physical lab.', path=str(selected))
    app = selected / 'app' if lab is not None else selected

    def installation():
        if not physical or app.resolve() != app:
            raise ValueError('Application path includes a link or junction')
        for name in ('VRoidStudio.exe', 'GameAssembly.dll', 'UnityPlayer.dll',
                     'VRoidStudio_Data/il2cpp_data/Metadata/global-metadata.dat'):
            path = app / name
            if path.resolve() != path or not path.is_file():
                raise ValueError('Missing or linked installation file: ' + name)
        digest = hashlib.sha256()
        with (app / 'GameAssembly.dll').open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        value = digest.hexdigest()
        label = SUPPORTED_ASSEMBLIES.get(value)
        add('application.build', 'pass' if label else 'blocked',
            label or 'Unknown application build; native calls remain blocked',
            'Use a supported VRoid 2.14.0 installation and prepare a new lab; '
            'do not bypass the hash allowlist.', sha256=value,
            supported=[{'sha256': h, 'label': text} for h, text in SUPPORTED_ASSEMBLIES.items()])
    check('application.build', installation,
          'Point --source to a complete installation, or create a new lab with prepare_lab.py. '
          'Historical evidence labs may have had app/ removed; keep their records intact.')

    registry = inspect_registry()
    add('registry.closet', 'pass' if registry['state'] == 'absent' else 'blocked',
        'Inspect the known crash-triggering registry key',
        'If present, review RECOVERY.md before explicitly backing up and clearing this key. '
        'If unreadable, resolve registry read access first.', **registry)
    if lab is not None and physical:
        def ownership():
            if not selected.is_dir():
                raise ValueError('The lab directory does not exist')
            state = inspect_lock(selected)
            add('lab.ownership', 'pass' if state['state'] in ('available', 'unreserved')
                else 'blocked', 'Inspect the live lab lock without changing the owner record',
                'Use a different lab or close its owning client normally; never delete its lock. '
                'An old PID is informational when no OS lock is held.', **state)
        check('lab.ownership', ownership, 'Check lab access and its physical lock path.')

    failed = [row['code'] for row in rows if row['status'] == 'blocked']
    return {'schema': 'vroid-doctor-v1', 'project_version': __version__,
            'target_kind': 'lab' if lab is not None else 'source', 'target': str(selected),
            'checks': rows, 'ok': not failed, 'blocked_checks': failed,
            'exit_code': 1 if failed else 0,
            'scope': 'Preflight only: no app launch, native capability calls, registry writes, '
                     'profile edits or lock-file rewrites. Lab availability is not reserved; '
                     'successful preflight does not certify injection, saving, visuals or E2E.'}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--lab', type=Path, help='existing prepared lab')
    target.add_argument('--source', type=Path, help='VRoid Studio installation to inspect')
    parser.add_argument('--json', type=Path, help='new report file; existing files are refused')
    parser.add_argument('--format', choices=('text', 'json'), default='text')
    args = parser.parse_args(argv)
    if args.json and args.json.exists():
        parser.error('The report already exists; choose a new --json path')
    try:
        report = build_report(lab=args.lab, source=args.source)
        encoded = json.dumps(report, ensure_ascii=False, indent=2)
        if args.json:
            # Only caller-requested output is written, with exclusive creation.
            with args.json.open('x', encoding='utf8') as output:
                output.write(encoded + '\n')
    except (OSError, ValueError) as error:
        print('DOCTOR_ERROR: ' + str(error), file=sys.stderr)
        return 2
    if args.format == 'json':
        print(encoded)
    else:
        for row in report['checks']:
            print(f"[{row['status']}] {row['code']}: {row['message']}")
            if row['status'] != 'pass':
                print('  ' + row['recovery'])
                print('  ' + json.dumps(row['detail'], ensure_ascii=False))
        print('PREFLIGHT PASSED' if report['ok'] else 'PREFLIGHT BLOCKED')
        print(report['scope'])
    return report['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
