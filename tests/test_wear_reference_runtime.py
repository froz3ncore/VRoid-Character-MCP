import asyncio,json,hashlib
from pathlib import Path
import pytest
from vroid_mcp.runtime import Runtime
from test_wear_reference import sample

@pytest.mark.parametrize('preview',[None,0,1,'true'])
def test_preview_mode_requires_an_explicit_boolean(preview):
    runtime=Runtime.__new__(Runtime)
    async def forbidden(*a):raise AssertionError('Invalid preview reached native')
    runtime._call=forbidden
    with pytest.raises(ValueError):asyncio.run(runtime.capture_wear_reference('wear','item',preview=preview))

@pytest.mark.parametrize('field,value',[('wear_token','other'),('item_id','other'),('pose_source','native_edit')])
def test_reference_identity_and_pose_mismatch_create_no_artifact(tmp_path,field,value):
    runtime=Runtime.__new__(Runtime);runtime.lab=tmp_path;runtime.lock=asyncio.Lock()
    data=sample();data.update(wear_token='wear',item_id='item',pose_source='native_preview',frame=12);data[field]=value
    async def native(operation,args):return data
    runtime._call=native
    with pytest.raises(ValueError,match='identity or pose source'):asyncio.run(runtime.capture_wear_reference('wear','item',preview=True))
    assert list(tmp_path.iterdir())==[]

@pytest.mark.parametrize('preview,pose_source',[(False,'native_edit'),(True,'native_preview')])
def test_reference_preserves_native_pose_identity_and_full_stream_artifact(tmp_path,preview,pose_source):
    runtime=Runtime.__new__(Runtime);runtime.lab=tmp_path;runtime.lock=asyncio.Lock()
    data=sample();data.update(wear_token='wear',item_id='item',pose_source=pose_source,frame=12)
    async def native(operation,args):
        assert operation=='capture_wear_reference' and args['preview'] is preview
        return data
    runtime._call=native
    result=asyncio.run(runtime.capture_wear_reference('wear','item',preview=preview))
    payload=Path(result['path']).read_bytes()
    assert result['pose_source']==pose_source and result['frame']==12
    assert hashlib.sha256(payload).hexdigest()==result['sha256']
    assert json.loads(payload)['garments'][0]['source_positions']==data['garments'][0]['source_positions']
