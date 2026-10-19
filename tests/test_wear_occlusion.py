import copy
import pytest
from vroid_mcp.wear_occlusion import describe,geometry_hash,prepare,validate_indices
def state():
    return dict(wear_token='wear:1',renderer_name='Body',renderer_id='0x1',default_mesh_id='0x2',default_vertex_count=20,source_positions=[[i,0.,0.] for i in range(20)],source_triangles=[0,1,2],hidden_vertices=[])
def test_geometry_identity_is_float32_and_topology_sensitive():
    s=state();h=geometry_hash(s['source_positions'],s['source_triangles'])
    assert h==geometry_hash([[float(x) for x in p] for p in s['source_positions']],s['source_triangles'])
    assert h!=geometry_hash(s['source_positions'],[0,2,1])
@pytest.mark.parametrize('field,value',[('wear_token','wear:2'),('renderer_id','0x8'),('default_mesh_id','0x9'),('hidden_vertices',[1])])
def test_stale_identity_or_mask_rejects_before_mutation(field,value):
    s=state();token=describe(s)['occlusion_token'];changed=copy.deepcopy(s);changed[field]=value
    with pytest.raises(ValueError,match='changed'):prepare(changed,token,[2])
@pytest.mark.parametrize('ids',[[True],[-1],[20],[1,1],[2,1],list(range(5))])
def test_invalid_or_excessive_indices_rejected(ids):
    with pytest.raises(ValueError):validate_indices(ids,20)
def test_reset_and_preserve_existing_marks():
    s=state();s['hidden_vertices']=[1];token=describe(s)['occlusion_token']
    assert prepare(s,token,[1,2])['expected_hidden_vertices']==[1]
    assert prepare(s,token,[])['hidden_vertices']==[]
