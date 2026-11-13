"""Source FigureHeight/FigureSlender secant sizing, with native VM pair evidence.

Adapted from mcjo79/vroid-mcp 0dc7d5e mcp_server/vroid_mcp.py (MIT).
See licenses/mcjo79-0dc7d5e.txt. Weight is a BMI/waist heuristic, not mass.
"""
from .group_validation import finite


def validate_size(height, weight, variant):
    if not finite(height) or not 20 <= height <= 400:
        raise ValueError('Height must be 20..400 cm; native silhouette range can be narrower')
    if weight is not None and (not finite(weight) or not 1 <= weight <= 1000):
        raise ValueError('Weight must be 1..1000 kg; it controls a BMI waist heuristic only')
    if variant not in ('F00', 'M00'):
        raise ValueError('Variant must be F00 or M00')


def paired_control(rows, negative, positive, group):
    matches = [row for row in rows if [b.get('key') for b in row.get('semantic_bindings', [])]
               == [negative, positive] and row.get('semantic_kind') == 'combined'
               and row.get('type') in ('CombinedBoneTransformParameterViewModel', 'CombinedBlendShapeTransformParameterViewModel')
               and row.get('semantic_group') == 'TransferableGroupType.N00.Level1.' + group
               and row.get('editable') and finite(row.get('min'))
               and finite(row.get('max')) and row['min'] <= 0 <= row['max']]
    if len(matches) != 1:
        raise ValueError('SILHOUETTE_BINDING_UNAVAILABLE_OR_AMBIGUOUS: ' + positive)
    return matches[0]


async def solve(runtime, expected, height, weight, variant):
    args = {'expected_model': expected}
    status = await runtime._call('status', args)
    if status.get('model_token') != expected:
        raise ValueError('STALE_MODEL')
    if status.get('model_variant') != variant:
        raise ValueError('SILHOUETTE_VARIANT_MISMATCH')
    body = await runtime._call('list_body_params', args)
    if body.get('model_token') != expected:
        raise ValueError('STALE_MODEL')
    rows = body['parameters']
    gender = {'F00': 'Female', 'M00': 'Male'}[variant]
    # Both gender controls can be editable on either fixture. Confirm the native
    # model variant above, then bind the observed negative/positive roles.
    scale = paired_control(rows, 'Level2WholeBody_WholeBodyScaleShrink', 'Level2WholeBody_WholeBodyScaleMag', 'WholeBody')
    figure = paired_control(rows, 'Level2WholeBody_FigureHeight' + gender, 'Level2WholeBody_FigureSlender' + gender, 'WholeBody')
    waist = paired_control(rows, 'Level2Waist_WaistScaleShrink', 'Level2Waist_WaistScaleMag', 'Waist')
    selected = [scale, figure, waist]
    if len({row['id'] for row in selected}) != 3 or any(not finite(row.get('value')) for row in selected):
        raise ValueError('SILHOUETTE_SNAPSHOT_INVALID')
    initial = [{'id': row['id'], 'value': row['value']} for row in selected]
    lower, upper = max(-1., figure['min']), min(1., figure['max'])
    if not lower < 0 < upper:
        raise ValueError('SILHOUETTE_NATIVE_RANGE_UNAVAILABLE')
    bmi = weight / (height / 100.) ** 2 if weight is not None else None
    coefficient = max(-1., min(1., (bmi - 21.) / 8.)) if bmi is not None else None
    if coefficient is not None and not waist['min'] <= coefficient <= waist['max']:
        raise ValueError('BMI_WAIST_OUTSIDE_NATIVE_RANGE')
    samples, written, dispatched = [], [], False

    async def apply(changes):
        nonlocal dispatched
        dispatched = True
        runtime.body_edited_tokens.add(expected)
        result = await runtime._call('set_body_params', {**args, 'changes': changes})
        await runtime._settled_for(expected, result.get('frame', -1))
        if not result.get('ok'):
            raise RuntimeError('SILHOUETTE_PARTIAL_WRITE: ' + str(result))
        written.extend(changes)

    async def measure():
        result = await runtime._call('get_height', args)
        value = result.get('live_centimeters')
        if not finite(value):
            raise RuntimeError('SILHOUETTE_HEIGHT_INVALID')
        return value

    try:
        await apply([{'id': scale['id'], 'value': 0.}, {'id': figure['id'], 'value': 0.}])
        x, measured = 0., await measure()
        for _ in range(10):
            samples.append({'figure': x, 'centimeters': measured})
            if abs(measured - height) <= .05:
                if coefficient is not None:
                    await apply([{'id': waist['id'], 'value': coefficient}])
                    measured = await measure()
                if abs(measured - height) > .05:
                    raise ValueError('SILHOUETTE_WAIST_CHANGED_HEIGHT')
                actual = await runtime._call('list_body_params', args)
                values = {row['id']:row['value'] for row in actual['parameters']}
                wanted = {scale['id']:0.,figure['id']:x,waist['id']:coefficient if coefficient is not None else waist['value']}
                if actual.get('model_token') != expected or any(not finite(values.get(id)) or abs(values[id]-value)>1e-5 for id,value in wanted.items()):
                    raise RuntimeError('SILHOUETTE_CONTROL_READBACK_MISMATCH')
                return dict(ok=True, model_token=expected, target_cm=height, measured_cm=measured,
                    samples=samples, written=written, readback=[row for row in actual['parameters']
                    if row['id'] in {r['id'] for r in selected}], variant=variant,
                    variant_evidence='native model variant and exact gender-specific negative/positive binding',
                    weight_is_heuristic=weight is not None, bmi=bmi, waist_coefficient=coefficient,
                    weight_convention='source BMI waist heuristic; not measured body mass',
                    measurement='VRoid native GetBodyHeight (live)', settled=True)
            if len(samples) == 1:
                next_x = min(upper, .3) if measured < height else max(lower, -.3)
            else:
                previous = samples[-2]
                span = x - previous['figure']
                slope = (measured - previous['centimeters']) / span if span else 0
                if abs(slope) < 1e-7:
                    break
                next_x = max(lower, min(upper, x + (height - measured) / slope))
            if abs(next_x - x) < 1e-7:
                break
            x = next_x
            await apply([{'id': figure['id'], 'value': x}])
            measured = await measure()
        raise ValueError('SILHOUETTE_DID_NOT_CONVERGE')
    except BaseException as error:
        # Cancellation/native uncertainty means a dispatched call may still run.
        # Never issue a restoration concurrently with unknown work.
        import asyncio
        if isinstance(error, asyncio.CancelledError) or runtime.uncertain:
            if dispatched:
                runtime.uncertain = True
            raise
        try:
            await apply(initial)
            actual = await runtime._call('list_body_params', args)
            values = {row['id']: row['value'] for row in actual['parameters']}
            restored = all(finite(values.get(row['id'])) and abs(values[row['id']] - row['value']) < 1e-5 for row in initial)
            if not restored:
                raise RuntimeError('SILHOUETTE_RESTORATION_READBACK_MISMATCH')
        except BaseException as restore_error:
            runtime.uncertain = True
            return dict(ok=False, partial=True, uncertain=True, error=str(error),
                        restoration_error=str(restore_error), samples=samples, written=written)
        return dict(ok=False, partial=False, restored=True, error=str(error), samples=samples,
                    written=written, restoration_readback=actual, model_token=expected)
