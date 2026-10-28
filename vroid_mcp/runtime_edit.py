"""Parameter, preset, height, history and save operations for one lab.

Every write goes through the native history, so a caller can undo it; every read
is labelled before it leaves this module. The two rules that matter here: a
model token must still match after a settle, and a saved file is written to a
staging name first and only renamed into place when it looks complete.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import pathlib
import time
import uuid
import zipfile
import shutil

from .color_state import attach_color_readback
from .lab_paths import save_destination
from .wear_paths import wear_input
from .file_paths import file_input, file_destination
from .parameter_labels import name_parameters
from .preset_labels import name_catalog, name_preset
from .preset_previews import decode_thumbnail, validate_request

PARAMETER_AREAS = ('face', 'body', 'clothing')
PRESET_AREAS = ('face', 'body', 'hair', 'clothing')
HEIGHT_PARAMETER = 'body/WholeBody/002'
HEIGHT_SAMPLES = 14
PREVIEW_TIMEOUT_SECONDS = 15
SELECTION_WAIT_SECONDS = 1


class EditTools:
    # ------------------------------------------------------------------ guards
    @staticmethod
    def _require_parameter_area(area: str) -> None:
        if area not in PARAMETER_AREAS:
            raise ValueError('Unsupported parameter area')

    @staticmethod
    def _require_preset_area(area: str) -> None:
        if area not in PRESET_AREAS:
            raise ValueError('Unsupported preset area')

    async def _settled_for(self, expected_model: str, after_frame: int = -1) -> dict:
        settled = await self._settle(after_frame)
        if settled['model_token'] != expected_model:
            raise RuntimeError('MODEL_CHANGED_DURING_OPERATION')
        return settled

    # -------------------------------------------------------------- parameters
    async def list_face_params(self) -> dict:
        return await self.list_params('face')

    async def list_params(self, area: str) -> dict:
        self._require_parameter_area(area)
        async with self.lock:
            return name_parameters(await self._call('list_' + area + '_params'))

    async def set_face_params(self, expected_model: str, changes: list[dict]) -> dict:
        return await self.set_params('face', expected_model, changes)

    async def set_params(self, area: str, expected_model: str, changes: list[dict]) -> dict:
        self._require_parameter_area(area)
        async with self.lock:
            result = await self._call('set_' + area + '_params',
                                      {'expected_model': expected_model, 'changes': changes})
            await self._settled_for(expected_model, result['frame'])
            result['settled'] = True
            return result

    async def parameter_call(self, operation: str, args: dict | None = None,
                             mutating: bool = False) -> dict:
        """Run one generic parameter operation, settling and labelling the result."""
        payload = args or {}
        async with self.lock:
            await self._settle()
            result = await self._call(operation, payload)
            if operation == 'list_parameters':
                result = name_parameters(result)
            if not mutating:
                return result
            expected = payload.get('expected_model')
            await self._settled_for(expected, result.get('frame', -1))
            result['settled'] = True
            if operation == 'set_parameters' and payload.get('domain') in ('colors', 'accessories'):
                rows = []
                offset = 0
                while True:
                    page = await self._call('list_parameters', {**payload, 'offset': offset, 'limit': 500})
                    if page['model_token'] != expected:
                        raise RuntimeError('MODEL_CHANGED_DURING_COLOR_READBACK')
                    rows.extend(name_parameters(page)['parameters'])
                    if page['next_offset'] is None:
                        break
                    offset = page['next_offset']
                result = attach_color_readback(result, rows)
            return result

    # ----------------------------------------------------------------- presets
    async def list_presets(self, area: str, category: str | None = None,
                           offset: int = 0, limit: int = 100) -> dict:
        self._require_preset_area(area)
        async with self.lock:
            return name_catalog(await self._call('list_presets', {'area': area, 'category': category,
                                                                  'offset': offset, 'limit': limit,
                                                                  'owned_only': True}))

    async def _owned_catalog(self, expected_model: str, area: str, wanted: list[str]) -> dict:
        """Page through the owned presets once until every wanted id is known."""
        catalog = await self._call('list_presets', {'expected_model': expected_model, 'area': area,
                                                    'offset': 0, 'limit': 200, 'owned_only': True})
        if catalog['model_token'] != expected_model:
            raise ValueError('Preset catalog identity mismatch')
        options = {preset['id']: preset for preset in catalog['presets']}
        while catalog.get('next_offset') is not None and not all(p in options for p in wanted):
            catalog = await self._call('list_presets', {'expected_model': expected_model, 'area': area,
                                                        'offset': catalog['next_offset'], 'limit': 200,
                                                        'owned_only': True})
            if catalog['model_token'] != expected_model:
                raise ValueError('Preset catalog identity mismatch')
            options.update((preset['id'], preset) for preset in catalog['presets'])
        if any(preset not in options for preset in wanted):
            raise ValueError('UNKNOWN_PRESET: relist owned presets')
        return options

    async def _thumbnail(self, expected_model: str, area: str, preset_id: str) -> tuple[dict, bytes | None]:
        started = await self._call('preset_preview_begin', {'expected_model': expected_model,
                                                            'area': area, 'preset_id': preset_id})
        request = started.get('request_id')
        result = started
        try:
            deadline = time.monotonic() + PREVIEW_TIMEOUT_SECONDS
            while not result.get('completed'):
                if time.monotonic() >= deadline:
                    raise TimeoutError('Native preset preview did not complete')
                await asyncio.sleep(.1)
                result = await self._call('preset_preview_poll', {'expected_model': expected_model,
                                                                  'request_id': request})
            if result.get('model_token') != expected_model or result.get('preset_id') != preset_id:
                raise ValueError('Native thumbnail identity mismatch')
            if result.get('ok'):
                metadata, data = decode_thumbnail(result, expected_model, preset_id)
                return metadata, data
            return {key: value for key, value in result.items() if key != 'base64'}, None
        finally:
            if request and not self.dead and not self.uncertain:
                await self._call('preset_preview_cancel', {'expected_model': expected_model,
                                                           'request_id': request})

    async def preview_presets(self, expected_model: str, area: str,
                              preset_ids: list[str]) -> tuple[dict, list[tuple[str, bytes]]]:
        validate_request(expected_model, area, preset_ids)
        async with self.lock:
            await self._settle()
            options = await self._owned_catalog(expected_model, area, preset_ids)
            items: list[dict] = []
            images: list[tuple[str, bytes]] = []
            for preset_id in preset_ids:
                item = name_preset(options[preset_id])
                metadata, data = await self._thumbnail(expected_model, area, preset_id)
                item.update(metadata)
                if data is not None:
                    images.append((preset_id, data))
                items.append(item)
            return {'model_token': expected_model, 'area': area, 'presets': items,
                    'scope': 'Native preset thumbnails, not the preset applied to this character'}, images

    async def apply_preset(self, area: str, expected_model: str, preset_id: str) -> dict:
        self._require_preset_area(area)
        async with self.lock:
            result = await self._call('apply_preset', {'area': area, 'expected_model': expected_model,
                                                       'preset_id': preset_id})
            await self._settle(result['frame'])
            before = result.pop('before_groups', None)
            query = {'area': area, 'expected_model': expected_model, 'preset_id': preset_id}
            if result.get('clear'):
                state = await self._call('preset_state', query)
                groups = state.get('active_groups', [])
                previous_ids = {group['id'] for group in before or []}
                current_ids = {group['id'] for group in groups}
                result.update(settled=True, selected=None, changed=groups != before,
                              active_groups=groups,
                              removed_groups=[group for group in before or [] if group['id'] not in current_ids],
                              confirmation='groups_removed' if previous_ids - current_ids else 'no_group_removed')
                return result
            deadline = time.monotonic() + SELECTION_WAIT_SECONDS
            state: dict = {}
            while time.monotonic() < deadline:
                state = await self._call('preset_state', query)
                if state['selected']:
                    result.update(settled=True, selected=True)
                    return result
                await asyncio.sleep(.15)
            # Some native hair sets expand into parts and drop the whole-set
            # checkbox. The operation has settled; report the evidence instead of
            # inventing a selection.
            groups = state.get('active_groups', [])
            changed = before is not None and groups != before
            result.update(settled=True, selected=False, changed=changed, active_groups=groups,
                          confirmation=('model_changed_without_preset_checkmark' if changed
                                        else 'selection_unconfirmed'),
                          message='Inspect the model and a screenshot; an unchecked set does not '
                                  'establish failure or exact preset equivalence.')
            return result

    # ------------------------------------------------------------ shoe templates
    async def list_shoe_templates(self, expected_model: str) -> dict:
        async with self.lock:
            await self._settle()
            return await self._call('list_shoe_templates', {'expected_model': expected_model})

    async def add_shoe_template(self, expected_model: str, template_id: str) -> dict:
        if not isinstance(template_id, str) or not template_id.strip():
            raise ValueError('A fresh native shoe template ID is required')
        async with self.lock:
            await self._settle()
            result = await self._call('add_shoe_template', {'expected_model': expected_model,
                                                            'template_id': template_id})
            await self._settle(result['frame'])
            state = await self._call('shoe_template_state', {'expected_model': expected_model})
            if state['model_token'] != expected_model:
                raise RuntimeError('MODEL_CHANGED_DURING_TEMPLATE_ADD')
            before = result.pop('before_groups')
            after = state['active_groups']
            previous_ids = {group['id'] for group in before}
            current_ids = {group['id'] for group in after}
            added = [group for group in after if group['id'] not in previous_ids]
            removed = [group for group in before if group['id'] not in current_ids]
            confirmed = len(added) == 1 and added[0]['type'].split('.')[-1] == 'Shoes' and not removed
            return {**result, 'settled': True, 'ok': confirmed,
                    'confirmation': ('native_shoe_group_added' if confirmed
                                     else 'unconfirmed_model_change'),
                    'active_groups': after, 'added_groups': added, 'removed_groups': removed,
                    'retry_safe': False}

    # ------------------------------------------------------------------- height
    async def set_height(self, expected_model: str, centimeters: float, tolerance_cm: float = .05) -> dict:
        if not math.isfinite(centimeters) or not 20 <= centimeters <= 400:
            raise ValueError('Height must be 20..400 cm; the native model range can be narrower')
        if not .01 <= tolerance_cm <= .5:
            raise ValueError('Tolerance must be .01...5 cm')
        args = {'expected_model': expected_model}
        async with self.lock:
            await self._settle()
            body = await self._call('list_body_params', args)
            parameter = next(item for item in body['parameters'] if item['id'] == HEIGHT_PARAMETER)
            initial = parameter['value']
            scale = initial
            samples: list[dict] = []

            async def measure() -> float:
                # BodyHeightValue is a UI cache and can be stale after loading.
                # Always solve against the current native geometry measurement.
                reading = await self._call('get_height', args)
                value = float(reading['live_centimeters'])
                if not math.isfinite(value):
                    raise RuntimeError('Native live height is not finite')
                return value

            async def apply(value: float) -> float:
                written = await self._call('set_body_params', {**args, 'changes': [
                    {'id': parameter['id'], 'value': value}]})
                if not written['ok']:
                    raise RuntimeError(written)
                await self._settle(written['frame'])
                return await measure()

            measured = await measure()
            for _ in range(HEIGHT_SAMPLES):
                samples.append({'scale_parameter': scale, 'centimeters': measured})
                if abs(measured - centimeters) <= tolerance_cm:
                    return {'model_token': expected_model, 'target_cm': centimeters,
                            'measured_cm': measured, 'error_cm': measured - centimeters,
                            'tolerance_cm': tolerance_cm, 'scale_parameter': scale, 'samples': samples,
                            'settled': True,
                            'measurement': 'VRoid native GetBodyHeight (live); hairstyle and model '
                                           'proportions can affect this measurement'}
                if len(samples) == 1:
                    # Nudge the scale first so the next sample gives a slope.
                    next_scale = min(1, scale + .05) if scale < .95 else scale - .05
                else:
                    previous = samples[-2]
                    span = scale - previous['scale_parameter']
                    slope = (measured - previous['centimeters']) / span if span else 0
                    if abs(slope) < 1e-6:
                        break
                    next_scale = max(parameter['min'], min(parameter['max'],
                                                           scale + (centimeters - measured) / slope))
                if abs(next_scale - scale) < 1e-7:
                    break
                scale = next_scale
                measured = await apply(scale)
            restored = await apply(initial)
            raise ValueError('Height did not converge inside the native range; the original scale was '
                             f'restored ({restored:.3f} cm)')

    # ------------------------------------------------------------ history / save
    async def history(self, method: str, expected_model: str, steps: int = 1) -> dict:
        if method not in ('undo', 'redo') or not 1 <= steps <= 32:
            raise ValueError('Invalid history operation')
        async with self.lock:
            for _ in range(steps):
                result = await self._call(method, {'expected_model': expected_model})
                await self._task(result)
                await self._settle(result['frame'])
            return name_parameters(await self._call('list_face_params', {'expected_model': expected_model}))

    async def save_as(self, filename: str, expected_model: str) -> dict:
        async with self.lock:
            destination = (file_destination(self.lab, filename, '.vroid', True)
                           if getattr(self, 'mode', 'copy') == 'attached' else save_destination(self.lab, filename))
            staging = destination.parent / ('stage-' + uuid.uuid4().hex + '.vroid')
            await self._settle()
            await self._call('save_as', {'path': str(staging), 'expected_model': expected_model})
            if not staging.is_file() or staging.stat().st_size < 100:
                raise RuntimeError('VRoid did not produce a file of a plausible size')
            if not zipfile.is_zipfile(staging):
                raise RuntimeError('Native save did not create a VRoid archive')
            with zipfile.ZipFile(staging) as archive:
                if archive.testzip() is not None:
                    raise RuntimeError('VRoid archive CRC failure')
            # os.rename refuses an existing destination on Windows; never os.replace.
            os.rename(staging, destination)
            return {'path': str(destination), 'bytes': destination.stat().st_size,
                    'model_token': expected_model,
                    'attached_copy': getattr(self, 'mode', 'copy') == 'attached',
                    'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}

    async def reopen_for_test(self, path: pathlib.Path) -> dict:
        resolved = path.resolve()
        if not resolved.is_relative_to(self.lab) or not resolved.is_file():
            raise ValueError('Only models inside this lab may be opened')
        async with self.lock:
            await self._task(await self._call('open_model', {'path': str(resolved)}))
            return await self._settle()

    async def replace_character(self, expected_model: str, discard_unsaved: bool, filename: str) -> dict:
        if discard_unsaved is not True:
            raise ValueError('EXPLICIT_DISCARD_REQUIRED')
        path = file_input(self.lab, filename, ('.vroid',), getattr(self, 'mode', 'copy') == 'attached')
        if not zipfile.is_zipfile(path):
            raise ValueError('Invalid VRoid archive')
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise ValueError('VRoid archive CRC failure')
        async with self.lock:
            await self._settled_for(expected_model)
            task = await self._call('replace_with_file', {'expected_model': expected_model,
                'discard_unsaved': True, 'path': str(path)})
            await self._task(task)
            result = await self._settle()
            if result['model_token'] == expected_model:
                self.uncertain = True
                raise RuntimeError('CHARACTER_SWITCH_IDENTITY_UNCONFIRMED')
            return result

    async def save_character(self, expected_model: str) -> dict:
        if getattr(self, 'mode', 'copy') != 'attached':
            raise ValueError('ATTACHED_ONLY')
        from .wear_paths import _physical
        async with self.lock:
            state = await self._settled_for(expected_model)
            ui = state['attached_state']
            if not ui.get('file_path'):
                raise ValueError('UNTITLED_CHARACTER: save to a new file first')
            path = pathlib.Path(ui['file_path'])
            if not path.is_absolute() or path.suffix.lower() != '.vroid' or not path.is_file():
                raise ValueError('Associated character must be an existing absolute .vroid file')
            _physical(path)
            original = hashlib.sha256(path.read_bytes()).hexdigest()
            backup = save_destination(self.lab, 'before-save-' + uuid.uuid4().hex + '.vroid')
            shutil.copyfile(path, backup)
            if hashlib.sha256(backup.read_bytes()).hexdigest() != original or hashlib.sha256(path.read_bytes()).hexdigest() != original:
                raise RuntimeError('SOURCE_CHANGED_BEFORE_SAVE')
            try:
                await self._call('save_character', {'expected_model': expected_model, 'path': str(path),
                    'command_revision': ui['command_revision']})
                with zipfile.ZipFile(path) as archive:
                    if archive.testzip() is not None:
                        raise RuntimeError('Saved character CRC failure')
            except Exception as error:
                raise RuntimeError('CHARACTER_SAVE_UNCERTAIN: inspect '+str(path)+' and backup '+str(backup)+'; do not retry blindly') from error
            return {'saved': True, 'path': str(path), 'backup_path': str(backup),
                'previous_sha256': original, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'bytes': path.stat().st_size, 'model_token': expected_model}

    async def new_character(self, expected_model: str, variant: str, discard_unsaved: bool) -> dict:
        if getattr(self, 'mode', 'copy') != 'attached':
            raise ValueError('ATTACHED_ONLY')
        if discard_unsaved is not True:
            raise ValueError('EXPLICIT_DISCARD_REQUIRED')
        if variant not in ('F00','M00'):
            raise ValueError('Unsupported variant')
        async with self.lock:
            await self._settled_for(expected_model)
            await self._call('replace_with_new_character', {'expected_model':expected_model,
                'variant':variant, 'discard_unsaved':True})
            deadline = time.monotonic() + 60
            while True:
                state = await self._call('status')
                ui = state.get('attached_state', {})
                if not state.get('model_ready') and ui.get('active_screen') == 'VRoid.Studio.StartScreen.ViewModel':
                    break
                if time.monotonic() >= deadline:
                    self.uncertain = True
                    raise TimeoutError('Native exit is pending; inspect the window before creating a character')
                await asyncio.sleep(.1)
            await self._call('finish_new_character', {'variant':variant})
            result = await self._settle()
            if result['model_token'] == expected_model:
                self.uncertain = True
                raise RuntimeError('CHARACTER_SWITCH_IDENTITY_UNCONFIRMED')
            return result

    async def save_character_as(self, expected_model: str, path: str) -> dict:
        if getattr(self, 'mode', 'copy') != 'attached':
            raise ValueError('ATTACHED_ONLY')
        before = await self.status()
        if before.get('model_token') != expected_model:
            raise ValueError('STALE_MODEL')
        saved = await self.save_as(path, expected_model)
        try:
            async with self.lock:
                await self._call('associate_character_file', {'expected_model':expected_model,
                    'path':saved['path'], 'command_revision':before['attached_state']['command_revision']})
        except Exception as error:
            raise RuntimeError('SAVED_FILE_ASSOCIATION_UNCERTAIN: inspect '+saved['path']+' and the window; do not retry blindly') from error
        return {**saved, 'attached_copy':False, 'associated':True}
