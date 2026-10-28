"""Explicit absolute file paths for attached sessions; copy IO remains in its lab."""
from pathlib import Path
import os
from .wear_paths import _filename, _physical, wear_input, wear_destination


def file_input(lab, value, suffixes, attached=False):
    path = Path(value)
    if not path.is_absolute():
        return wear_input(lab, value, suffixes)
    if not attached:
        raise ValueError('Absolute paths require an attached window')
    _filename(path.name, suffixes)
    _physical(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def file_destination(lab, value, suffix, attached=False):
    path = Path(value)
    if not path.is_absolute():
        return wear_destination(lab, value, suffix)
    if not attached:
        raise ValueError('Absolute paths require an attached window')
    _filename(path.name, (suffix,))
    _physical(path)
    if not path.parent.is_dir():
        raise ValueError('Choose an existing destination directory')
    if os.path.lexists(path):
        raise FileExistsError('Refusing to overwrite an existing file')
    return path
