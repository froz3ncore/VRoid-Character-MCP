"""Serialized aggregate hair groups and exact post-settle geometry verification."""
import math
import struct


CATEGORIES = ('HairFront', 'HairBack', 'AllHair', 'HairTied', 'HairSideburns', 'HairAhoge', 'HairHanege')


def validate(expected_model, category=None, scope=None, scoped=False):
    if not isinstance(expected_model, str) or not expected_model:
        raise ValueError('EXPECTED_MODEL_REQUIRED')
    if (scoped or category is not None) and category not in CATEGORIES:
        raise ValueError('HAIR_PART_CATEGORY_REQUIRED')
    if scoped and (not isinstance(scope, str) or not scope):
        raise ValueError('HAIR_GROUP_SCOPE_REQUIRED')


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def native_float(value):
    try:
        converted = struct.unpack('=f', struct.pack('=f', value))[0]
    except (OverflowError, struct.error):
        raise ValueError('INVALID_PROCEDURAL_LENGTH: outside native Single range') from None
    if not math.isfinite(converted):
        raise ValueError('INVALID_PROCEDURAL_LENGTH')
    return converted


class HairGroupTools:
    async def list_hair_groups(self, expected_model, category=None):
        validate(expected_model, category)
        async with self.lock:
            await self._settled_for(expected_model)
            result = await self._call('list_hair_groups', {'expected_model': expected_model, 'category': category})
            if result.get('model_token') != expected_model:
                raise RuntimeError('STALE_MODEL')
            return result

    async def _hair_step(self, operation, expected_model, category, scope, **changes):
        result = None
        try:
            result = await self._call(operation, {'expected_model': expected_model,
                'category': category, 'scope': scope, **changes})
            if result.get('model_token') != expected_model:
                raise RuntimeError('MODEL_CHANGED_DURING_OPERATION')
            if result.get('ok') is False:
                definite = (result.get('dispatch_state') == 'prewrite_rejected'
                    and result.get('native_invocation_attempted') is False
                    and not result.get('uncertain')
                    and not result.get('partial')
                    and not any(result.get(key) for key in ('command_count', 'attempted_commands',
                                                            'setter_count', 'attempted_setters')))
                if getattr(self, 'mode', 'copy') == 'attached':
                    definite = definite and result.get('attached_prewrite_verified') is True
                self.uncertain |= not definite
                result['uncertain'] = not definite
                return result
            if result.get('uncertain') or result.get('partial'):
                self.uncertain = True
                return result
            await self._settled_for(expected_model, result.get('frame', -1))
            procedural = operation == 'set_procedural_hair'
            expected = result.get('verification_identity') if procedural else result.get('verification_snapshot')
            if expected is None:
                raise RuntimeError('HAIR_VERIFICATION_RECEIPT_MISSING')
            current = await self._call('get_hair_group_state', {'expected_model': expected_model,
                'category': category, 'scope': expected['scope']})
            actual = current.get('group')
            if procedural:
                matches = actual is not None and actual.get('type') == 'procedural' and all(
                    actual.get(key) == value for key, value in expected.items()
                    if key in ('scope', 'transferable_id', 'group_id', 'owner')) and (
                    actual.get('configured') == result['requested_configured'])
            else:
                matches = actual == expected
            if current.get('model_token') != expected_model or not matches:
                raise RuntimeError('HAIR_SETTLED_READBACK_MISMATCH: do not retry')
            result.pop('verification_snapshot', None)
            result['settled'] = True
            result['verification_pending'] = False
            result['verification_stage'] = 'settled'
            result['settled_readback'] = actual
            if procedural:
                result['configured'] = actual['configured']
                result['readback'] = current.get('stats', actual)
            return result
        except Exception as error:
            self.uncertain = True
            if result is not None:
                result.pop('verification_snapshot', None)
                result['immediate_verified_points'] = result.get('verified_points', [])
                result['immediate_affected_points'] = result.get('affected_points', 0)
                result.update(ok=False, uncertain=True, settled=False, verification_stage='unconfirmed',
                    verified_points=[], changed_points=[], affected_points=0, affected_strands=0,
                    partial=(result.get('command_count') or result.get('setter_count') or 0) > 0,
                    error=str(error))
                return result
            return {'model_token': expected_model, 'source_scope': scope, 'category': category,
                'ok': False, 'uncertain': True, 'partial': None, 'settled': False,
                'dispatch_state': 'response_lost', 'native_invocation_attempted': None,
                'command_count': None, 'attempted_commands': None, 'completed_points': None,
                'verified_points': None, 'completion': 'native response unavailable; do not retry', 'error': str(error)}
        except BaseException:
            self.uncertain = True
            raise

    async def _hair_group_edit(self, operation, expected_model, category, scope, **changes):
        async with self.lock:
            await self._settled_for(expected_model)
            return await self._hair_step(operation, expected_model, category, scope, **changes)

    async def scale_brush_hair(self, expected_model, category, scope, factor):
        validate(expected_model, category, scope, True)
        if not finite(factor) or not 0 < factor <= 10:
            raise ValueError('INVALID_FACTOR: finite (0,10] required')
        return await self._hair_group_edit('scale_brush_hair', expected_model, category, scope, factor=factor)

    async def clone_brush_hair(self, expected_model, category, scope, offset):
        validate(expected_model, category, scope, True)
        if not isinstance(offset, list) or len(offset) != 3 or not all(finite(v) for v in offset):
            raise ValueError('INVALID_OFFSET: finite native XYZ required')
        return await self._hair_group_edit('clone_brush_hair', expected_model, category, scope, offset=offset)

    async def set_procedural_hair(self, expected_model, category, scope, length=None, hair_count=None):
        validate(expected_model, category, scope, True)
        changes = {k: v for k, v in (('length', length), ('hair_count', hair_count)) if v is not None}
        if not changes:
            raise ValueError('PROCEDURAL_CHANGES_REQUIRED')
        if length is not None and not finite(length):
            raise ValueError('INVALID_PROCEDURAL_LENGTH')
        if length is not None:
            changes['length'] = native_float(length)
        if hair_count is not None and (type(hair_count) is not int or hair_count <= 0):
            raise ValueError('INVALID_PROCEDURAL_HAIR_COUNT')
        async with self.lock:
            await self._settled_for(expected_model)
            native = await self._call('get_procedural_hair_controls', {'expected_model': expected_model,
                'category': category, 'scope': scope})
            if native.get('model_token') != expected_model:
                raise RuntimeError('STALE_MODEL')
            for key, value in changes.items():
                controls = [c for c in native['controls'] if c['key'] == key]
                if len(controls) != 1 or not controls[0]['min'] <= value <= controls[0]['max']:
                    raise ValueError('PROCEDURAL_NATIVE_RANGE')
            steps = []
            for key, value in changes.items():
                step = await self._hair_step('set_procedural_hair', expected_model, category, scope,
                    expected_identity=native.get('identity'), **{key: value})
                steps.append(step)
                if not step.get('ok'):
                    if len(steps) > 1:
                        self.uncertain = True
                        step.update(partial=True, uncertain=True)
                    break
            last = dict(steps[-1])
            last.update(steps=steps,
                confirmed_setter_count=sum(s.get('setter_count') or 0 for s in steps),
                explicit_command_count=sum(s.get('command_count') or 0 for s in steps),history_entry_count=None)
            for counter in ('setter_count', 'attempted_setters', 'command_count', 'attempted_commands'):
                last[counter] = None if any(s.get(counter) is None for s in steps) else sum(s[counter] for s in steps)
            return last
