"""Filename-only wearable IO inside a physical disposable lab."""
from __future__ import annotations

import os
from contextlib import contextmanager
import stat
import unicodedata
from pathlib import Path


def _filename(filename: str, suffixes: tuple[str, ...]) -> None:
    if (not isinstance(filename,str) or not filename or
        any(c in '\\/:<>"|?*' or unicodedata.category(c)=='Cc' for c in filename) or
        filename.rstrip(' .')!=filename):
        raise ValueError('Use a plain wearable filename without paths or control characters')
    reserved={'CON','PRN','AUX','NUL','CONIN$','CONOUT$',
              *(f'{prefix}{number}' for prefix in ('COM','LPT') for number in '123456789¹²³')}
    if filename.split('.')[0].rstrip(' .').upper() in reserved:
        raise ValueError('Reserved Windows filename')
    if Path(filename).suffix.lower() not in {s.lower() for s in suffixes}:
        raise ValueError('Unsupported wearable extension')


def _physical(path: Path) -> None:
    for part in reversed((path,*path.parents)):
        try:info=part.lstat()
        except FileNotFoundError:continue
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError('Wearable paths must not contain links, junctions or reparse points')


@contextmanager
def physical_directory(path: Path):
    """Keep a verified Windows directory in place through child IO."""
    _physical(path)
    if os.name != 'nt':
        yield
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    open_dir = kernel.CreateFileW
    open_dir.argtypes = [wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,
                         wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    open_dir.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes, close.restype = [wintypes.HANDLE], wintypes.BOOL
    # FILE_LIST_DIRECTORY participates in sharing checks (an attributes-only
    # handle does not). Allow child IO while denying directory deletion/rename.
    # Open the reparse point itself with backup semantics. Recheck after admission.
    handle = open_dir(str(path), 1, 3, None, 3, 0x02200000, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        _physical(path)
        if not path.is_dir():
            raise ValueError('Expected a physical directory')
        yield
    finally:
        close(handle)


def _target(lab: Path, filename: str, suffixes: tuple[str,...], create: bool) -> Path:
    _filename(filename,suffixes)
    root=Path(os.path.abspath(lab))
    _physical(root)
    if not root.is_dir():raise ValueError('Lab directory does not exist')
    folder=root/'saves'
    _physical(folder)
    if create:folder.mkdir(exist_ok=True)
    if not folder.is_dir():raise ValueError('Lab saves directory does not exist')
    target=folder/filename
    _physical(target)
    return target


def wear_input(lab: Path, filename: str, suffixes: tuple[str,...]) -> Path:
    target=_target(lab,filename,suffixes,False)
    if not target.is_file():raise FileNotFoundError('Wearable input does not exist or is not a regular file')
    return target


def wear_destination(lab: Path, filename: str, suffix: str='.xroid') -> Path:
    target=_target(lab,filename,(suffix,),True)
    if os.path.lexists(target):raise FileExistsError('Refusing to overwrite an existing wearable')
    return target
