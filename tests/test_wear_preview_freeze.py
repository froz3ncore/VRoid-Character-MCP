import asyncio,math
import pytest
from vroid_mcp.runtime import Runtime

@pytest.mark.parametrize('seconds',[-1,61,math.nan,math.inf,True,'1',None])
def test_invalid_time_never_reaches_native(seconds):
    r=Runtime.__new__(Runtime)
    async def forbidden(*args):raise AssertionError('Invalid time reached native')
    r._call=forbidden
    with pytest.raises(ValueError):asyncio.run(r.hold_wear_preview_pose('wear','0x123',seconds))

@pytest.mark.parametrize('clip',['walk','0x',1,None])
def test_invalid_clip_never_reaches_native(clip):
    r=Runtime.__new__(Runtime)
    with pytest.raises(ValueError):asyncio.run(r.hold_wear_preview_pose('wear',clip,.3))

@pytest.mark.parametrize('field,value',[('wear_token','other'),('clip_id','0x456'),('pose_held',False),('clip_time',1.),('clip_time',math.nan)])
def test_freeze_requires_identity_and_native_time_readback(field,value):
    r=Runtime.__new__(Runtime);r.lock=asyncio.Lock()
    result={'wear_token':'wear','clip_id':'0x123','pose_held':True,'seconds':.3,'clip_time':.3,'director_paused':True}
    result[field]=value
    async def native(name,args):return result
    r._call=native
    with pytest.raises(ValueError):asyncio.run(r.hold_wear_preview_pose('wear','0x123',.3))

def test_freeze_returns_confirmed_native_settings():
    r=Runtime.__new__(Runtime);r.lock=asyncio.Lock()
    async def native(name,args):
        assert name=='hold_wear_preview_pose' and args=={'expected_wear':'wear','clip_id':'0x123','seconds':.3}
        return {'wear_token':'wear','clip_id':'0x123','pose_held':True,'seconds':.3,'clip_time':.3,'director_paused':True}
    r._call=native
    assert asyncio.run(r.hold_wear_preview_pose('wear','0x123',.3))['pose_held']
