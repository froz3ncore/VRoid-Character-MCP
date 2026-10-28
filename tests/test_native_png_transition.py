import asyncio
from types import SimpleNamespace

import pytest

from vroid_mcp.runtime import Runtime
from vroid_mcp import edit_sequence


@pytest.mark.parametrize('op', ['open_texture_editor', 'close_texture_editor', 'open_wear_project', 'save_as'])
def test_transition_waits_for_png_callbacks_before_dispatch(tmp_path, op):
    subject = Runtime(tmp_path)
    subject.native_png_decoder_ready = True
    subject.texture_editor_entered = True
    subject.body_edited_tokens.add('live')
    calls = []
    def native(name, args):
        calls.append(name)
        if name == 'native_png_status':
            return {'installed': True, 'pending': 1 if len(calls) == 1 else 0, 'fatal': None}
        return {}
    subject.script = SimpleNamespace(exports_sync=SimpleNamespace(call=native))
    asyncio.run(subject._call(op, {'expected_model': 'live'}))
    assert calls == ['native_png_status', 'native_png_status', op]


@pytest.mark.parametrize('state', [{'installed': False}, {'installed': True, 'fatal': 'callback failed'}])
def test_failed_png_pipeline_never_enters_transition(tmp_path, state):
    subject = Runtime(tmp_path)
    subject.native_png_decoder_ready = True
    calls = []
    def native(op, args): calls.append(op); return state
    subject.script = SimpleNamespace(exports_sync=SimpleNamespace(call=native))
    with pytest.raises(RuntimeError, match='NATIVE_PNG_DECODER_UNAVAILABLE'):
        asyncio.run(subject._call('open_wear_project'))
    assert calls == ['native_png_status'] and subject.uncertain


def test_unverified_and_attached_sessions_keep_existing_guard(tmp_path):
    subject = Runtime(tmp_path)
    subject.body_edited_tokens.add('live')
    with pytest.raises(RuntimeError, match='REOPEN_REQUIRED'):
        edit_sequence.before_call(subject, 'open_texture_editor', {'expected_model': 'live'})
    subject.native_png_decoder_ready = True
    subject.mode = 'attached'
    with pytest.raises(RuntimeError, match='REOPEN_REQUIRED'):
        edit_sequence.before_call(subject, 'open_texture_editor', {'expected_model': 'live'})
