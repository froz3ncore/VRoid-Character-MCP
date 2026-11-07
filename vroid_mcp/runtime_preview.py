"""Bounded, serialized editor-only state, independent of saved expressions."""
import asyncio
import math
import time
from contextlib import asynccontextmanager

from .exception_notes import add_exception_note

MODES = ('Front', 'Right', 'Top', 'Reverse', 'RotateUp', 'RotateLeft', 'RotateRight', 'RotateDown')


def validate_camera(expected_model, action, **arguments):
    fields = {'get': (), 'angles': ('angles',), 'rotate': ('angles',), 'zoom': ('delta',),
              'pan': ('pan',), 'reset': (), 'mode': ('mode',), 'projection': (), 'custom': ('position', 'center')}
    if not isinstance(expected_model, str) or not expected_model or action not in fields:
        raise ValueError('INVALID_EDITOR_CAMERA_ACTION_OR_MODEL')
    if any(v is not None and k not in fields[action] for k, v in arguments.items()):
        raise ValueError('UNRELATED_CAMERA_ARGUMENT')
    def vector(value, count, bound):
        return isinstance(value, list) and len(value) == count and all(
            type(v) in (float, int) and math.isfinite(v) and abs(v) <= bound for v in value)
    if action in ('angles', 'rotate') and not vector(arguments.get('angles'), 2, 36000):
        raise ValueError('INVALID_CAMERA_ANGLES')
    if action == 'pan' and not vector(arguments.get('pan'), 2, 1000):
        raise ValueError('INVALID_CAMERA_PAN')
    delta = arguments.get('delta')
    if action == 'zoom' and (type(delta) not in (float, int) or not math.isfinite(delta) or abs(delta) > 1000):
        raise ValueError('INVALID_CAMERA_DELTA')
    if action == 'mode' and arguments.get('mode') not in MODES:
        raise ValueError('INVALID_CAMERA_MODE')
    if action == 'custom' and (not vector(arguments.get('position'), 3, 10000)
        or not vector(arguments.get('center'), 3, 10000) or arguments['position'] == arguments['center']):
        raise ValueError('INVALID_CAMERA_CUSTOM')


class PreviewTools:
    @asynccontextmanager
    async def _preview_transaction(self, mutation, tool):
        receipt = None
        failure = None
        state = {'success': False}
        try:
            if mutation and getattr(self, 'mode', 'copy') == 'attached':
                receipt = await self._call('attached_edit_begin', {'tool': tool})
            yield state
        except BaseException as error:
            failure = error
            if mutation:
                self.uncertain = True
            raise
        finally:
            if receipt:
                try:
                    finished = await self._call('attached_edit_finish', {'id': receipt['id'],
                        'success': state['success'], 'uncertain': self.uncertain})
                    self.uncertain |= finished['needs_review']
                except BaseException as cleanup_error:
                    self.uncertain = True
                    if failure is None:
                        raise
                    add_exception_note(failure, 'Preview receipt cleanup failed: ' + str(cleanup_error))

    def _preview_rejected(self, result, mutation):
        if result.get('ok') is not False:
            return False
        definite = (result.get('dispatch_state') == 'prewrite_rejected'
                    and result.get('native_invocation_attempted') is False and result.get('uncertain') is False)
        if mutation and not definite:
            self.uncertain = True
        return True

    async def editor_camera(self, expected_model, action='get', *, angles=None, delta=None, pan=None,
                            mode=None, position=None, center=None):
        arguments = dict(angles=angles, delta=delta, pan=pan, mode=mode, position=position, center=center)
        validate_camera(expected_model, action, **arguments)
        async with self.lock:
            state = await self._settle()
            if state.get('model_token') != expected_model:
                raise ValueError('STALE_MODEL')
            attempted = action != 'get'
            async with self._preview_transaction(attempted, 'editor_camera') as transaction:
                result = await self._call('editor_camera' if attempted else 'get_editor_camera', dict(expected_model=expected_model, action=action, **arguments))
                if self._preview_rejected(result, attempted):
                    return result
                owner = result.get('preview_identity')
                if attempted:
                    await self._settle()
                    result = await self._call('get_editor_camera', dict(expected_model=expected_model, action='get'))
                deadline = time.monotonic() + 12
                # Named native modes may animate; never return their first angle as terminal.
                while result.get('rotating'):
                    if time.monotonic() >= deadline:
                        raise TimeoutError('CAMERA_ROTATION_UNCONFIRMED: do not retry')
                    await asyncio.sleep(.05)
                    result = await self._call('get_editor_camera', dict(expected_model=expected_model, action='get'))
                if result.get('model_token') != expected_model or result.get('preview_identity') != owner:
                    raise RuntimeError('CAMERA_MODEL_CHANGED')
                transaction['success'] = True
                return {**result, 'settled': True}

    async def face_preview(self, expected_model, name=None, weight=100, filter=None, *, reset=False, restore=False):
        if not isinstance(expected_model, str) or not expected_model:
            raise ValueError('EXPECTED_MODEL_REQUIRED')
        if (name is not None and (not isinstance(name, str) or not name or len(name) > 256)
            or filter is not None and (not isinstance(filter, str) or len(filter) > 256)
            or type(weight) not in (int, float) or not math.isfinite(weight) or not 0 <= weight <= 100
            or type(reset) is not bool or type(restore) is not bool
            or sum((name is not None, reset, restore)) > 1):
            raise ValueError('INVALID_FACE_PREVIEW_ARGUMENTS')
        async with self.lock:
            state = await self._settle()
            if state.get('model_token') != expected_model:
                raise ValueError('STALE_MODEL')
            mutation = name is not None or reset or restore
            async with self._preview_transaction(mutation, 'face_preview') as transaction:
                result = await self._call('face_preview' if mutation else 'list_face_preview', dict(expected_model=expected_model, name=name,
                    weight=weight, filter=filter, reset=reset, restore=restore))
                if self._preview_rejected(result, mutation):
                    return result
                if result.get('model_token') != expected_model:
                    raise RuntimeError('PREVIEW_MODEL_CHANGED')
                transaction['success'] = True
                return result
