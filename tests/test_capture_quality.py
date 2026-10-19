import asyncio,base64,json
import pytest
from vroid_mcp.capture_quality import quality_plan,decode_capture
from vroid_mcp.runtime import Runtime

@pytest.mark.parametrize('size,quality,side,samples',[(256,'legacy',256,1),(768,'balanced',768,4),(1024,'high',2048,4),(2048,'high',2828,4)])
def test_gpu_budget_preserves_output(size,quality,side,samples):
    p=quality_plan(size,quality)
    assert p['render_size']==side and p['render_size']**2<=8_000_000
    assert p['requested_msaa']==samples and p['output_size']==size
    assert p['clamped']==(size==2048 and quality=='high')

@pytest.mark.parametrize('size,quality',[(True,'high'),(255,'high'),(2049,'high'),(512.0,'high'),(512,'ultra'),(512,None)])
def test_invalid_plan(size,quality):
    with pytest.raises(ValueError):quality_plan(size,quality)

def native_result():
    return {'width':256,'height':256,'quality':{**quality_plan(256,'high'),'msaa_samples':4},
            'base64':base64.b64encode(b'\x89PNG\r\n\x1a\n'+b'\x00\x00\x00\x0dIHDR'+(256).to_bytes(4,'big')*2).decode()}

@pytest.mark.parametrize('change',['png','dimensions','budget','samples','bool_samples'])
def test_native_result_must_match_request(change):
    r=native_result()
    if change=='png':r['base64']=base64.b64encode(b'\x89PNG\r\n\x1a\n').decode()
    elif change=='dimensions':r['width']=512
    elif change=='budget':r['quality']['render_size']=8192
    elif change=='samples':r['quality']['msaa_samples']=8
    else:r['quality']['msaa_samples']=True
    with pytest.raises(ValueError):decode_capture(r,256,'high')

def test_gpu_downgrade_is_accepted_as_actual_samples():
    r=native_result();r['quality']['msaa_samples']=2
    assert decode_capture(r,256,'high').startswith(b'\x89PNG')

def test_old_baseline_is_legacy_and_different_quality_rejected_before_native(tmp_path):
    folder=tmp_path/'reviews'/('a'*32);folder.mkdir(parents=True)
    (folder/'review.json').write_text(json.dumps({'views':['front'],'size':512}),encoding='utf8')
    r=Runtime.__new__(Runtime);r.lab=tmp_path
    with pytest.raises(ValueError,match='quality must match'):
        asyncio.run(r.capture_review('token',['front'],512,baseline_id='a'*32))

@pytest.mark.parametrize('tool',['screenshot','review','wear','motion'])
def test_invalid_quality_never_reaches_native_or_creates_artifacts(tmp_path,tool):
    r=Runtime.__new__(Runtime);r.lab=tmp_path
    async def run():
        if tool=='screenshot':return await r.screenshot('front','token',512,'invalid')
        if tool=='review':return await r.capture_review('token',['front'],quality='invalid')
        if tool=='wear':return await r.capture_wear_review('token',['front'],768,'invalid')
        return await r.capture_wear_motion('token',3,.1,'front',512,'invalid')
    with pytest.raises(ValueError):asyncio.run(run())
    assert not list(tmp_path.iterdir())
