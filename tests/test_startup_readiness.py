import asyncio
from types import SimpleNamespace

import frida
import pytest

from vroid_mcp import bridge


def runtime():
    return SimpleNamespace(lock=asyncio.Lock(), script=SimpleNamespace(exports_sync=SimpleNamespace(
        health=lambda: {'ready': True, 'error': None, 'native_png_decoder_ready': True})))


def test_first_frame_wait_retries_only_status_and_creates_model_once(monkeypatch):
    calls, waits = [], []
    failures = iter(['MAIN_THREAD_TIMEOUT: not executed', 'BRIDGE_NOT_READY', None])
    async def call(subject, operation, args=None):
        calls.append(operation)
        if operation == 'status':
            failure = next(failures)
            if failure: raise frida.RPCException(failure)
            return {'model_ready': False, 'reason': 'NO_MODEL'}
        return {'requested': True}
    async def settled(subject): return {'model_ready': True}
    monkeypatch.setattr(bridge, 'call', call)
    monkeypatch.setattr(bridge, 'settle', settled)
    monkeypatch.setattr(bridge, 'record', lambda subject, event: waits.append(event))
    assert asyncio.run(bridge.initialize(runtime())) == {'model_ready': True}
    assert calls == ['status', 'status', 'status', 'new_model']
    assert len(waits) == 2


def test_native_error_other_than_undispatched_readiness_is_not_retried(monkeypatch):
    calls = []
    async def call(subject, operation, args=None):
        calls.append(operation)
        raise frida.RPCException('NATIVE_PNG_DECODE_FAILED')
    monkeypatch.setattr(bridge, 'call', call)
    with pytest.raises(frida.RPCException, match='NATIVE_PNG_DECODE_FAILED'):
        asyncio.run(bridge.initialize(runtime()))
    assert calls == ['status']
