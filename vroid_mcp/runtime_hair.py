"""Serialized aggregate hair groups and exact post-settle geometry verification."""
import math


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


class HairGroupTools:
    async def list_hair_groups(self, expected_model, category=None):
        validate(expected_model, category)
        async with self.lock:
            await self._settled_for(expected_model)
            result = await self._call('list_hair_groups', {'expected_model': expected_model, 'category': category})
            if result.get('model_token') != expected_model:
                raise RuntimeError('STALE_MODEL')
            return result

    async def _hair_group_edit(self, operation, expected_model, category, scope, **changes):
        async with self.lock:
            await self._settled_for(expected_model)
            if operation == 'set_procedural_hair':
                native = await self._call('get_procedural_hair_controls', {'expected_model': expected_model,
                    'category': category, 'scope': scope})
                if native.get('model_token') != expected_model:
                    raise RuntimeError('STALE_MODEL')
                for key, value in changes.items():
                    controls = [c for c in native['controls'] if c['key'] == key]
                    if len(controls) != 1 or not controls[0]['min'] <= value <= controls[0]['max']:
                        raise ValueError('PROCEDURAL_NATIVE_RANGE')
            dispatched = False
            result = None
            try:
                dispatched = True
                result = await self._call(operation, {'expected_model': expected_model,
                    'category': category, 'scope': scope, **changes})
                if result.get('model_token') != expected_model:
                    raise RuntimeError('MODEL_CHANGED_DURING_OPERATION')
                if result.get('uncertain') or result.get('partial') or not result.get('ok'):
                    self.uncertain = True
                    result['uncertain'] = True
                    return result
                await self._settled_for(expected_model, result.get('frame', -1))
                expected = result.pop('verification_snapshot')
                current = await self._call('get_hair_group_state', {'expected_model': expected_model,
                    'category': category, 'scope': expected['scope']})
                actual = current.get('group')
                if operation == 'set_procedural_hair':
                    matches = actual is not None and actual.get('scope') == expected['scope'] and (
                        actual.get('type') == 'procedural' and actual.get('configured') == expected.get('configured'))
                else:
                    matches = actual == expected
                if current.get('model_token') != expected_model or not matches:
                    raise RuntimeError('HAIR_SETTLED_READBACK_MISMATCH: do not retry')
                result['settled'] = True
                result['settled_readback'] = current['group']
                if operation == 'set_procedural_hair':
                    result['configured'] = current['group']['configured']
                    result['readback'] = current.get('stats', current['group'])
                return result
            except Exception as error:
                if dispatched:
                    self.uncertain = True
                if result is not None:
                    result.pop('verification_snapshot', None)
                    result.update(ok=False, uncertain=True, settled=False,
                                  partial=(result.get('command_count') or result.get('setter_count') or 0) > 0,
                                  error=str(error))
                    return result
                return {'model_token': expected_model, 'source_scope': scope, 'category': category,
                        'ok': False, 'uncertain': True, 'partial': None, 'settled': False,
                        'command_count': None, 'attempted_commands': None, 'completed_points': None,
                        'completion': 'native response unavailable; do not retry', 'error': str(error)}
            except BaseException:
                if dispatched:
                    self.uncertain = True
                raise

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
        if hair_count is not None and (type(hair_count) is not int or hair_count <= 0):
            raise ValueError('INVALID_PROCEDURAL_HAIR_COUNT')
        return await self._hair_group_edit('set_procedural_hair', expected_model, category, scope, **changes)
