"""Display-only preset names; identity always remains the native preset ID.

Curated English labels from brainrom/vroid-studio-mcp (MIT). See the bundled
data/preset_labels/LICENSE and NOTICE for attribution and the pinned source.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).with_name('data') / 'preset_labels'


@lru_cache(maxsize=1)
def labels() -> dict[str, str]:
    merged: dict[str, str] = {}
    for file in sorted(DATA.glob('10-*.json')):
        payload = json.loads(file.read_text(encoding='utf-8'))
        body = payload.get('labels', payload)
        for resource, name in body.items():
            if isinstance(name, str) and name.strip():
                merged[resource] = name
    return merged


def name_preset(preset: dict) -> dict:
    """Add a descriptive name without changing existing label/ID fields."""
    native = preset.get('label') or preset.get('id') or ''
    name = labels().get(preset.get('resource_name'))
    return {**preset, 'name': name or native,
            'name_source': 'brainrom_labels' if name else 'native_label',
            'name_language': 'en' if name else None}


def name_catalog(catalog: dict) -> dict:
    return {**catalog, 'presets': [name_preset(p) for p in catalog['presets']]}
