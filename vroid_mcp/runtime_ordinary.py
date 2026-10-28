"""Parts and ordinary-edit VRM export with explicit model identity checks."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import struct
import time
import uuid

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
            return await self._call('list_parts', {'expected_model': expected_model})

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
            # Any replacement may change the model's body topology, so do not
            # permit texture entry until a fresh process reopens the model.
            return {'model_token': expected_model, 'part_id': part_id, 'replaced': True}

    async def save_custom_items(self, expected_model, types=None):
        raise RuntimeError('CUSTOM_ITEM_SAVE_UNAVAILABLE: the native request did not produce a '
                           'verifiable saved item in the isolated test. Use the VRoid interface '
                           'and verify the item in its closet; no save was attempted by MCP.')

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
