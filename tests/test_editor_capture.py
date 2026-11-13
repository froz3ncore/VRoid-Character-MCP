import asyncio
import base64

import pytest

from vroid_mcp.capture_quality import quality_plan, decode_capture
from vroid_mcp.runtime import Runtime


@pytest.mark.parametrize('width,height', [(640, 1024), (1024, 640)])
def test_rectangular_plan_and_png(width, height):
    plan = quality_plan(512, 'balanced', width=width, height=height, msaa=2, ssaa=3)
    assert (plan['render_width'], plan['render_height']) == (width * 3, height * 3)
    png = b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\x0dIHDR' + width.to_bytes(4, 'big') + height.to_bytes(4, 'big')
    result = dict(width=width, height=height, quality={**plan, 'msaa_samples': 1}, base64=base64.b64encode(png).decode())
    assert decode_capture(result, 512, 'balanced', width=width, height=height, msaa=2, ssaa=3) == png
    result['height'] = width
    with pytest.raises(ValueError):
        decode_capture(result, 512, 'balanced', width=width, height=height, msaa=2, ssaa=3)


@pytest.mark.parametrize('args', [dict(width=640), dict(width=255, height=1024), dict(width=True, height=1024),
    dict(msaa=8), dict(msaa=True), dict(ssaa=4), dict(ssaa=float('nan'))])
def test_invalid_overrides_before_native(args):
    with pytest.raises(ValueError):
        quality_plan(512, 'balanced', **args)


def test_budget_preserves_aspect():
    p = quality_plan(512, 'high', width=2048, height=1536, ssaa=3)
    assert p['render_width'] * p['render_height'] <= 8_000_000
    assert abs(p['effective_scale_x'] - p['effective_scale_y']) < .001
    assert p['clamped']


@pytest.mark.parametrize('kwargs', [dict(width=640, height=1024), dict(msaa=2), dict(ssaa=1), dict(size=768), dict(quality='high')])
def test_app_frame_rejects_overrides_without_native(kwargs):
    r = Runtime.__new__(Runtime)
    with pytest.raises(ValueError, match='APP_FRAME'):
        asyncio.run(r.screenshot('current_editor', 'token', clean=False, **kwargs))


@pytest.mark.parametrize('action,kwargs', [('bad', {}), ('rotate', {'angles': [float('nan'), 0]}),
    ('zoom', {'delta': True}), ('pan', {'pan': [0, 1e10]}), ('mode', {'mode': 'bad'}),
    ('custom', {'position': [0, 0, 1]}), ('get', {'delta': 1})])
def test_invalid_camera_arguments_precede_lock(action, kwargs):
    r = Runtime.__new__(Runtime)
    with pytest.raises(ValueError):
        asyncio.run(r.editor_camera('token', action, **kwargs))


def test_face_weight_validation_precedes_lock():
    r = Runtime.__new__(Runtime)
    for weight in [True, float('nan'), -1, 101]:
        with pytest.raises(ValueError):
            asyncio.run(r.face_preview('token', 'Smile', weight))


def png(width, height):
    return base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\x0dIHDR' + width.to_bytes(4, 'big') + height.to_bytes(4, 'big')).decode()


def runtime_double(handler):
    r = Runtime.__new__(Runtime)
    r.lock, r.uncertain = asyncio.Lock(), False
    r.calls = []
    async def settled(*args):
        return {'model_token': 'token'}
    async def call(operation, args=None):
        assert r.lock.locked()
        r.calls.append((operation, args))
        return handler(operation, args)
    r._call, r._settle = call, settled
    return r


def test_application_frame_polls_without_preparation_and_reports_native_size():
    polls = 0
    def handler(operation, args):
        nonlocal polls
        if operation == 'start_app_frame':
            return {'id': 4}
        assert operation == 'poll_app_frame' and args == {'id': 4}
        polls += 1
        return {'completed': polls == 2, 'result': {'model_token': 'token', 'width': 1234, 'height': 734,
            'provenance': 'unity_application_frame', 'phase': 'UnityEngine.Awaitable.OnEndOfFrame.onLeave',
            'quality': {'msaa_samples': 2}, 'base64': png(1234, 734)}}
    r = runtime_double(handler)
    data, metadata = asyncio.run(r.screenshot_with_metadata('current_editor', 'token', clean=False))
    assert data.startswith(b'\x89PNG') and metadata['width'] == 1234 and 'base64' not in metadata
    assert [operation for operation, args in r.calls] == ['start_app_frame', 'poll_app_frame', 'poll_app_frame']


@pytest.mark.parametrize('clean,view,overrides', [(True, 'front', {'width': 640, 'height': 1024, 'msaa': 2, 'ssaa': 3}),
    (True, 'current_editor', {})])
def test_new_clean_paths_do_not_change_ui_and_keep_metadata(clean, view, overrides):
    plan = quality_plan(512, 'balanced', **overrides)
    def handler(operation, args):
        assert operation == 'screenshot' and args['view'] == view
        return {'model_token': 'token', 'width': plan['output_width'], 'height': plan['output_height'],
            'quality': {**plan, 'msaa_samples': 1}, 'base64': png(plan['output_width'], plan['output_height']),
            'provenance': 'clean_current_editor_render' if view == 'current_editor' else 'clean_fixed_camera_render'}
    r = runtime_double(handler)
    _, metadata = asyncio.run(r.screenshot_with_metadata(view, 'token', **overrides))
    assert len(r.calls) == 1 and metadata['quality']['msaa_samples'] == 1


def test_clean_failure_does_not_fall_back_to_application_frame():
    def handler(operation, args):
        assert operation == 'screenshot'
        raise RuntimeError('READ_FAILED')
    r = runtime_double(handler)
    with pytest.raises(RuntimeError, match='READ_FAILED'):
        asyncio.run(r.screenshot('current_editor', 'token'))
    assert len(r.calls) == 1


def test_camera_mode_polls_terminal_state_without_replaying_mutation():
    def handler(operation, args):
        assert operation in ('editor_camera', 'get_editor_camera')
        return {'model_token': 'token', 'angles': [45, 0], 'rotating': args['action'] == 'mode'}
    r = runtime_double(handler)
    result = asyncio.run(r.editor_camera('token', 'mode', mode='Right'))
    assert result['settled'] and [args['action'] for _, args in r.calls] == ['mode', 'get']


@pytest.mark.parametrize('tool', ['camera', 'face', 'app'])
def test_preview_native_response_loss_marks_uncertain_without_retry(tool):
    def handler(operation, args):
        if operation == 'start_app_frame':
            return {'id': 3}
        raise RuntimeError('RESPONSE_LOST')
    r = runtime_double(handler)
    with pytest.raises(RuntimeError, match='RESPONSE_LOST'):
        if tool == 'camera':
            asyncio.run(r.editor_camera('token', 'zoom', delta=1))
        elif tool == 'face':
            asyncio.run(r.face_preview('token', 'Smile'))
        else:
            asyncio.run(r.screenshot('current_editor', 'token', clean=False))
    assert r.uncertain
    assert len(r.calls) == (2 if tool == 'app' else 1)


@pytest.mark.parametrize('mode', ['copy', 'attached'])
def test_known_preview_prewrite_does_not_poison_corrected_request(mode):
    def handler(operation, args):
        if operation.startswith('attached_'):
            return {'id': 'receipt'} if operation == 'attached_edit_begin' else {'needs_review': False}
        if args.get('name') == 'ile':
            return {'model_token': 'token', 'ok': False, 'uncertain': False, 'dispatch_state': 'prewrite_rejected',
                    'native_invocation_attempted': False, 'error': 'AMBIGUOUS_BLENDSHAPE_SUFFIX'}
        return {'model_token': 'token', 'ok': True}
    r = runtime_double(handler);r.mode = mode
    rejected = asyncio.run(r.face_preview('token', 'ile'))
    assert not rejected['ok'] and not r.uncertain
    assert asyncio.run(r.face_preview('token', 'Smile'))['ok'] and not r.uncertain


@pytest.mark.parametrize('tool', ['camera', 'face'])
def test_readonly_preview_errors_do_not_create_receipts_or_uncertainty(tool):
    def handler(operation, args):
        assert not operation.startswith('attached_')
        raise RuntimeError('NATIVE_READ_FAILED')
    r = runtime_double(handler);r.mode = 'attached'
    with pytest.raises(RuntimeError, match='NATIVE_READ_FAILED'):
        asyncio.run(r.editor_camera('token') if tool == 'camera' else r.face_preview('token'))
    assert not r.uncertain


@pytest.mark.parametrize('metadata', [False, True])
def test_default_capture_never_destructively_prepares_ui(metadata):
    def handler(operation, args):
        assert operation != 'prepare_capture', 'selection clearing cannot be exactly undone'
        raise RuntimeError('CAPTURE_FAILED')
    r = runtime_double(handler)
    with pytest.raises(RuntimeError, match='CAPTURE_FAILED'):
        asyncio.run(r.screenshot_with_metadata('front', 'token') if metadata else r.screenshot('front', 'token'))


@pytest.mark.parametrize('tool', ['default', 'metadata', 'review'])
@pytest.mark.parametrize('failure', ['settle', 'native', 'png', 'model'])
def test_clean_capture_failures_never_clear_or_restore_ui_on_another_model(tool, failure):
    def handler(operation, args):
        assert operation == 'screenshot'
        if failure == 'native':
            raise RuntimeError('NATIVE_FAILED_AFTER_GUIDE_ISOLATION')
        return {'model_token': 'replacement' if failure == 'model' else 'token', 'width': 512, 'height': 512,
                'quality': {**quality_plan(512), 'msaa_samples': 4}, 'base64': png(256 if failure == 'png' else 512, 512)}
    r = runtime_double(handler)
    if failure == 'settle':
        async def failed(*args):
            raise RuntimeError('SETTLE_FAILED')
        r._settle = failed
    with pytest.raises((RuntimeError, ValueError)):
        if tool == 'review':
            asyncio.run(r.capture_review('token', ['front'], size=512))
        elif tool == 'metadata':
            asyncio.run(r.screenshot_with_metadata('front', 'token'))
        else:
            asyncio.run(r.screenshot('front', 'token'))
    assert all(operation == 'screenshot' for operation, args in r.calls)


def test_native_capture_cleanup_uncertainty_is_retained_without_retry():
    def handler(operation, args):
        raise RuntimeError('CAPTURE_CLEANUP_FAILED: camera rollback unconfirmed')
    r = runtime_double(handler)
    with pytest.raises(RuntimeError, match='CAPTURE_CLEANUP_FAILED'):
        asyncio.run(r.screenshot('photo', 'token'))
    assert r.uncertain and len(r.calls) == 1
