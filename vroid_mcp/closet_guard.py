"""Refuse to launch VRoid Studio while the crash-triggering registry key exists.

`HKCU\\SOFTWARE\\Classes\\vroid.closet` makes xroid (`.xroid`) loading crash
deterministically in the validated build, and the crash reporter recreates the
key after each crash.  Previously the key was checked by hand before a native
run; a forgotten check means a process that dies mid-way and an uncertain save.

The guard reads the key before launch:

* absent  -> nothing happens;
* present -> the run stops with ``VROID_CLOSET_CRASH_KEY`` and an explicit
  recovery command instead of launching a doomed process;
* present and ``VROID_MCP_CLEAR_CLOSET_KEY=1`` (or ``--clear``) -> the key is
  exported to a timestamped ``.reg`` file inside the lab, removed, and the
  removal is re-read before the launch continues.

Nothing here touches other registry locations or policy settings.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import time

KEY = r'SOFTWARE\Classes\vroid.closet'
ENV_CLEAR = 'VROID_MCP_CLEAR_CLOSET_KEY'


def _read_probe() -> bool:
    import winreg

    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY))
    except FileNotFoundError:
        return False
    except OSError:
        # An unreadable key still exists; treat it as present rather than risk a launch.
        return True
    return True


def present() -> bool:
    if os.name != 'nt':
        return False
    return _read_probe()


def _export(destination: pathlib.Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(['reg', 'export', 'HKCU\\' + KEY, str(destination), '/y'],
                            capture_output=True, text=True)
    if result.returncode != 0 or not destination.is_file():
        raise RuntimeError('Could not back up the vroid.closet registry key: '
                           + (result.stderr or result.stdout).strip())


def _delete() -> None:
    """Remove the key in-process, then with reg.exe; both can be denied."""
    import winreg

    errors = []
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, KEY)
        return
    except FileNotFoundError:
        return
    except OSError as error:
        errors.append(f'winreg: {error}')
    result = subprocess.run(['reg', 'delete', 'HKCU\\' + KEY, '/f'], capture_output=True, text=True)
    if result.returncode == 0:
        return
    errors.append('reg: ' + (result.stderr or result.stdout).strip())
    raise PermissionError('; '.join(errors))


def manual_command() -> str:
    return 'reg delete "HKCU\\' + KEY + '" /f'


def clear(lab: pathlib.Path | str) -> dict:
    """Back up the key, then remove it if this process is allowed to."""
    lab = pathlib.Path(lab)
    stamp = time.strftime('%Y%m%d-%H%M%S')
    backup = lab / 'crash-guard' / f'vroid-closet-{stamp}.reg'
    _export(backup)
    try:
        _delete()
    except PermissionError as error:
        raise PermissionError(
            'VROID_CLOSET_CRASH_KEY: the key was backed up to ' + str(backup) +
            ' but this process may not remove it (' + str(error) + '). '
            'Run this in a normal shell, then start the server again: ' + manual_command()) from None
    if present():
        raise RuntimeError('The vroid.closet registry key is still present after removal: ' + KEY)
    return {'closet_key': 'removed', 'backup': str(backup), 'key': KEY}



def enforce(lab: pathlib.Path | str, clear_when_present: bool | None = None) -> dict:
    """Raise on the crash key unless clearing it was explicitly requested."""
    if not present():
        return {'closet_key': 'absent', 'key': KEY}
    if clear_when_present is None:
        clear_when_present = os.environ.get(ENV_CLEAR, '') == '1'
    if clear_when_present:
        return clear(lab)
    raise RuntimeError(
        'VROID_CLOSET_CRASH_KEY: HKCU\\' + KEY + ' exists and makes .xroid loading crash '
        'deterministically. Back it up and remove it before launching; if this process may not '
        'write the registry, run `' + manual_command() + '` in a normal shell. '
        'The backup from the previous session is under the lab\'s crash-guard/ directory. '
        'Nothing was launched.')


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description='Check or clear the vroid.closet crash key')
    parser.add_argument('--lab', required=True, help='lab directory that receives the .reg backup')
    parser.add_argument('--clear', action='store_true', help='back up and remove the key when present')
    args = parser.parse_args(argv)
    state = {'closet_key': 'present' if present() else 'absent', 'key': KEY}
    if state['closet_key'] == 'present' and args.clear:
        state = clear(args.lab)
    print(json.dumps(state, ensure_ascii=False))
    return 0 if state['closet_key'] != 'present' else 1


if __name__ == '__main__':
    raise SystemExit(main())

