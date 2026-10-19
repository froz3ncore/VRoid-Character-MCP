import asyncio,math
import pytest
from vroid_mcp.runtime import Runtime

@pytest.mark.parametrize('upper,foot',[(True,8),(3,math.nan),(7,8),(3,13),(-1,8),(5,4),(None,8)])
def test_invalid_angles_do_not_reach_native(upper,foot):
    r=Runtime.__new__(Runtime)
    with pytest.raises(ValueError):asyncio.run(r.pose_wear_preview_legs('wear','0x123',0,upper,foot))

@pytest.mark.parametrize('field,value',[('wear_token','other'),('clip_id','0x456'),('director_paused',False),('session_only',False),('clip_time',.5),('clip_time',math.nan)])
def test_pose_rejects_wrong_native_identity_or_time(field,value):
    r=Runtime.__new__(Runtime);r.lock=asyncio.Lock()
    result=dict(wear_token='wear',clip_id='0x123',director_paused=True,session_only=True,clip_time=0)
    result[field]=value
    async def native(*args):return result
    r._call=native
    with pytest.raises(ValueError):asyncio.run(r.pose_wear_preview_legs('wear','0x123',0,3,8))
