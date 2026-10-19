"""Exact native message-key corrections, separate from native labels and IDs."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA=Path(__file__).with_name('data')/'parameter_labels'


@lru_cache(maxsize=1)
def corrections() -> dict[str,str]:
    return json.loads((DATA/'en.json').read_text(encoding='utf-8'))


def name_parameter(parameter: dict) -> dict:
    key=parameter.get('translation_key')
    corrected=corrections().get(key) if isinstance(key,str) else None
    # Never match on visible text, suffixes, ordinal IDs or a partial combined key.
    return {**parameter,'name':corrected or parameter.get('label') or parameter.get('id',''),
            'name_source':'brainrom_correction' if corrected else 'native_label',
            'name_language':'en' if corrected else None,'name_key':key if corrected else None}


def name_parameters(result: dict) -> dict:
    return {**result,'parameters':[name_parameter(p) for p in result['parameters']]}
