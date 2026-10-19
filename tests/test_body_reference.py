import copy
import pytest
from vroid_mcp.body_reference import validate_body_reference

def sample():
    mat=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]
    mesh={'node_id':0,'world_matrix':mat,'positions':[[0,0,0],[1,0,0],[0,1,0]],'uv0':[],
          'triangles':[0,1,2],'bone_nodes':[0],
          'weights':[{'indices':[0,0,0,0],'weights':[1,0,0,0]} for _ in range(3)]}
    return {'schema':'vroid-body-reference-v1','model_token':'current','height_cm':170,
            'nodes':[{'id':0,'parent':None,'world_matrix':mat}],
            'meshes':[dict(copy.deepcopy(mesh),name=name) for name in ['Body','Face','Hand','Foot']]}

def test_valid():
    assert validate_body_reference(sample(),'current')['vertices']==12

@pytest.mark.parametrize('case',['token','cycle','index','nan','weights','bone','stream','matrix','missing'])
def test_invalid_reference_rejected(case):
    d=sample();m=d['meshes'][0]
    if case=='token':d['model_token']='stale'
    if case=='cycle':d['nodes'][0]['parent']=0
    if case=='index':m['triangles'][0]=3
    if case=='nan':m['positions'][0][0]=float('nan')
    if case=='weights':m['weights'][0]['weights']=[.5,0,0,0]
    if case=='bone':m['bone_nodes']=[99]
    if case=='stream':m['weights'].pop()
    if case=='matrix':m['world_matrix'][3][3]=0
    if case=='missing':d['meshes'].pop()
    with pytest.raises(ValueError):validate_body_reference(d,'current')
