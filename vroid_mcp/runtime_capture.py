"""Screenshot, multi-view review and body-reference capture for one lab.

A review is a reproducible set of native renders plus the numeric state they were
taken at: the same request must produce the same framing, and a baseline is only
accepted when its views, size, capture quality and effective MSAA all match. The
images are evidence for a human, never an automatic verdict.
"""

from __future__ import annotations

import base64
import asyncio
import hashlib
import json
import time
import uuid

from .capture_quality import decode_capture, quality_plan
from .capture_views import is_regional, review_reference
from .color_state import attach_color_readback
from .lab_paths import review_folder, validate_capture

CHECKLIST = [
    'eye and eyebrow balance',
    'bangs obscuring eyes',
    'hair/scalp gaps',
    'hair/clothing intersections',
    'head/body and limb proportions',
    'front/side/back silhouette',
]


class CaptureTools:
    async def _native_capture(self, args):
        try:
            return await self._call('screenshot', args)
        except BaseException as error:
            if (isinstance(error, asyncio.CancelledError)
                or any(code in str(error) for code in ('CAPTURE_CLEANUP_FAILED', 'PHOTO_CAMERA_OWNER_CHANGED'))):
                self.uncertain = True
            raise

    async def capture_body_reference(self, expected_model: str, label: str = '') -> dict:
        """Save the current body and face geometry as one validated JSON artifact."""
        from .body_reference import validate_body_reference
        from .wear_paths import wear_destination

        if not expected_model:
            raise ValueError('expected_model is required')
        destination = wear_destination(self.lab, 'body-reference-' + uuid.uuid4().hex + '.json', '.json')
        async with self.lock:
            dress_up = await self._call('get_wear_status')
            if dress_up['active']:
                raise ValueError('DRESS_UP_ACTIVE: a body reference describes ordinary editing, not an assembly')
            await self._settle()
            captured = await self._call('capture_body_reference', {'expected_model': expected_model})
            summary = validate_body_reference(captured, expected_model)
            captured['label'] = label
            encoded = json.dumps(captured, ensure_ascii=False, allow_nan=False).encode('utf-8')
            # Exclusive creation: never overwrite a previous reference.
            with destination.open('xb') as output:
                output.write(encoded)
            return {**summary, 'captured': True, 'path': str(destination), 'bytes': len(encoded),
                    'sha256': hashlib.sha256(encoded).hexdigest(), 'label': label,
                    'scope': captured['scope']}

    async def _capture(self, view: str, expected_model: str, size: int, quality: str = 'balanced',
                       metadata: dict | None = None, framing_metadata: dict | None = None,
                       framing_reference: dict | None = None) -> bytes:
        result = await self._native_capture({'view': view, 'expected_model': expected_model,
                                                 'size': size, 'quality': quality,
                                                 'framing_reference': framing_reference})
        if result.get('model_token') != expected_model:
            raise ValueError('MODEL_CHANGED_DURING_CAPTURE')
        if metadata is not None:
            metadata.update(result['quality'])
        if framing_metadata is not None and 'framing' in result:
            framing_metadata.update(result['framing'])
        return decode_capture(result, size, quality)

    async def screenshot(self, view: str, expected_model: str, size: int = 512,
                         quality: str = 'balanced', *, width=None, height=None, msaa=None, ssaa=None,
                         clean=True) -> bytes:
        data, _ = await self.screenshot_with_metadata(view, expected_model, size, quality,
            width=width, height=height, msaa=msaa, ssaa=ssaa, clean=clean)
        return data

    async def screenshot_with_metadata(self, view: str, expected_model: str, size: int = 512,
                         quality: str = 'balanced', *, width=None, height=None, msaa=None, ssaa=None,
                         clean=True) -> tuple[bytes, dict]:
        if not isinstance(expected_model, str) or not expected_model:
            raise ValueError('EXPECTED_MODEL_REQUIRED: pass a fresh model_token')
        if type(clean) is not bool:
            raise ValueError('Capture clean must be boolean')
        if not clean and (view not in ('front', 'current_editor') or size != 512 or quality != 'balanced'
            or any(v is not None for v in (width, height, msaa, ssaa))):
            raise ValueError('APP_FRAME_OVERRIDES: use default view or current_editor and default clean-render arguments')
        if view != 'current_editor':
            validate_capture([view], size)
        overrides = dict(width=width, height=height, msaa=msaa, ssaa=ssaa)
        quality_plan(size, quality, **overrides)
        async with self.lock:
            state = await self._settle()
            if state.get('model_token') != expected_model:
                raise ValueError('STALE_MODEL: list parameters again')
            # Guide isolation belongs to the native render scope. No host-side
            # selection/controller mutation may survive settle or PNG failures.
            args = dict(view=view, expected_model=expected_model, size=size, quality=quality, clean=clean, **overrides)
            if clean:
                result = await self._native_capture(args)
                data = decode_capture(result, size, quality, **overrides)
            else:
                try:
                    ticket = await self._call('start_app_frame', {'expected_model': expected_model})
                    deadline = time.monotonic() + 12
                    while True:
                        done = await self._call('poll_app_frame', ticket)
                        if done.get('completed'):
                            if done.get('error'):
                                raise RuntimeError(done['error'])
                            result = done['result']
                            break
                        if time.monotonic() >= deadline:
                            raise TimeoutError('APP_FRAME_TIMEOUT: do not retry')
                        await asyncio.sleep(.05)
                    data = self._decode_app_frame(result, expected_model)
                except BaseException:
                    self.uncertain = True
                    raise
            if result.get('model_token') != expected_model:
                raise ValueError('MODEL_CHANGED_DURING_CAPTURE')
            return data, {key: value for key, value in result.items() if key != 'base64'}

    @staticmethod
    def _decode_app_frame(result, expected_model):
        width, height = result.get('width'), result.get('height')
        if (result.get('model_token') != expected_model or result.get('provenance') != 'unity_application_frame'
            or result.get('phase') != 'UnityEngine.Awaitable.OnEndOfFrame.onLeave'
            or type(width) is not int or type(height) is not int or min(width, height) < 1
            or width * height > 8_000_000):
            raise ValueError('Invalid native application frame metadata')
        data = base64.b64decode(result['base64'], validate=True)
        if (len(data) < 24 or data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR'
            or int.from_bytes(data[16:20], 'big') != width or int.from_bytes(data[20:24], 'big') != height):
            raise ValueError('Unexpected application PNG dimensions')
        return data

    # ------------------------------------------------------------------ review
    def _load_baseline(self, baseline_id: str, views: list[str], size: int, quality: str,
                       images: list) -> tuple[dict | None, dict]:
        folder = review_folder(self.lab, baseline_id)
        metadata_path = folder / 'review.json'
        if metadata_path.resolve() != metadata_path:
            raise ValueError('Baseline metadata must not be a link')
        baseline = json.loads(metadata_path.read_text(encoding='utf-8'))
        if baseline['views'] != views or baseline['size'] != size:
            raise ValueError('Baseline views and size must match')
        if baseline.get('quality', 'legacy') != quality:
            raise ValueError('Baseline capture quality must match')
        previous = {}
        for view in views:
            source = folder / (view + '.png')
            if source.resolve() != source:
                raise ValueError('Baseline images must not be links')
            data = source.read_bytes()
            if hashlib.sha256(data).hexdigest() != baseline['images'][view]['sha256']:
                raise ValueError('Baseline image was modified')
            previous[view] = data
            images.append(('before / ' + view, data))
        return baseline, previous

    async def _review_state(self, expected_model: str) -> dict:
        state: dict = {}
        for area in ('face', 'body', 'clothing'):
            state[area] = await self._call('list_' + area + '_params', {'expected_model': expected_model})
        state['colors'] = await self._call('list_parameters', {'domain': 'colors', 'limit': 200,
                                                              'expected_model': expected_model})
        state['height'] = await self._call('get_height', {'expected_model': expected_model})
        return state

    @staticmethod
    def _parameter_changes(baseline: dict, state: dict) -> list[dict]:
        changes = []
        for area in ('face', 'body', 'clothing', 'colors'):
            previous = {item['id']: item['value'] for item in baseline['state'][area]['parameters']}
            for item in state[area]['parameters']:
                if item.get('alias_of'):
                    continue
                if previous.get(item['id']) != item['value']:
                    changes.append({'area': area, 'id': item['id'], 'label': item['label'],
                                    'before': previous.get(item['id']), 'after': item['value']})
        return changes

    async def capture_review(self, expected_model: str, views: list[str], size: int = 1024,
                             label: str = '', baseline_id: str | None = None,
                             quality: str = 'balanced') -> tuple[dict, list[tuple[str, bytes]]]:
        """Render 1-6 native views with their numeric state; a human judges the result."""
        validate_capture(views, size)
        quality_plan(size, quality)
        if 'photo' in views:
            raise ValueError('Animated photo previews use screenshot; review is for reproducible views')
        if len(label) > 80:
            raise ValueError('Label must be at most 80 characters')

        baseline = None
        images: list = []
        if baseline_id:
            baseline, _ = self._load_baseline(baseline_id, views, size, quality, images)

        async with self.lock:
            status = await self._settle()
            if status['model_token'] != expected_model:
                raise ValueError('MODEL_CHANGED')
            if status.get('photo_active'):
                raise ValueError('Leave photo preview before capture_review')
            framing_reference = framing_mode = None
            if any(is_regional(view) for view in views):
                fresh = await self._call('capture_framing_reference', {'expected_model': expected_model})
                framing_reference, framing_mode = review_reference(fresh, baseline)
            rendered = []
            for view in views:
                metadata: dict = {}
                framing: dict = {}
                data = await self._capture(view, expected_model, size, quality, metadata, framing,
                                           framing_reference)
                if baseline:
                    recorded = baseline['images'][view].get('quality', {}).get('msaa_samples', 1)
                    if recorded != metadata['msaa_samples']:
                        raise ValueError('Baseline effective MSAA must match')
                rendered.append((view, data, metadata, framing))
            state = await self._review_state(expected_model)
            final = await self._call('status')
            if final['model_token'] != expected_model:
                raise ValueError('MODEL_CHANGED_DURING_CAPTURE')

        capture_id = uuid.uuid4().hex
        folder = review_folder(self.lab, capture_id)
        folder.mkdir(parents=True, exist_ok=False)
        manifest = {
            'capture_id': capture_id, 'label': label, 'model_token': expected_model,
            'created_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'views': views, 'size': size,
            'baseline_id': baseline_id, 'quality': quality, 'state': state, 'images': {},
            'visual_review_required': True, 'checklist': CHECKLIST,
            'limitations': 'Native rendered evidence, not an automated beauty score or geometry '
                           'collision test. Hair simulation may vary between frames.',
        }
        if framing_reference:
            manifest.update(framing_reference=framing_reference, framing_mode=framing_mode)
        for view, data, metadata, framing in rendered:
            path = folder / (view + '.png')
            path.write_bytes(data)
            manifest['images'][view] = {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(),
                                        'quality': metadata}
            if framing:
                manifest['images'][view]['framing'] = framing
            images.append(('after / ' + view if baseline else view, data))
        if baseline:
            manifest['parameter_changes'] = self._parameter_changes(baseline, state)
            manifest['baseline_same_model_token'] = baseline['model_token'] == expected_model
        manifest['manifest_path'] = str(folder / 'review.json')
        (folder / 'review.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        return manifest, images
