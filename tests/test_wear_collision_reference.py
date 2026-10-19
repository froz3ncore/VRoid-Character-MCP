import copy,math
import pytest
from test_wear_reference import sample
from vroid_mcp.wear_reference import validate_wear_reference

def collision_sample():
    data=sample();identity=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]
    data['colliders']=[{'world_matrix':identity,'radius':.05,'offset':[0,0,0],'tail':[0,1,0],'world_offset':[0,0,0],'world_tail':[0,1,0]}]
    data['spring_bones']=[{'world_matrix':identity,'position':[0,0,0]}]
    return data

def test_valid_collision_context():validate_wear_reference(collision_sample())

@pytest.mark.parametrize('case',['radius','matrix','world_tail','spring_position'])
def test_invalid_collision_context_is_refused(case):
    data=collision_sample()
    if case=='radius':data['colliders'][0]['radius']=math.nan
    if case=='matrix':data['colliders'][0]['world_matrix'][0][0]=math.nan
    if case=='world_tail':data['colliders'][0]['world_tail'][1]=2
    if case=='spring_position':data['spring_bones'][0]['position'][2]=math.inf
    with pytest.raises(ValueError):validate_wear_reference(data)
