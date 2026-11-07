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
        assert operation == 'editor_camera'
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
