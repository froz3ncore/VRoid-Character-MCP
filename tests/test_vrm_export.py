import asyncio,json,struct
from pathlib import Path
import pytest
from vroid_mcp.runtime import Runtime
from vroid_mcp.vrm_export import export_metadata,validate_vrm


def document():
    return {'asset':{'version':'2.0'},'buffers':[{'byteLength':4}],
        'bufferViews':[{'buffer':0,'byteLength':4}],
        'accessors':[{'bufferView':0,'count':3}],
        'nodes':[{'mesh':0,'skin':0}], 'skins':[{'joints':[0]}],
        'meshes':[{'primitives':[{'indices':0,'attributes':{'POSITION':0}}]}],
        'extensions':{'VRMC_vrm':{'specVersion':'1.0','meta':{'name':'Test','authors':['Test'],'version':'1.0'},
            'humanoid':{'humanBones':{'hips':{'node':0}}}},
            'VRMC_springBone':{'colliders':[{'node':0}],'colliderGroups':[{'colliders':[0]}],
                'springs':[{'name':'Test','joints':[{'node':0}],'colliderGroups':[0]}]}}}


def glb(data):
    text=json.dumps(data).encode();text+=b' '*((-len(text))%4)
    chunks=struct.pack('<I4s',len(text),b'JSON')+text+struct.pack('<I4s',4,b'BIN\x00')+b'\0'*4
    return struct.pack('<4sII',b'glTF',2,12+len(chunks))+chunks


def test_checks_embedded_resources_and_spring_references(tmp_path):
    path=tmp_path/'avatar.vrm';path.write_bytes(glb(document()))
    result=validate_vrm(path)
    assert result['self_contained'] and result['meshes']==1 and result['springs']==1


@pytest.mark.parametrize('change',[
    lambda d:d['buffers'][0].update(uri='external.bin'),
    lambda d:d['bufferViews'][0].update(byteLength=100),
    lambda d:d['skins'][0].update(joints=[1]),
    lambda d:d['extensions']['VRMC_springBone']['colliderGroups'][0].update(colliders=[1]),
    lambda d:d['extensions']['VRMC_springBone']['springs'][0].update(joints=[{'node':1}]),
    lambda d:d['extensions']['VRMC_vrm'].update(specVersion='0.0'),
    lambda d:d.update(images=[{'uri':'external.png'}]),
])
def test_invalid_reference_or_external_resource_rejected(tmp_path,change):
    data=document();change(data);path=tmp_path/'avatar.vrm';path.write_bytes(glb(data))
    with pytest.raises(ValueError):validate_vrm(path)


@pytest.mark.parametrize('raw',[b'',b'glTF',glb(document())[:-4],b'xxxx'+glb(document())[4:]])
def test_truncated_or_invalid_container_rejected(tmp_path,raw):
    path=tmp_path/'bad.vrm';path.write_bytes(raw)
    with pytest.raises(ValueError):validate_vrm(path)


@pytest.mark.parametrize('value',['',' ',None,'x\n', 'a'*161])
def test_bad_metadata_rejected_before_native_or_output(tmp_path,value):
    runtime=Runtime.__new__(Runtime);runtime.lab=tmp_path
    with pytest.raises(ValueError):asyncio.run(runtime.export_wear_vrm('test.vrm','wear',value,'author'))
    assert not list(tmp_path.iterdir())


def test_existing_export_is_preserved_before_native_call(tmp_path):
    folder=tmp_path/'saves';folder.mkdir();target=folder/'keep.vrm';target.write_bytes(b'original')
    runtime=Runtime.__new__(Runtime);runtime.lab=tmp_path
    with pytest.raises(FileExistsError):asyncio.run(runtime.export_wear_vrm(target.name,'wear','title','author'))
    assert target.read_bytes()==b'original'


def test_invalid_native_output_is_not_published_and_completed_export_is_cleaned(tmp_path):
    runtime=Runtime.__new__(Runtime);runtime.lab=tmp_path;runtime.lock=asyncio.Lock();runtime.uncertain=False;runtime.dead=False
    calls=[]
    async def call(name,args):
        calls.append(name)
        if name=='wear_vrm_export_state':return {'wear_token':'wear','mode':3,'ready':True,'renderers':1}
        if name=='write_wear_vrm_export':Path(args['path']).write_bytes(b'broken');return {'task_id':'1'}
        return {}
    async def completed(task):pass
    runtime._call=call;runtime._wear_task=completed
    with pytest.raises(ValueError):asyncio.run(runtime.export_wear_vrm('new.vrm','wear','title','author'))
    assert calls.count('write_wear_vrm_export')==1 and calls[-1]=='finish_wear_vrm_export'
    assert not (tmp_path/'saves/new.vrm').exists()
    assert len(list((tmp_path/'saves').glob('stage-*.vrm')))==1


def test_uncertain_export_is_not_retried_or_disposed(tmp_path):
    runtime=Runtime.__new__(Runtime);runtime.lab=tmp_path;runtime.lock=asyncio.Lock();runtime.uncertain=False;runtime.dead=False
    calls=[]
    async def call(name,args):
        calls.append(name)
        if name=='wear_vrm_export_state':return {'wear_token':'wear','mode':3,'ready':True,'renderers':1}
        if name=='write_wear_vrm_export':return {'task_id':'1'}
        return {}
    async def pending(task):runtime.uncertain=True;raise TimeoutError('pending')
    runtime._call=call;runtime._wear_task=pending
    with pytest.raises(TimeoutError):asyncio.run(runtime.export_wear_vrm('new.vrm','wear','title','author'))
    assert calls.count('write_wear_vrm_export')==1 and 'finish_wear_vrm_export' not in calls


def test_native_fault_blocks_further_writes_without_disposing_pending_session(tmp_path):
    runtime=Runtime.__new__(Runtime);runtime.lab=tmp_path;runtime.lock=asyncio.Lock();runtime.uncertain=False;runtime.dead=False
    calls=[]
    async def call(name,args):
        calls.append(name)
        if name=='wear_vrm_export_state':return {'wear_token':'wear','mode':3,'ready':True,'renderers':1}
        if name=='write_wear_vrm_export':raise RuntimeError('native task failed')
        return {}
    runtime._call=call
    with pytest.raises(RuntimeError,match='native task failed'):
        asyncio.run(runtime.export_wear_vrm('new.vrm','wear','title','author'))
    assert runtime.uncertain and calls.count('write_wear_vrm_export')==1
    assert 'finish_wear_vrm_export' not in calls
