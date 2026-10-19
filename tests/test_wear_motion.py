import asyncio,copy,math
import pytest
from vroid_mcp.runtime import Runtime
from vroid_mcp.wear_motion import summarize_motion

def samples():
    result=[]
    for i in range(3):
        result.append({'wear_token':'token','frame':i+10,'preview_root':'root',
            'renderers':[{'id':'dress','name':'Dress','vertices':3}],
            'bones':[{'id':'joint','name':'WM_Skirt_01','position':[i*.1,0,0],
                'local_rotation':[0,0,math.sin(i*.1),math.cos(i*.1)]}]})
    return result

def test_measured_motion_and_spring_rotation():
    r=summarize_motion(samples())
    assert r['frames_advanced'] and r['native_bone_motion_observed'] and r['spring_local_rotation_changed']
    assert r['max_world_displacement_m']==pytest.approx(.2)
    assert r['max_spring_local_rotation_change_degrees']==pytest.approx(math.degrees(.4))

def test_playing_state_and_frame_advance_do_not_invent_transform_motion():
    data=samples()
    for s in data:s['bones']=copy.deepcopy(data[0]['bones'])
    r=summarize_motion(data)
    assert r['frames_advanced'] and not r['native_bone_motion_observed'] and not r['spring_local_rotation_changed']

def test_quaternion_sign_flip_is_not_spring_motion():
    data=samples()
    for s in data:s['bones'][0]['local_rotation']=[0,0,0,-1]
    data[0]['bones'][0]['local_rotation']=[0,0,0,1]
    assert not summarize_motion(data)['spring_local_rotation_changed']

def test_capture_saves_full_transforms_but_returns_compact_result(tmp_path):
    import base64,json
    from vroid_mcp.capture_quality import quality_plan
    r=Runtime.__new__(Runtime);r.lab=tmp_path;r.lock=asyncio.Lock();frames=iter(samples())
    async def native(operation,args=None):
        if operation=='get_wear_status':return {'wear_token':'token','animation_playing':True,'animation_ready':True}
        assert operation=='wear_motion_sample'
        sample=next(frames)
        return {**sample,'bounds':{'min':[0,0,0],'max':[1,1,1]},'width':256,'height':256,
            'quality':{**quality_plan(256),'msaa_samples':4},
            'base64':base64.b64encode(b'\x89PNG\r\n\x1a\n'+b'\x00\x00\x00\x0dIHDR'+(256).to_bytes(4,'big')*2).decode()}
    r._call=native
    result=asyncio.run(r.capture_wear_motion('token',3,.1,'front',256))
    assert 'samples' not in result and len(result['images'])==3
    manifest=json.loads(__import__('pathlib').Path(result['manifest_path']).read_text(encoding='utf8'))
    assert len(manifest['samples'])==3 and manifest['samples'][0]['bones'][0]['id']=='joint'

@pytest.mark.parametrize('case',['token','root','bone','renderer','nan','rotation'])
def test_changed_or_invalid_native_motion_rejected(case):
    data=samples();last=data[-1]
    if case=='token':last['wear_token']='other'
    if case=='root':last['preview_root']='other'
    if case=='bone':last['bones'][0]['id']='other'
    if case=='renderer':last['renderers'][0]['vertices']=4
    if case=='nan':last['bones'][0]['position'][0]=float('nan')
    if case=='rotation':last['bones'][0]['local_rotation']=[0,0,0,0]
    with pytest.raises(ValueError):summarize_motion(data)

@pytest.mark.parametrize('count,interval,view,size',[(2,.25,'front',768),(17,.25,'front',768),
    (True,.25,'front',768),(3,float('nan'),'front',768),(3,True,'front',768),
    (3,.09,'front',768),(3,2.1,'front',768),(3,.25,'bad',768),(3,.25,'front',1025)])
def test_bad_motion_capture_never_calls_native(tmp_path,count,interval,view,size):
    r=Runtime.__new__(Runtime);r.lab=tmp_path
    async def forbidden(*a):raise AssertionError('Invalid capture reached native')
    r._call=forbidden
    with pytest.raises(ValueError):asyncio.run(r.capture_wear_motion('token',count,interval,view,size))
    assert list(tmp_path.iterdir())==[]

@pytest.mark.parametrize('token,playing,ready',[('stale',True,True),('token',False,False),('token',True,False)])
def test_unready_or_stale_motion_does_not_create_artifact(tmp_path,token,playing,ready):
    r=Runtime.__new__(Runtime);r.lab=tmp_path;r.lock=asyncio.Lock()
    async def native(operation,args=None):
        assert operation=='get_wear_status'
        return {'wear_token':'token','animation_playing':playing,'animation_ready':ready}
    r._call=native
    with pytest.raises(ValueError):asyncio.run(r.capture_wear_motion(token,3,.25,'front',768))
    assert list(tmp_path.iterdir())==[]
