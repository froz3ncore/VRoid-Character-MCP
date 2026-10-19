import asyncio
import pytest
from vroid_mcp.capture_views import REGIONAL_VIEWS,validate_wear_views,review_reference
from vroid_mcp.runtime import Runtime,validate_capture

def test_view_names_are_portable_and_all_paths_accept_them():
    assert len(REGIONAL_VIEWS)==36
    for view in REGIONAL_VIEWS:
        assert ':' not in view and '/' not in view
        validate_capture([view],256);validate_wear_views([view])
    validate_wear_views(['body_front','face_front','head_front','upper_front','legs_front','feet_front'])

@pytest.mark.parametrize('views',[[],['face:left'],['face_left']*2,['body_front','face_front','head_front','upper_front','legs_front','feet_front','front']])
def test_invalid_views_fail_before_native_or_artifacts(tmp_path,views):
    runtime=Runtime.__new__(Runtime);runtime.lab=tmp_path
    with pytest.raises(ValueError):asyncio.run(runtime.capture_wear_review('token',views,512))
    assert not list(tmp_path.iterdir())

def test_baseline_locks_only_same_live_model_root():
    current={'model_token':'a','root_id':'b','bounds':{'min':[0,0,0],'max':[1,2,1]},'reference_frame':200}
    old={**current,'bounds':{'min':[0,0,0],'max':[1,1,1]},'reference_frame':100}
    ref,mode=review_reference(current,{'framing_reference':old})
    assert mode=='baseline_locked' and ref['bounds']==old['bounds'] and ref['reference_frame']==100
    for key in ['model_token','root_id']:
        changed={**old,key:'changed'}
        assert review_reference(current,{'framing_reference':changed})==(current,'current_model')
    assert current['reference_frame']==200

def test_capture_propagates_reference_and_metadata():
    runtime=Runtime.__new__(Runtime)
    from test_capture_quality import native_result
    async def call(operation,args):
        assert operation=='screenshot' and args['framing_reference']=={'id':'locked'}
        return {**native_result(),'framing':{'camera_readback_verified':True}}
    runtime._call=call;quality={};framing={}
    asyncio.run(runtime._capture('face_left','token',256,'high',quality,framing,{'id':'locked'}))
    assert framing['camera_readback_verified'] and quality['msaa_samples']==4
