"""Validation for native preset thumbnails returned through MCP."""
from __future__ import annotations

import base64
import hashlib

AREAS = ('face', 'body', 'hair', 'clothing')


def validate_request(expected_model: str, area: str, preset_ids: list[str]) -> None:
    if not isinstance(expected_model, str) or not expected_model:
        raise ValueError('A fresh model_token is required')
    if area not in AREAS:
        raise ValueError('Unsupported preset area')
    if not isinstance(preset_ids, list) or not 1 <= len(preset_ids) <= 6:
        raise ValueError('Choose 1-6 distinct preset IDs from list_presets')
    if any(not isinstance(p, str) or not p.startswith(area + '/') or len(p) > 1024 for p in preset_ids):
        raise ValueError('Preset IDs must belong to the requested area')
    if len(set(preset_ids)) != len(preset_ids):
        raise ValueError('Choose distinct preset IDs')


def decode_thumbnail(result: dict, expected_model: str, preset_id: str) -> tuple[dict, bytes]:
    if result.get('model_token') != expected_model or result.get('preset_id') != preset_id:
        raise ValueError('Native thumbnail identity mismatch')
    data = base64.b64decode(result['base64'], validate=True)
    if not 33 <= len(data) <= 2 * 1024 * 1024 or not data.startswith(b'\x89PNG\r\n\x1a\n') or data[12:16] != b'IHDR':
        raise ValueError('Invalid native thumbnail PNG')
    width, height = int.from_bytes(data[16:20], 'big'), int.from_bytes(data[20:24], 'big')
    if not 1 <= width <= 512 or not 1 <= height <= 512 or (width, height) != (result.get('width'), result.get('height')):
        raise ValueError('Unexpected native thumbnail dimensions')
    metadata = {k: v for k, v in result.items() if k != 'base64'}
    metadata.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    return metadata, data
