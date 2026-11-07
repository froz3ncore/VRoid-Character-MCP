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


def inspect_custom_item(path, *, include_icon=False):
    path = Path(path).resolve(strict=True)
    if not path.is_file() or path.suffix.lower() != '.vroidcustomitem':
        raise ValueError('CUSTOM_ITEM_FILE_REQUIRED')
    # One protected descriptor owns metadata, streamed digest and optional icon.
    # Windows denies write/rename; other hosts additionally verify descriptor and
    # path identity before accepting a generation that could have changed.
    with pinned_file(path), path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        if not 0 < before.st_size <= 512 * 1024 * 1024:
            raise ValueError('CUSTOM_ITEM_SIZE_LIMIT')
        digest, count = hashlib.sha256(), 0
        for chunk in iter(lambda:stream.read(1024*1024), b''):
            count += len(chunk)
            if count > before.st_size: raise ValueError('CUSTOM_ITEM_BYTES_CHANGED')
            digest.update(chunk)
        stream.seek(0)
        metadata, icon = _inspect_archive(stream, include_icon)
        after,current = os.fstat(stream.fileno()),path.stat()
        identity = lambda info:(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)
        # Windows 3.13 stat/fstat disagree on deprecated st_ctime (creation vs
        # last-write); compare ctime within fstat, not across the two APIs.
        if (count != before.st_size or identity(before) != identity(after)
                or before.st_ctime_ns != after.st_ctime_ns or identity(before) != identity(current)
                or os.name!='nt' and before.st_ctime_ns != current.st_ctime_ns):
            raise ValueError('CUSTOM_ITEM_BYTES_CHANGED')
        result = {'path':str(path),'bytes':count,'sha256':digest.hexdigest(),'metadata':metadata}
        if include_icon: result['icon'] = icon
        return result


def _inspect_archive(stream, include_icon):
    try:
        with zipfile.ZipFile(stream) as archive:
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
            icon = None
            if include_icon:
                candidates=[e for e in entries if e.filename.startswith('thumbnails/') and e.filename.endswith('.png')]
                if len(candidates)!=1 or not 0<candidates[0].file_size<=2*1024*1024:
                    raise ValueError('CUSTOM_ITEM_ICON_AMBIGUOUS_OR_UNAVAILABLE')
                icon=archive.read(candidates[0])
    except (zipfile.BadZipFile, KeyError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError('CUSTOM_ITEM_ARCHIVE_INVALID') from error
    return metadata, icon


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
