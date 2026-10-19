"""Invalid review requests must never reach native code or create artifacts."""
import asyncio
import pytest
from vroid_mcp.runtime import Runtime

@pytest.mark.parametrize('views,size',[([],768),(['front','front'],768),(['../outside'],768),
    (['photo'],768),(['front'],255),(['front'],2049),(['front'],True)])
def test_wear_capture_rejects_before_native(tmp_path,views,size):
    runtime=Runtime.__new__(Runtime);runtime.lab=tmp_path
    async def must_not_call(*args,**kwargs):raise AssertionError('Native call on invalid request')
    runtime._call=must_not_call
    with pytest.raises(ValueError):asyncio.run(runtime.capture_wear_review('token',views,size))
    assert list(tmp_path.iterdir())==[]

def test_stale_native_guard_does_not_create_review_folder(tmp_path):
    runtime=Runtime.__new__(Runtime);runtime.lab=tmp_path;runtime.lock=asyncio.Lock()
    async def native(name,args):
        assert name=='get_wear_snapshot' and args=={'expected_wear':'stale'}
        raise RuntimeError('STALE_WEAR')
    runtime._call=native
    with pytest.raises(RuntimeError,match='STALE_WEAR'):
        asyncio.run(runtime.capture_wear_review('stale',['front'],768))
    assert list(tmp_path.iterdir())==[]
