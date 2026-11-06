"""Bounded ZIP preflight and byte-exact registered custom-item resolution.

ZIP checks establish integrity only. Native deserialization and the migration
predicate establish compatibility before a registered option may be applied.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import zipfile


def inspect_custom_item(path):
    path = Path(path).resolve(strict=True)
    if not path.is_file() or path.suffix.lower() != '.vroidcustomitem':
        raise ValueError('CUSTOM_ITEM_FILE_REQUIRED')
    if not 0 < path.stat().st_size <= 512 * 1024 * 1024:
        raise ValueError('CUSTOM_ITEM_SIZE_LIMIT')
    try:
        with zipfile.ZipFile(path) as archive:
            entries, seen, total = archive.infolist(), set(), 0
            if not 1 <= len(entries) <= 4096:
                raise ValueError('CUSTOM_ITEM_ENTRY_LIMIT')
            for entry in entries:
                name = entry.filename
                parts = PurePosixPath(name).parts
                mode = (entry.external_attr >> 16) & 0xffff
                if (not name or '\\' in name or ':' in name or name.startswith('/')
                        or '..' in parts or '.' in name.split('/') or name.casefold() in seen
                        or entry.flag_bits & 1 or stat.S_ISLNK(mode)):
                    raise ValueError('CUSTOM_ITEM_UNSAFE_ARCHIVE')
                seen.add(name.casefold())
                total += entry.file_size
                if (entry.file_size > 256 * 1024 * 1024 or total > 1024 * 1024 * 1024
                        or entry.file_size > max(1, entry.compress_size) * 1000):
                    raise ValueError('CUSTOM_ITEM_EXPANSION_LIMIT')
            meta_entry = archive.getinfo('v1customitem/meta.json')
            if meta_entry.file_size > 1024 * 1024 or archive.testzip() is not None:
                raise ValueError('CUSTOM_ITEM_ARCHIVE_CORRUPT')
            metadata = json.loads(archive.read(meta_entry).decode('utf-8'))
            if not isinstance(metadata, dict) or any(not isinstance(metadata.get(key), str)
                    or not metadata[key] for key in ('rootTransferableGroupId', 'rootTransferableGroupTypeId')):
                raise ValueError('CUSTOM_ITEM_METADATA_INVALID')
    except (zipfile.BadZipFile, KeyError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError('CUSTOM_ITEM_ARCHIVE_INVALID') from error
    return {'path': str(path), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'metadata': metadata}


def resolve_registered(info, rows):
    matches = []
    for row in rows:
        if (row.get('id') != info['metadata']['rootTransferableGroupId'] or
                row.get('group_type') != info['metadata']['rootTransferableGroupTypeId']):
            continue
        try:
            registered = inspect_custom_item(row['path'])
        except (ValueError, OSError):
            continue
        if registered['sha256'] == info['sha256'] and registered['metadata'] == info['metadata']:
            matches.append(row)
    exact = [row for row in matches if Path(row['path']).resolve() == Path(info['path'])]
    matches = exact or matches
    if len(matches) != 1:
        raise ValueError('CUSTOM_ITEM_UNREGISTERED_OR_AMBIGUOUS')
    row = matches[0]
    if (row.get('registered') is not True or not all(isinstance(row.get(key), str) and row[key]
            for key in ('resource_name', 'revision', 'custom_resource_name', 'custom_revision'))):
        raise ValueError('CUSTOM_ITEM_REGISTRY_IDENTITY_UNAVAILABLE')
    return row


@contextmanager
def pinned_file(path):
    """Allow native readers while prohibiting Windows writes/rename until selection settles."""
    if os.name != 'nt':
        with open(path, 'rb'):
            yield
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes, close.restype = [wintypes.HANDLE], wintypes.BOOL
    handle = create(str(path), 0x80000000, 1, None, 3, 0x80, None)
    if handle == wintypes.HANDLE(-1).value:
        raise OSError(ctypes.get_last_error(), 'Cannot pin registered custom-item bytes')
    try:
        yield
    finally:
        close(handle)


@contextmanager
def pinned_application(runtime, path):
    """Keep the validated source immutable while an unknown native load may run."""
    pin = pinned_file(path)
    pin.__enter__()
    try:
        yield
    finally:
        if runtime.uncertain:
            if not hasattr(runtime, '_pending_custom_item_pins'):
                runtime._pending_custom_item_pins = []
            runtime._pending_custom_item_pins.append(pin)
        else:
            pin.__exit__(None, None, None)
