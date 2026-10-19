"""Path and capture-request policy for one lab directory.

These rules decide where an artifact may be written and which views may be
captured. They are pure functions so they can be tested without starting VRoid;
the runtime imports them back through `vroid_mcp.runtime` for compatibility.
"""

from __future__ import annotations

import pathlib
import re

from .capture_views import CAPTURE_VIEWS

CAPTURE_ID = re.compile(r'[0-9a-f]{32}')
RESERVED_NAMES = frozenset(
    ['CON', 'PRN', 'AUX', 'NUL'] + [f'COM{i}' for i in range(1, 10)] + [f'LPT{i}' for i in range(1, 10)])
FORBIDDEN_IN_NAME = set('\\/:<>"|?*')
MODEL_SUFFIX = '.vroid'
MAX_VIEWS = 6
MIN_SIZE = 256
MAX_SIZE = 2048


def validate_capture(views: Sequence[str], size: int) -> None:
    """Accept one to six distinct known views at an integer size in range."""
    if not views:
        raise ValueError('Choose at least one view')
    if len(views) > MAX_VIEWS:
        raise ValueError(f'Capture at most {MAX_VIEWS} views per batch')
    if len(set(views)) != len(views):
        raise ValueError('Each view may appear only once per batch')
    unknown = [view for view in views if view not in CAPTURE_VIEWS]
    if unknown:
        raise ValueError('Unsupported view(s): ' + ', '.join(unknown))
    if type(size) is not int or not MIN_SIZE <= size <= MAX_SIZE:
        raise ValueError(f'Capture size must be an integer from {MIN_SIZE} to {MAX_SIZE}')


def _physical(path: pathlib.Path) -> pathlib.Path:
    """Resolve without following a link: a redirected artifact folder is refused."""
    resolved = path.resolve()
    if resolved != path:
        raise ValueError('Artifact folders must not be links or junctions')
    return resolved


def review_folder(lab: pathlib.Path, capture: str) -> pathlib.Path:
    """Resolve `reviews/<capture_id>` for an id returned by capture_review."""
    if not CAPTURE_ID.fullmatch(capture):
        raise ValueError('Use the capture_id returned by capture_review')
    folder = lab.resolve() / 'reviews' / capture
    return _physical(folder)


def _plain_model_name(filename: str) -> None:
    if not filename:
        raise ValueError('A .vroid filename is required')
    if any(ord(character) < 32 for character in filename) or set(filename) & FORBIDDEN_IN_NAME:
        raise ValueError('Use a plain filename without path separators or control characters')
    if filename != filename.rstrip(' .'):
        raise ValueError('A filename may not end with a space or a dot')
    suffix_ok = filename.lower().endswith(MODEL_SUFFIX) and filename not in (MODEL_SUFFIX, '.' + MODEL_SUFFIX)
    if not suffix_ok:
        raise ValueError('The filename must end in .vroid and name something')
    stem = filename.split('.', 1)[0].upper()
    if stem in RESERVED_NAMES:
        raise ValueError('Windows reserves that filename')


def save_destination(lab: pathlib.Path, name: str) -> pathlib.Path:
    """Resolve `saves/<filename>` for a new model file, refusing to overwrite."""
    _plain_model_name(name)
    saves = lab.resolve() / 'saves'
    saves.mkdir(exist_ok=True)
    destination = _physical(saves) / name
    already_taken = destination.exists() or destination.is_symlink()
    if already_taken:
        raise FileExistsError(f'Refusing to overwrite an existing file: {name}')
    return destination
