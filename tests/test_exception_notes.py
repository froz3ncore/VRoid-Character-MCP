import asyncio

import pytest

from vroid_mcp.runtime_preview import PreviewTools


@pytest.mark.parametrize('exception_type', [ValueError, asyncio.CancelledError])
def test_preview_cleanup_preserves_primary_exception_and_uncertainty(exception_type):
    preview = PreviewTools()
    preview.mode = 'attached'
    preview.uncertain = False
    primary = exception_type('PRIMARY_PREVIEW_FAILURE')
    primary.__notes__ = ['existing note']
    calls = []

    async def native(operation, arguments):
        calls.append(operation)
        if operation == 'attached_edit_begin':
            return {'id': 'receipt'}
        raise RuntimeError('SECONDARY_RECEIPT_FAILURE')

    preview._call = native

    async def scenario():
        # Check inside the task: Python 3.10 asyncio.run recreates cancellation.
        with pytest.raises(exception_type) as raised:
            async with preview._preview_transaction(True, 'editor_camera'):
                raise primary
        assert raised.value is primary

    asyncio.run(scenario())
    assert str(primary) == 'PRIMARY_PREVIEW_FAILURE'
    assert primary.__notes__ == [
        'existing note', 'Preview receipt cleanup failed: SECONDARY_RECEIPT_FAILURE']
    assert preview.uncertain
    assert calls == ['attached_edit_begin', 'attached_edit_finish']


def test_note_fallback_retains_order_without_changing_exception():
    from vroid_mcp.exception_notes import add_exception_note

    class LegacyError(ValueError):
        add_note = None

    error = LegacyError('PRIMARY_FAILURE')
    add_exception_note(error, 'first')
    notes = error.__notes__
    add_exception_note(error, 'second')
    assert error.__notes__ is notes
    assert notes == ['first', 'second']
    assert error.args == ('PRIMARY_FAILURE',)
    assert str(error) == 'PRIMARY_FAILURE'


def test_note_helper_uses_available_add_note():
    from vroid_mcp.exception_notes import add_exception_note

    class NotedError(ValueError):
        def add_note(self, note):
            self.received = note

    error = NotedError('PRIMARY_FAILURE')
    add_exception_note(error, 'cleanup failed')
    assert error.received == 'cleanup failed'
