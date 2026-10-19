"""Independent inspector must reject plausible but broken humanoid/expression/spring bindings."""
import copy,importlib.util,json,struct
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('vrm_inspect',Path(__file__).resolve().parents[1]/'tools/vrm_inspect.py')
inspector=importlib.util.module_from_spec(spec);spec.loader.exec_module(inspector)

def avatar(version='1.0'):
    names=inspector.REQUIRED_HUMANOID
    nodes=[{} for _ in names];nodes[2]['mesh']=0
    doc={'asset':{'version':'2.0'},'nodes':nodes,'meshes':[{'primitives':[{'targets':[{}]}]}]}
    if version=='1.0':
        doc['extensions']={'VRMC_vrm':{'specVersion':'1.0','humanoid':{'humanBones':{name:{'node':i} for i,name in enumerate(names)}},
            'expressions':{'preset':{'blink':{'morphTargetBinds':[{'node':2,'index':0,'weight':1}]}}}},
            'VRMC_springBone':{'springs':[{'joints':[{'node':0}]}]}}
    else:
        doc['extensions']={'VRM':{'humanoid':{'humanBones':[{'bone':name,'node':i} for i,name in enumerate(names)]},
            'blendShapeMaster':{'blendShapeGroups':[{'name':'Blink','presetName':'blink','binds':[{'mesh':0,'index':0,'weight':100}]},{'name':'Custom','presetName':'unknown'}]},
            'secondaryAnimation':{'boneGroups':[{'bones':[0]}]}}}
    return doc

def write_avatar(tmp_path,doc):
    text=json.dumps(doc).encode();text+=b' '*(-len(text)%4)
    raw=struct.pack('<III',inspector.GLB_MAGIC,2,20+len(text))+struct.pack('<II',len(text),inspector.JSON_CHUNK)+text
    path=tmp_path/'avatar.vrm';path.write_bytes(raw);return path

@pytest.mark.parametrize('version',['1.0','0.0'])
def test_valid_delivery_profile_and_legacy_expression_classification(tmp_path,version):
    path=write_avatar(tmp_path,avatar(version));result=inspector.inspect(path)
    assert result['ok'] and not result['findings'] and len(result['humanoid']['bones'])==15
    assert result['expressions']['preset']==['blink']
    if version=='0.0':assert result['expressions']['custom']==['Custom']

@pytest.mark.parametrize('value',[-1,15,True,1.0,None,'2'])
def test_humanoid_node_type_and_bounds_are_checked(tmp_path,value):
    doc=avatar();doc['extensions']['VRMC_vrm']['humanoid']['humanBones']['leftFoot']['node']=value
    result=inspector.inspect(write_avatar(tmp_path,doc));assert not result['ok'] and any('humanoid node' in p for p in result['findings'])

@pytest.mark.parametrize('bone',['leftLowerArm','rightHand','leftLowerLeg','head'])
def test_all_fifteen_required_roles_are_enforced(tmp_path,bone):
    doc=avatar();del doc['extensions']['VRMC_vrm']['humanoid']['humanBones'][bone]
    result=inspector.inspect(write_avatar(tmp_path,doc));assert not result['ok'] and bone in result['humanoid']['missing_required']

def test_duplicate_humanoid_nodes_are_rejected(tmp_path):
    doc=avatar();doc['extensions']['VRMC_vrm']['humanoid']['humanBones']['leftFoot']['node']=0
    assert not inspector.inspect(write_avatar(tmp_path,doc))['ok']

@pytest.mark.parametrize('mutation',[
    lambda d:d['extensions']['VRMC_vrm']['expressions']['preset']['blink']['morphTargetBinds'][0].update(node=999),
    lambda d:d['extensions']['VRMC_vrm']['expressions']['preset']['blink']['morphTargetBinds'][0].update(index=999),
    lambda d:d['extensions']['VRMC_springBone']['springs'][0]['joints'][0].update(node=999),
    lambda d:d['extensions']['VRMC_springBone']['springs'][0].update(joints=[]),
    lambda d:d['extensions']['VRMC_springBone']['springs'][0].update(colliderGroups=[0]),
    lambda d:d['extensions']['VRMC_springBone'].update(colliders=[{'node':999}]),
    lambda d:d['nodes'][0].update(children=[999]),
])
def test_bad_expression_and_spring_references_fail(tmp_path,mutation):
    doc=avatar();mutation(doc);result=inspector.inspect(write_avatar(tmp_path,doc));assert not result['ok'] and result['findings']

def test_absent_expressions_springs_require_explicit_profile_opt_out(tmp_path):
    doc=avatar();doc['extensions']['VRMC_vrm']['expressions']={};del doc['extensions']['VRMC_springBone']
    path=write_avatar(tmp_path,doc);assert not inspector.inspect(path)['ok'];assert inspector.main([str(path)])==1
    result=inspector.inspect(path,allow_no_expressions=True,allow_no_springs=True)
    assert result['ok'] and not result['findings'] and len(result['warnings'])==2
    assert inspector.main([str(path),'--allow-no-expressions','--allow-no-springs'])==0
    doc['extensions']['VRMC_vrm']['humanoid']['humanBones']['hips']['node']=999
    assert not inspector.inspect(write_avatar(tmp_path,doc),allow_no_expressions=True,allow_no_springs=True)['ok']

@pytest.mark.parametrize('bad', ['version','trailing','duplicate_json','truncated_bin'])
def test_all_container_chunks_are_checked_before_accepting_json(tmp_path,bad):
    path=write_avatar(tmp_path,avatar());raw=path.read_bytes()
    if bad=='version':raw=raw[:4]+struct.pack('<I',1)+raw[8:]
    else:
        tail={'trailing':b'xxxx','duplicate_json':raw[12:],'truncated_bin':struct.pack('<II',8,0x004E4942)+b'1234'}[bad]
        raw=raw[:8]+struct.pack('<I',len(raw)+len(tail))+raw[12:]+tail
    path.write_bytes(raw);assert inspector.main([str(path)])==2
