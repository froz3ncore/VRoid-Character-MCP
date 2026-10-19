import copy
import pytest
from vroid_mcp.wear_reference import validate_wear_reference

def sample():
    matrix=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]
    body={'name':'Body','world_matrix':matrix,'positions':[[0,0,0],[1,0,0],[0,1,0]],'normals':[[0,0,1]]*3,'triangles':[0,1,2]}
    garment=copy.deepcopy(body)
    garment.update(name='Dress',source_positions=copy.deepcopy(body['positions']),uv0=[[0,0]]*3,
        bone_ids=[0],bindposes=[matrix],weights=[{'indices':[0,0,0,0],'weights':[1,0,0,0]} for _ in range(3)])
    return {'schema':'vroid-wear-reference-v1','body':body,'garments':[garment],
        'bones':[{'id':0,'name':'Hips','world_matrix':matrix}]}

def test_valid_reference():validate_wear_reference(sample())

def test_base_foot_skin_uses_the_shared_bone_table():
    data=sample();foot=copy.deepcopy(data['garments'][0]);foot['name']='Foot';data['base_meshes']=[foot]
    validate_wear_reference(data)
    foot['bone_ids']=[1]
    with pytest.raises(ValueError):validate_wear_reference(data)

@pytest.mark.parametrize('case',['unknown','duplicate','invalid_weight','nonfinite_matrix'])
def test_invalid_base_mesh_reference_rejected(case):
    data=sample();foot=copy.deepcopy(data['garments'][0]);foot['name']='Foot';data['base_meshes']=[foot]
    if case=='unknown':foot['name']='Unrelated'
    if case=='duplicate':data['base_meshes'].append(copy.deepcopy(foot))
    if case=='invalid_weight':foot['weights'][0]['weights']=[0,0,0,0]
    if case=='nonfinite_matrix':foot['world_matrix'][0][0]=float('nan')
    with pytest.raises(ValueError):validate_wear_reference(data)

def test_distinct_native_skeleton_instances_can_exceed_4096_bones():
    data=sample();matrix=data['bones'][0]['world_matrix']
    data['bones']=[{'id':i,'name':'bone','world_matrix':matrix} for i in range(4224)]
    validate_wear_reference(data)

@pytest.mark.parametrize('case',['nan','triangle','normal','matrix','stream','uv','weight','index','bone','duplicate_mesh','oversize_bones'])
def test_malformed_reference_rejected(case):
    data=sample();g=data['garments'][0]
    if case=='nan':g['positions'][0][0]=float('nan')
    if case=='triangle':g['triangles'][0]=3
    if case=='normal':g['normals'].pop()
    if case=='matrix':g['world_matrix'][3][0]=1
    if case=='stream':g['source_positions'].pop()
    if case=='uv':g['uv0'][0]=[1]
    if case=='weight':g['weights'][0]['weights']=[.5,0,0,0]
    if case=='index':g['weights'][0]['indices'][0]=1
    if case=='bone':g['bone_ids']=[1]
    if case=='duplicate_mesh':data['garments'].append(copy.deepcopy(g))
    if case=='oversize_bones':data['bones']=[data['bones'][0]]*32769
    with pytest.raises(ValueError):validate_wear_reference(data)
