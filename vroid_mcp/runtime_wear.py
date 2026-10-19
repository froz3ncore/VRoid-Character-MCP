"""Dress-up assembly operations for one lab.

An assembly is addressed by `wear_token`, not by the model token. Every method
re-reads the native state and refuses a stale token, and any operation whose
result cannot be confirmed marks the session uncertain instead of guessing: an
assembly that may have changed is not safe to save over.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import pathlib
import re
import time
import uuid
import zipfile

from .capture_quality import decode_capture, quality_plan
from .capture_views import is_regional, validate_wear_views
from .lab_paths import review_folder
from .wear_paths import wear_destination, wear_input

CLIP_ID = re.compile('0x[0-9a-fA-F]+')
WEAR_TASK_SECONDS = 180
VRM_PREPARE_SECONDS = 60
ANIMATION_WAIT_SECONDS = 15
FIT_REGIONS = ('feet', 'waist_back', 'head', 'whole_body')
BASE_MESHES = ('Body', 'Foot', 'Face', 'Hair')


class WearTools:
    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _require_clip(clip_id: str, message: str) -> None:
        if not isinstance(clip_id, str) or not CLIP_ID.fullmatch(clip_id):
            raise ValueError(message)

    @staticmethod
    def _require_number(name: str, value, maximum: float, minimum: float = 0) -> None:
        if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
            raise ValueError('Invalid ' + name)

    async def _require_wear(self, expected_wear: str) -> dict:
        status = await self._call('get_wear_status')
        if status.get('wear_token') != expected_wear:
            raise ValueError('STALE_WEAR')
        return status

    async def _wear_task(self, task: dict) -> None:
        deadline = time.monotonic() + WEAR_TASK_SECONDS
        while time.monotonic() < deadline:
            try:
                result = await self._call('task_status', task)
            except Exception as error:
                if 'MAIN_THREAD_TIMEOUT: not executed' not in str(error):
                    raise
                # Polling only: never resubmit the mutation.
                continue
            if result['completed']:
                if result['faulted'] or result['canceled'] or result.get('result') is False:
                    raise RuntimeError(result.get('error', 'Wear operation canceled'))
                return
            await asyncio.sleep(.2)
        self.uncertain = True
        raise TimeoutError('Wear operation still pending; restart before further edits')

    # ------------------------------------------------------------------- status
    async def wear_status(self) -> dict:
        async with self.lock:
            return await self._call('get_wear_status')

    async def wear_snapshot(self, expected_wear: str) -> dict:
        async with self.lock:
            return await self._call('get_wear_snapshot', {'expected_wear': expected_wear})

    async def sample_wear_preview_rig(self, expected_wear: str) -> dict:
        async with self.lock:
            result = await self._call('sample_wear_preview_rig', {'expected_wear': expected_wear})
            if result['wear_token'] != expected_wear or result['model_modified'] is not False or not result['nodes']:
                raise ValueError('Native preview rig identity or state changed')
            if len(result['nodes']) > 4096:
                raise ValueError('Native preview rig node limit')
            seen = set()
            for node in result['nodes']:
                if node['id'] in seen:
                    raise ValueError('Duplicate native bone identity')
                seen.add(node['id'])
                matrix = node['world_matrix']
                if len(matrix) != 4 or any(len(row) != 4 for row in matrix):
                    raise ValueError('Malformed native bone matrix')
                if any(type(value) not in (int, float) or not math.isfinite(value)
                       for row in matrix for value in row):
                    raise ValueError('Malformed native bone matrix')
                if max(abs(a - b) for a, b in zip(matrix[3], [0, 0, 0, 1])) > 1e-5:
                    raise ValueError('Nonaffine native bone matrix')
            return result

    async def wear_preview_clips(self, expected_wear: str) -> dict:
        async with self.lock:
            return await self._call('list_wear_preview_clips', {'expected_wear': expected_wear})

    async def select_wear_preview_clip(self, expected_wear: str, clip_id: str | None) -> dict:
        if clip_id is not None:
            self._require_clip(clip_id, 'Use a session-local clip ID from list_wear_preview_clips, '
                                        'or null to restore the default')
        async with self.lock:
            return await self._call('select_wear_preview_clip', {'expected_wear': expected_wear,
                                                                 'clip_id': clip_id})

    # ------------------------------------------------------------------ capture
    async def capture_wear_reference(self, expected_wear: str, item_id: str,
                                     mesh_names: list[str] | None = None, preview: bool = False,
                                     include_base_meshes: bool = False,
                                     base_mesh_names: list[str] | None = None) -> dict:
        from .wear_reference import validate_wear_reference

        if type(preview) is not bool:
            raise ValueError('preview must be boolean')
        if type(include_base_meshes) is not bool:
            raise ValueError('include_base_meshes must be boolean')
        if base_mesh_names is not None:
            invalid = (not include_base_meshes or not base_mesh_names or len(base_mesh_names) > 4
                       or len(set(base_mesh_names)) != len(base_mesh_names)
                       or 'Body' not in base_mesh_names
                       or any(name not in BASE_MESHES for name in base_mesh_names))
            if invalid:
                raise ValueError('Choose Body and optional distinct Foot/Face/Hair base meshes')
        if mesh_names is not None:
            invalid = (not mesh_names or len(mesh_names) > 128
                       or len(set(mesh_names)) != len(mesh_names)
                       or any(not isinstance(name, str) or not name or len(name) > 200
                              for name in mesh_names))
            if invalid:
                raise ValueError('Choose 1-128 distinct names from get_wear_snapshot')

        async with self.lock:
            data = await self._call('capture_wear_reference', {
                'expected_wear': expected_wear, 'item_id': item_id, 'mesh_names': mesh_names,
                'preview': preview, 'include_base_meshes': include_base_meshes,
                'base_mesh_names': base_mesh_names})
            expected_pose = 'native_preview' if preview else 'native_edit'
            if (data['wear_token'] != expected_wear or data['item_id'] != item_id
                    or data['pose_source'] != expected_pose):
                raise ValueError('Native wear reference identity or pose source changed')
            validate_wear_reference(data)
            if include_base_meshes and 'Body' not in {mesh['name'] for mesh in data.get('base_meshes', [])}:
                raise ValueError('Native base Body reference missing')
            payload = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
            destination = wear_destination(self.lab, 'wear-reference-' + uuid.uuid4().hex + '.json',
                                           suffix='.json')
            with destination.open('xb') as stream:
                stream.write(payload)
            return {'captured': True, 'schema': data['schema'], 'wear_token': data['wear_token'],
                    'item_id': item_id, 'pose_source': data['pose_source'], 'frame': data['frame'],
                    'path': str(destination), 'bytes': len(payload),
                    'sha256': hashlib.sha256(payload).hexdigest(),
                    'body_vertices': len(data['body']['positions']),
                    'garments': [garment['name'] for garment in data['garments']],
                    'garment_vertices': sum(len(garment['positions']) for garment in data['garments']),
                    'bones': len(data['bones']),
                    'base_meshes': [mesh['name'] for mesh in data.get('base_meshes', [])],
                    'base_foot_source': data.get('base_foot_source')}

    async def capture_wear_review(self, expected_wear: str, views: list[str], size: int,
                                  quality: str = 'balanced') -> tuple[dict, list[bytes]]:
        quality_plan(size, quality)
        validate_wear_views(views)
        if type(size) is not int or not 256 <= size <= 2048:
            raise ValueError('Capture size must be 256..2048')
        capture_id = uuid.uuid4().hex
        folder = review_folder(self.lab, capture_id)
        async with self.lock:
            state = await self._call('get_wear_snapshot', {'expected_wear': expected_wear})
            reference = None
            if any(is_regional(view) for view in views):
                reference = await self._call('wear_framing_reference', {'expected_wear': expected_wear})
            folder.mkdir(parents=True, exist_ok=False)
            images: list[bytes] = []
            records = []
            for view in views:
                result = await self._call('wear_capture', {'expected_wear': expected_wear, 'view': view,
                                                           'size': size, 'quality': quality,
                                                           'framing_reference': reference})
                data = decode_capture(result, size, quality)
                result.pop('base64')
                path = folder / (view + '.png')
                path.write_bytes(data)
                images.append(data)
                records.append({**result, 'path': str(path), 'sha256': hashlib.sha256(data).hexdigest()})
            manifest = {'schema': 'vroid-wear-review-v1', 'capture_id': capture_id,
                        'wear_token': expected_wear, 'snapshot': state, 'quality': quality,
                        'images': records,
                        'scope': 'Native assembled static views; animation/VRM/Godot separate'}
            if reference:
                manifest['framing_reference'] = reference
            (folder / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                                  encoding='utf-8')
            return manifest, images

    async def capture_wear_motion(self, expected_wear: str, samples: int, interval_seconds: float,
                                  view: str, size: int, quality: str = 'balanced') -> dict:
        from .wear_motion import summarize_motion

        quality_plan(size, quality)
        if type(samples) is not int or not 3 <= samples <= 16:
            raise ValueError('Motion sample count must be 3..16')
        if type(interval_seconds) not in (int, float) or not math.isfinite(interval_seconds) \
                or not .1 <= interval_seconds <= 2:
            raise ValueError('Motion interval must be 0.1..2 seconds')
        validate_wear_views([view])
        if type(size) is not int or not 256 <= size <= 1024:
            raise ValueError('Motion image size must be 256..1024')
        folder = review_folder(self.lab, uuid.uuid4().hex)
        records = []
        fixed_bounds = None
        async with self.lock:
            status = await self._require_wear(expected_wear)
            if not status['animation_playing'] or not status['animation_ready']:
                raise ValueError('Start native animation before capturing motion')
            folder.mkdir(parents=True, exist_ok=False)
            started = time.monotonic()
            for index in range(samples):
                if index:
                    await asyncio.sleep(interval_seconds)
                result = await self._call('wear_motion_sample', {
                    'expected_wear': expected_wear, 'view': view, 'size': size,
                    'fixed_bounds': fixed_bounds, 'quality': quality})
                data = decode_capture(result, size, quality)
                result.pop('base64')
                fixed_bounds = result['bounds']
                path = folder / ('frame-%02d.png' % index)
                path.write_bytes(data)
                records.append({**result, 'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(),
                                'elapsed_seconds': time.monotonic() - started})
            final = await self._call('get_wear_status')
            if final['wear_token'] != expected_wear or not final['animation_playing']:
                raise RuntimeError('Native motion state changed during capture')
        summary = summarize_motion(records)
        manifest = {'schema': 'vroid-wear-motion-v1', 'wear_token': expected_wear, 'view': view,
                    'requested_interval_seconds': interval_seconds, 'size': size, 'quality': quality,
                    'samples': records, 'summary': summary, 'animation_left_playing': True,
                    'manifest_path': str(folder / 'motion.json')}
        (folder / 'motion.json').write_text(json.dumps(manifest, ensure_ascii=False, allow_nan=False,
                                                       indent=2), encoding='utf-8')
        keys = ('frame', 'path', 'sha256', 'elapsed_seconds', 'width', 'height', 'quality', 'framing')
        return {key: value for key, value in manifest.items() if key != 'samples'} | {
            'images': [{key: record[key] for key in keys if key in record} for record in records]}

    # ------------------------------------------------------------------ preview
    async def hold_wear_preview_pose(self, expected_wear: str, clip_id: str, seconds: float) -> dict:
        self._require_clip(clip_id, 'Use a freshly selected native clip ID')
        self._require_number('preview time', seconds, 60)
        async with self.lock:
            result = await self._call('hold_wear_preview_pose', {'expected_wear': expected_wear,
                                                                 'clip_id': clip_id, 'seconds': seconds})
            if (result['wear_token'] != expected_wear or result['clip_id'] != clip_id
                    or result['pose_held'] is not True or result['director_paused'] is not True):
                raise ValueError('Native frozen preview identity or state changed')
            if any(type(result[key]) not in (int, float) or not math.isfinite(result[key])
                   for key in ('seconds', 'clip_time')):
                raise ValueError('Nonfinite native preview time readback')
            if abs(result['seconds'] - seconds) > 1e-5 or abs(result['clip_time'] - seconds) > 1e-5:
                raise ValueError('Native preview time readback mismatch')
            return result

    async def pose_wear_preview_legs(self, expected_wear: str, clip_id: str, seconds: float,
                                     upper_leg_inward_degrees: float, foot_inward_degrees: float) -> dict:
        self._require_clip(clip_id, 'Use a fresh native preview clip ID')
        for name, value, maximum in (('seconds', seconds, 60),
                                     ('upper leg', upper_leg_inward_degrees, 6),
                                     ('foot', foot_inward_degrees, 12)):
            self._require_number(name, value, maximum)
        if upper_leg_inward_degrees > foot_inward_degrees:
            raise ValueError('Upper leg twist exceeds total foot yaw')
        async with self.lock:
            result = await self._call('pose_wear_preview_legs', {
                'expected_wear': expected_wear, 'clip_id': clip_id, 'seconds': seconds,
                'upper_leg_inward_degrees': upper_leg_inward_degrees,
                'foot_inward_degrees': foot_inward_degrees})
            if (result['wear_token'] != expected_wear or result['clip_id'] != clip_id
                    or result['director_paused'] is not True or result['session_only'] is not True):
                raise ValueError('Preview pose identity or state changed')
            if not math.isfinite(result['clip_time']) or abs(result['clip_time'] - seconds) > 1e-5:
                raise ValueError('Preview pose time mismatch')
            return result

    # ---------------------------------------------------------------- occlusion
    async def inspect_wear_body_occlusion(self, expected_wear: str) -> dict:
        from .wear_occlusion import describe

        async with self.lock:
            data = await self._call('inspect_wear_body_occlusion', {'expected_wear': expected_wear})
            if data['wear_token'] != expected_wear:
                raise ValueError('Native wear identity changed')
            return describe(data)

    async def set_wear_body_occlusion(self, expected_wear: str, expected_occlusion_token: str,
                                      hidden_vertices: list[int]) -> dict:
        from .wear_occlusion import describe, prepare

        async with self.lock:
            data = await self._call('inspect_wear_body_occlusion', {'expected_wear': expected_wear})
            if data['wear_token'] != expected_wear:
                raise ValueError('Native wear identity changed')
            args = prepare(data, expected_occlusion_token, hidden_vertices)
            if hidden_vertices == data['hidden_vertices']:
                return {'changed': False, **describe(data)}
            try:
                result = await self._call('set_wear_body_occlusion', args)
            except Exception as error:
                if 'BODY_MASK_MUTATION_UNCERTAIN' in str(error):
                    self.uncertain = True
                raise
            if result['hidden_vertices'] != hidden_vertices:
                self.uncertain = True
                raise RuntimeError('Body occlusion readback failed; inspect the saved state before another mutation')
            return result

    async def inspect_wear_native_shoes(self, expected_wear: str) -> dict:
        from .native_shoe_visibility import describe

        async with self.lock:
            data = await self._call('inspect_wear_native_shoes', {'expected_wear': expected_wear})
            if data['wear_token'] != expected_wear:
                raise ValueError('Native wear identity changed')
            return describe(data)

    async def set_wear_native_shoes_visible(self, expected_wear: str, expected_visibility_token: str,
                                            visible: bool) -> dict:
        from .native_shoe_visibility import describe, prepare

        async with self.lock:
            data = await self._call('inspect_wear_native_shoes', {'expected_wear': expected_wear})
            if data['wear_token'] != expected_wear:
                raise ValueError('Native wear identity changed')
            args = prepare(data, expected_visibility_token, visible)
            if args['hidden_vertices'] == data['hidden_vertices']:
                return {'changed': False, **describe(data)}
            try:
                result = await self._call('set_wear_native_shoes_visible', args)
            except Exception as error:
                if 'NATIVE_SHOE_MUTATION_UNCERTAIN' in str(error):
                    self.uncertain = True
                raise
            if result['hidden_vertices'] != args['hidden_vertices']:
                self.uncertain = True
                raise RuntimeError('Native shoe visibility readback failed; do not retry')
            return result

    # --------------------------------------------------------------------- fit
    async def inspect_wear_fit_context(self, expected_wear: str, item_id: str, mesh_names: list[str],
                                       region: str = 'feet', preview: bool = False,
                                       sample_limit: int = 256,
                                       target_mesh_name: str | None = None) -> dict:
        from .wear_fit import glb, inspect

        if region not in FIT_REGIONS:
            raise ValueError('Unsupported fit region')
        if type(sample_limit) is not int or not 32 <= sample_limit <= 2048:
            raise ValueError('sample_limit must be 32..2048')
        if not isinstance(mesh_names, list) or not 1 <= len(mesh_names) <= 16:
            raise ValueError('Choose 1-16 actual wearable mesh names')
        if target_mesh_name is not None and (target_mesh_name not in mesh_names or len(mesh_names) < 2):
            raise ValueError('Include the target mesh and at least one comparison mesh')
        base_names = (['Body', 'Foot'] if region == 'feet'
                      else ['Body'] if region == 'waist_back' else ['Body', 'Face', 'Hair'])
        captured = await self.capture_wear_reference(expected_wear, item_id, mesh_names, preview, True,
                                                     base_names)
        data = json.loads(pathlib.Path(captured['path']).read_text(encoding='utf-8'))
        report, meshes = await asyncio.to_thread(inspect, data, region, sample_limit, target_mesh_name)
        debug = wear_destination(self.lab, 'fit-context-' + uuid.uuid4().hex + '.glb', '.glb')
        payload = await asyncio.to_thread(glb, meshes)
        with debug.open('xb') as stream:
            stream.write(payload)
        report.update(raw_reference=captured,
                      debug_glb={'path': str(debug), 'bytes': len(payload),
                                 'sha256': hashlib.sha256(payload).hexdigest(),
                                 'scope': 'Static diagnostic anatomy and wearable geometry; '
                                          'no textures or animation'})
        destination = wear_destination(self.lab, 'fit-context-' + uuid.uuid4().hex + '.json', '.json')
        encoded = json.dumps(report, ensure_ascii=False, allow_nan=False,
                             separators=(',', ':')).encode('utf-8')
        with destination.open('xb') as stream:
            stream.write(encoded)
        return {**report, 'report_path': str(destination),
                'report_sha256': hashlib.sha256(encoded).hexdigest()}

    # ------------------------------------------------------------- project files
    async def open_wear_project(self, filename: str, expected_wear: str, discard_unsaved: bool) -> dict:
        path = wear_input(self.lab, filename, ('.vroid', '.xroid'))
        async with self.lock:
            await self._wear_task(await self._call('open_wear_project', {
                'path': str(path), 'expected_wear': expected_wear,
                'discard_unsaved': discard_unsaved}))
            status = await self._call('get_wear_status')
            if not status['active']:
                raise RuntimeError('Dress-up did not become active')
            return status

    async def wear_edit(self, operation: str, args: dict) -> dict:
        if operation not in ('set_wear_fit', 'set_wear_animation'):
            raise ValueError('Unsupported wear edit')
        async with self.lock:
            await self._call(operation, args)
            deadline = time.monotonic() + ANIMATION_WAIT_SECONDS
            while True:
                await asyncio.sleep(.2)
                result = await self._call('get_wear_status')
                ready = (result['animation_playing'] == args['playing']
                         and (not args['playing'] or result['animation_ready']))
                if operation != 'set_wear_animation' or ready:
                    return result
                if time.monotonic() > deadline:
                    raise RuntimeError('WEAR_PREVIEW_NOT_READY: the native preview did not reach the '
                                       'requested state; inspect the copy before further edits')

    async def import_xwear(self, filename: str, expected_wear: str) -> dict:
        path = wear_input(self.lab, filename, ('.xwear',))
        async with self.lock:
            before = await self._call('get_wear_status')
            task = await self._call('import_xwear', {'path': str(path), 'expected_wear': expected_wear})
            after = before
            try:
                await self._wear_task(task)
            finally:
                if not self.uncertain and not self.dead:
                    after = await self._call('wear_finish_import', task)
            previous_ids = {item['id'] for item in before['items']}
            added = [item['id'] for item in after['items'] if item['id'] not in previous_ids]
            if not added:
                raise RuntimeError('Native import completed without a new wearable')
            return {**after, 'added_item_ids': added, 'auto_fit_applied': False,
                    'source_path': str(path)}

    async def save_wear_project(self, filename: str, expected_wear: str) -> dict:
        destination = wear_destination(self.lab, filename)
        staging = destination.parent / ('stage-' + uuid.uuid4().hex + '.xroid')
        async with self.lock:
            task = await self._call('save_wear_project', {'path': str(staging),
                                                          'expected_wear': expected_wear})
            await self._wear_task(task)
            if not staging.is_file() or not zipfile.is_zipfile(staging):
                raise RuntimeError('Native save did not create an XRoid archive')
            with zipfile.ZipFile(staging) as archive:
                if archive.testzip() is not None:
                    raise RuntimeError('XRoid archive CRC failure')
            await self._call('wear_clear_save_path', {'expected_wear': expected_wear})
            # os.rename refuses an existing destination on Windows.
            os.rename(staging, destination)
            return {'saved': True, 'path': str(destination), 'bytes': destination.stat().st_size,
                    'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
                    'wear_token': expected_wear, 'cache_path': task.get('cache_path')}

    async def export_wear_vrm(self, filename: str, expected_wear: str, title: str, author: str,
                              version: str = '1.0') -> dict:
        from .vrm_export import export_metadata, validate_vrm

        metadata = export_metadata(title, author, version)
        destination = wear_destination(self.lab, filename, '.vrm')
        staging = destination.parent / ('stage-' + uuid.uuid4().hex + '.vrm')
        async with self.lock:
            await self._call('prepare_wear_vrm_export', {'expected_wear': expected_wear})
            complete = False
            cleanup = None
            checked: dict = {}
            try:
                deadline = time.monotonic() + VRM_PREPARE_SECONDS
                while True:
                    state = await self._call('wear_vrm_export_state', {'expected_wear': expected_wear})
                    if state['wear_token'] != expected_wear or state['mode'] != 3:
                        raise RuntimeError('Native export identity or mode changed')
                    if state['ready'] and state['renderers'] > 0:
                        break
                    if time.monotonic() > deadline:
                        self.uncertain = True
                        raise TimeoutError('Native VRM preparation pending; inspect before another operation')
                    await asyncio.sleep(.2)
                task = await self._call('write_wear_vrm_export', {'expected_wear': expected_wear,
                                                                  'path': str(staging), **metadata})
                await self._wear_task(task)
                complete = True
                if not staging.is_file():
                    raise RuntimeError('Native exporter completed without a VRM file')
                checked = validate_vrm(staging)
                if (checked['metadata']['name'] != title
                        or checked['metadata']['authors'] != [author]
                        or checked['metadata'].get('version') != version):
                    raise RuntimeError('Native VRM metadata readback mismatch')
            except Exception:
                if not complete:
                    # Preparation may still own a live native task.
                    self.uncertain = True
                raise
            finally:
                if complete and not self.uncertain and not self.dead:
                    cleanup = await self._call('finish_wear_vrm_export', {'expected_wear': expected_wear})
            final = await self._call('get_wear_status')
            if final['wear_token'] != expected_wear or final['animation_playing']:
                raise RuntimeError('Wear state changed during export')
            os.rename(staging, destination)
            return {'exported': True, 'path': str(destination), 'wear_token': expected_wear, **checked,
                    'metadata_policy': 'restrictive_native_defaults', 'cleanup': cleanup,
                    'visual_fit_accepted': False, 'godot_accepted': False}
