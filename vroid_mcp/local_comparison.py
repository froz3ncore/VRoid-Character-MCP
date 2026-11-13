"""Compare presets on copies of one saved character through the local client."""

from __future__ import annotations

import base64
import hashlib
from html import escape
import json
from pathlib import Path
from uuid import uuid4

from mcp.types import TextContent
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .capture_views import REGIONAL_VIEWS


class Comparison(BaseModel):
    model_config = ConfigDict(extra='forbid')
    preset_ids: list[str] = Field(min_length=2, max_length=6)
    views: list[str] = Field(default_factory=list, max_length=3)
    size: int = Field(default=512, ge=256, le=1024)

    @property
    def slot(self) -> tuple[str, str]:
        area, category, _ = self.preset_ids[0].split('/')
        return area, category

    @model_validator(mode='after')
    def validate_selection(self):
        parts = [value.split('/') for value in self.preset_ids]
        if any(len(part) != 3 or not all(part) for part in parts):
            raise ValueError('Use preset IDs from list_presets')
        area, category = self.slot
        if area not in ('face', 'body', 'hair', 'clothing') or any(
            part[:2] != [area, category] for part in parts
        ):
            raise ValueError('All presets must belong to the same area and category')
        if len(set(self.preset_ids)) != len(self.preset_ids):
            raise ValueError('Choose distinct preset IDs')
        if len(set(self.views)) != len(self.views) or any(v not in REGIONAL_VIEWS for v in self.views):
            raise ValueError('Choose distinct regional views, such as face_front or body_front')
        return self


async def _call(client, name, **arguments) -> dict:
    result = await client.call_tool(name, arguments)
    if not result.content or not isinstance(result.content[0], TextContent):
        raise RuntimeError(f'{name}: expected a text response')
    first = result.content[0].text
    if result.isError:
        raise RuntimeError(f'{name}: {first[:500]}')
    return json.loads(first)


def _make_report(source: Path, views: list[str], rows: list[tuple], destination: Path) -> None:
    title = f'Preset comparison for {source.name}'
    header = ''.join(f'<th scope="col">{escape(view)}</th>' for view in views)
    with destination.open('x', encoding='utf-8') as report:
        report.write(f'<!doctype html><html lang="en"><meta charset="utf-8">'
                     f'<title>{escape(title)}</title><h1>{escape(title)}</h1>\n'
                     f'<table><thead><tr><th scope="col">Variant</th>{header}</tr></thead><tbody>\n')
        for label, preset_id, capture in rows:
            report.write(f'<tr><th scope="row">{escape(label)}')
            if preset_id:
                report.write(f'<br><code>{escape(preset_id)}</code>')
            report.write('</th>')
            for view in views:
                data = Path(capture['images'][view]['path']).read_bytes()
                png = base64.b64encode(data).decode('ascii')
                report.write(f'<td><img width="256" height="256" alt="{escape(label + " / " + view)}" '
                             f'src="data:image/png;base64,{png}"></td>')
            report.write('</tr>\n')
        report.write('</tbody></table></html>\n')


async def compare_presets(client, spec: Comparison, source: Path, lab: Path) -> dict:
    area, category = spec.slot
    region = 'face' if area in ('face', 'hair') else 'body'
    views = spec.views or [f'{region}_front', f'{region}_three_quarter_left']
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    status = await _call(client, 'get_status')
    if status.get('mode') != 'copy' or not status.get('model_ready'):
        raise RuntimeError('Comparison requires a ready, disposable VRoid copy')
    token = status['model_token']

    candidates = {}
    offset = 0
    while offset is not None and not all(p in candidates for p in spec.preset_ids):
        page = await _call(client, 'list_presets', area=area, category=category, offset=offset, limit=100)
        candidates.update((item['id'], item) for item in page['presets'] if item.get('owned'))
        offset = page.get('next_offset')
    missing = [p for p in spec.preset_ids if p not in candidates]
    if missing:
        raise ValueError('Presets unavailable in this VRoid installation: ' + ', '.join(missing))

    async def capture(label):
        return await _call(client, 'capture_review', expected_model=token, label=label[:80],
                           views=views, size=spec.size, include_images=False)

    rows = [('Saved baseline', None, await capture('Saved baseline'))]
    filename = source.relative_to(lab / 'saves').as_posix()
    for index, preset_id in enumerate(spec.preset_ids, 1):
        if index > 1:
            # Reopen instead of undoing a preset that may have changed multiple parts.
            status = await _call(client, 'open_character', expected_model=token,
                                 filename=filename, discard_unsaved=True)
            token = status['model_token']
        preset = candidates[preset_id]
        name = preset.get('name') or preset['label']
        label = f'{index}. {name}'
        applied = await _call(client, 'apply_preset', expected_model=token, area=area, preset_id=preset_id)
        if not (applied.get('selected') or applied.get('changed') or applied.get('clear')):
            raise RuntimeError(f'VRoid did not confirm applying {preset_id}')
        rows.append((label, preset_id, await capture(label)))

    if hashlib.sha256(source.read_bytes()).hexdigest() != original_hash:
        raise RuntimeError('Source model changed during comparison')
    path = lab / 'reviews' / f'preset-comparison-{uuid4().hex}.html'
    _make_report(source, views, rows, path)
    return {'ok': True, 'comparison_path': str(path), 'views': views,
            'variants': [{'label': label, 'preset_id': preset_id, 'capture_id': capture['capture_id']}
                         for label, preset_id, capture in rows]}
