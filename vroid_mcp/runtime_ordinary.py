"""Parts and ordinary-edit VRM export with explicit model identity checks."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import struct
import time
import uuid
import pathlib
import zipfile

from .wear_paths import wear_destination


def check_vrm_container(path, version):
    """Check the GLB envelope and requested VRM extension; not a full VRM validator."""
    raw = path.read_bytes()
    if len(raw) < 28:
        raise ValueError('Truncated VRM export')
    magic, gltf_version, total = struct.unpack_from('<4sII', raw)
    if magic != b'glTF' or gltf_version != 2 or total != len(raw):
        raise ValueError('Invalid GLB header or length')
    length, chunk_type = struct.unpack_from('<I4s', raw, 12)
    if chunk_type != b'JSON' or length % 4 or 20 + length > len(raw):
        raise ValueError('Invalid GLB JSON chunk')
    doc = json.loads(raw[20:20 + length])
    extension = 'VRM' if version == 0 else 'VRMC_vrm'
    if extension not in doc.get('extensions', {}):
        raise ValueError('Expected VRM extension missing: ' + extension)
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
            'format': 'VRM 0.x' if version == 0 else 'VRM 1.0',
            'validation_scope': 'GLB envelope and VRM extension only; visual and runtime acceptance separate'}


class OrdinaryTools:
    async def _require_live_model(self, token):
        if not isinstance(token, str) or not token:
            raise ValueError('EXPECTED_MODEL_REQUIRED: pass a fresh model_token')
        status = await self._call('status')
        if not status.get('model_ready') or status.get('model_token') != token:
            raise ValueError('STALE_MODEL: list parameters again')

    async def list_parts(self, expected_model):
        async with self.lock:
            await self._require_live_model(expected_model)
            await self._settle()
            result = await self._call('list_parts', {'expected_model': expected_model})
            closet = await self._call('custom_item_state', {'expected_model': expected_model})
            result['custom_items'] = closet['files']
            result['savable_types'] = sorted({p['type'] for p in closet['parts']})
            return result

    async def replace_part(self, expected_model, part_id):
        async with self.lock:
            await self._require_live_model(expected_model)
            await self._settle()
            before = await self._call('list_parts', {'expected_model': expected_model})
            if any(part['id'] == part_id for part in before['parts']):
                return {'model_token': expected_model, 'part_id': part_id,
                        'replaced': False, 'reason': 'ALREADY_ACTIVE'}
            # A partially failed native replacement may still alter topology.
            self.body_edited_tokens.add(expected_model)
            result = await self._call('replace_part', {'expected_model': expected_model, 'part_id': part_id})
            deadline = time.monotonic() + 30
            while True:
                await asyncio.sleep(.3)
                settled = await self._settle(result['frame'])
                if settled.get('model_token') != expected_model:
                    raise RuntimeError('MODEL_CHANGED_DURING_OPERATION')
                parts = await self._call('list_parts', {'expected_model': expected_model})
                if any(part['id'] == part_id for part in parts['parts']):
                    break
                if time.monotonic() > deadline:
                    self.uncertain = True
                    raise RuntimeError('REPLACE_PART_UNCONFIRMED: native load may still be pending; inspect Player.log')
            # Retain the edit record for fallback sessions without the decoder.
            return {'model_token': expected_model, 'part_id': part_id, 'replaced': True}

    async def save_custom_items(self, expected_model, types=None):
        if self.mode == 'attached' and not getattr(self, 'native_png_decoder_ready', False):
            raise RuntimeError('ATTACHED_CUSTOM_ITEM_SAVE_UNAVAILABLE: verified attachment is required')
        if types is not None and (not isinstance(types, list) or not types or
                                  any(not isinstance(t, str) or not t for t in types) or len(set(types)) != len(types)):
            raise ValueError('types must be a nonempty list of unique savable type names')
        async with self.lock:
            await self._require_live_model(expected_model)
            await self._settle()
            args = {'expected_model': expected_model}
            snapshot = await self._call('custom_item_state', args)
            root = pathlib.Path(snapshot['base_path']).resolve()
            profile = (self.lab / 'profile').resolve()
            attached = self.mode == 'attached'
            if (not attached and (not root.is_relative_to(profile) or root == profile)) or not root.is_dir():
                raise RuntimeError('CUSTOM_ITEM_PROFILE_MISMATCH')
            parts = snapshot['parts']
            if types is not None:
                parts = [p for p in parts if p['type'] in types]
                if sorted(p['type'] for p in parts) != sorted(types):
                    raise ValueError('Unknown or ambiguous savable type; use list_parts savable_types')
            if not parts:
                raise ValueError('No savable parts in the current model')
            saved = []
            known = {p.resolve() for p in root.rglob('*.vroidcustomitem')}
            known.update(pathlib.Path(item['path']).resolve() for item in snapshot['files'])
            try:
                for part in parts:
                    await self._call('save_custom_item', {**args, 'part_id': part['id']})
                    deadline = time.monotonic() + 30
                    while True:
                        current = await self._call('custom_item_state', args)
                        if pathlib.Path(current['base_path']).resolve() != root:
                            raise RuntimeError('CUSTOM_ITEM_PROFILE_CHANGED')
                        matches = []
                        for item in current['files']:
                            path = pathlib.Path(item['path']).resolve()
                            if path in known or item['group_type'] != part['group_type']:
                                continue
                            if not path.is_relative_to(root):
                                raise RuntimeError('CUSTOM_ITEM_PATH_OUTSIDE_PROFILE')
                            if path.is_file():
                                matches.append((path, item))
                        if len(matches) > 1:
                            raise RuntimeError('CUSTOM_ITEM_SAVE_AMBIGUOUS')
                        if matches:
                            path, item = matches[0]
                            with zipfile.ZipFile(path) as archive:
                                if archive.testzip() is not None:
                                    raise RuntimeError('CUSTOM_ITEM_ARCHIVE_CORRUPT')
                                meta = json.loads(archive.read('v1customitem/meta.json'))
                                if (meta['rootTransferableGroupId'] != item['id'] or
                                        meta['rootTransferableGroupTypeId'] != part['group_type']):
                                    raise RuntimeError('CUSTOM_ITEM_METADATA_MISMATCH')
                            saved.append({**item, 'type': part['type'], 'bytes': path.stat().st_size,
                                          'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
                            known.add(path)
                            break
                        if time.monotonic() > deadline:
                            raise TimeoutError('CUSTOM_ITEM_SAVE_UNCONFIRMED: inspect closet; do not retry blindly')
                        await asyncio.sleep(.3)
                if attached:
                    await self._settle()
                    await self._call('preserve_attached_unsaved', {**args,
                        'source_file_path': snapshot['source_file_path'], 'was_unsaved': snapshot['unsaved']})
            except BaseException:
                self.uncertain = True
                raise
            return {'model_token': expected_model, 'saved': saved,
                    'profile_scope': 'attached VRoid profile' if attached else 'lab profile',
                    'verified': 'ZIP integrity, metadata and native closet registration; cold reopen is separate'}

    async def export_vrm(self, expected_model, filename, version=1, title=None, author=None):
        if type(version) is not int or version not in (0, 1):
            raise ValueError('version must be 0 or 1')
        for name, value in (('title', title), ('author', author)):
            if value is not None and (not isinstance(value, str) or not value.strip() or len(value) > 160 or any(ord(c) < 32 or ord(c) == 127 for c in value)):
                raise ValueError('Invalid VRM metadata: ' + name)
        async with self.lock:
            await self._require_live_model(expected_model)
            await self._settle()
            destination = wear_destination(self.lab, filename, '.vrm')
            staging = destination.parent / ('stage-' + uuid.uuid4().hex + '.vrm')
            args = {'expected_model': expected_model}
            state = await self._call('vrm_export_state', args)
            if state.get('model_token') != expected_model or state.get('busy'):
                raise RuntimeError('VRM_EXPORT_STATE_INVALID')
            entered = not state['export_screen']
            completed = False
            started = False
            try:
                if entered:
                    await self._call('enter_vrm_export', args)
                deadline = time.monotonic() + 60
                while True:
                    state = await self._call('vrm_export_state', args)
                    if state.get('model_token') != expected_model:
                        raise RuntimeError('MODEL_CHANGED_DURING_OPERATION')
                    if state['ready']:
                        break
                    if time.monotonic() > deadline:
                        self.uncertain = True
                        raise TimeoutError('VRM export preparation timed out; state uncertain')
                    await asyncio.sleep(.3)
                await self._call('start_vrm_export', {**args, 'version': version, 'path': str(staging),
                                                      'title': title, 'author': author})
                started = True
                deadline = time.monotonic() + 900
                while True:
                    status = await self._call('vrm_export_status')
                    if not status['running']:
                        completed = True
                        break
                    if time.monotonic() > deadline:
                        self.uncertain = True
                        raise TimeoutError('VRM export timed out; do not retry')
                    await asyncio.sleep(1)
                if not status.get('done') or not staging.is_file():
                    raise RuntimeError('VRM_EXPORT_FAILED: inspect Player.log')
                checked = check_vrm_container(staging, version)
            except BaseException:
                if started and not completed:
                    self.uncertain = True
                raise
            finally:
                if entered and not self.uncertain and not self.dead:
                    await self._call('leave_vrm_export', args)
            os.rename(staging, destination)
            return {'exported': True, 'model_token': expected_model, 'path': str(destination), **checked}
