import asyncio
import pytest
from vroid_mcp.runtime import Runtime

@pytest.mark.parametrize('clip_id',['walk_00','../clip','0x','0xg1',123,True,''])
def test_invalid_clip_identity_never_reaches_native(clip_id):
    r=Runtime.__new__(Runtime)
    async def forbidden(*args):raise AssertionError('Invalid clip reached native')
    r._call=forbidden
    with pytest.raises(ValueError):asyncio.run(r.select_wear_preview_clip('wear',clip_id))

@pytest.mark.parametrize('clip_id',[None,'0x123abc'])
def test_selector_preserves_fresh_identity_and_default_restore(clip_id):
    r=Runtime.__new__(Runtime);r.lock=asyncio.Lock()
    async def native(operation,args):
        assert operation=='select_wear_preview_clip' and args=={'expected_wear':'wear','clip_id':clip_id}
        return {'wear_token':'wear','selected_preview_clip':clip_id}
    r._call=native
    assert asyncio.run(r.select_wear_preview_clip('wear',clip_id))['wear_token']=='wear'
