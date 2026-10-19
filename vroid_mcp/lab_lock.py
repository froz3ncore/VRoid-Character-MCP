"""Single-owner guard for one VRoid lab directory.

Two MCP servers driving the same lab copy corrupt each other: both write the
profile, the saves and the frida bridge of one installation.  The lock is a
one-byte Windows file lock held for the lifetime of the process, plus the
owning PID written just after the locked byte so a stale owner is identifiable
from the message.  The OS releases the lock when the process dies, so a
crashed run never leaves a lock that has to be cleared by hand.

Byte 0 is the lock sentinel and is never rewritten by a second attempt: a
write to that byte is denied while another process owns it, which is why the
lock is taken before anything is written and the PID starts at byte 1.
"""

from __future__ import annotations

import os
import pathlib

LOCK_NAME = '.mcp-owner.lock'
_PID_OFFSET = 1


def lock_path(lab: pathlib.Path | str) -> pathlib.Path:
    return pathlib.Path(lab) / LOCK_NAME


def _read_owner(handle) -> str:
    try:
        handle.seek(_PID_OFFSET)
        text = handle.read(64).decode('ascii', 'replace')
    except OSError:
        return 'unknown'
    digits = ''.join(ch for ch in text if ch.isdigit())
    return digits or 'unknown'


def acquire(lab: pathlib.Path | str):
    """Take the lab lock, or raise RuntimeError naming the current owner."""
    import msvcrt

    path = lock_path(lab)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open('r+b') if path.exists() else path.open('w+b')
    if path.stat().st_size < 1:
        handle.write(b'\0')
        handle.flush()
    handle.seek(0)
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        owner = _read_owner(handle)
        handle.close()
        raise RuntimeError(f'Another MCP process already owns this lab (pid {owner}): {path}') from None
    handle.seek(0)
    handle.truncate(0)
    handle.write(b'\0' + f'{os.getpid()}\n'.encode('ascii'))
    handle.flush()
    handle.seek(0)
    return handle


def release(handle) -> None:
    if handle is None:
        return
    import msvcrt

    try:
        # Clear the PID record while the lock is still held, so a released lab
        # never looks owned by a process that already exited cleanly.
        handle.seek(1)
        handle.write(b'0')
        handle.truncate(2)
        handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    finally:
        handle.close()


def owner(lab: pathlib.Path | str) -> str | None:
    """Report the recorded owner without taking the lock.

    A lock file left by an older reader that only wrote a zero sentinel is not
    an owner: the byte-range lock itself is what excludes a second server, so
    an all-zero record means nobody recorded a PID.
    """
    path = lock_path(lab)
    if not path.is_file():
        return None
    try:
        with path.open('rb') as handle:
            handle.seek(_PID_OFFSET)
            text = handle.read(64).decode('ascii', 'replace')
    except OSError:
        return 'unknown'
    digits = ''.join(ch for ch in text if ch.isdigit())
    if not digits or set(digits) == {'0'}:
        return None
    return digits


def probe(lab: pathlib.Path | str) -> str | None:
    """Return the live owner, or None when this process could take the lock."""
    try:
        handle = acquire(lab)
    except RuntimeError:
        return owner(lab) or 'unknown'
    release(handle)
    return None
