import asyncio,copy,math
import pytest
from vroid_mcp.runtime import Runtime

def sample():return dict(wear_token='wear',model_modified=False,nodes=[dict(id='0x1',name='Foot',parent_id=None,world_matrix=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]])])

@pytest.mark.parametrize('problem',['identity','modified','empty','duplicate','nan','shape','projective'])
def test_bad_preview_snapshot_rejected(problem):
    value=sample()
    if problem=='identity':value['wear_token']='stale'
    if problem=='modified':value['model_modified']=True
    if problem=='empty':value['nodes']=[]
    if problem=='duplicate':value['nodes'].append(copy.deepcopy(value['nodes'][0]))
    if problem=='nan':value['nodes'][0]['world_matrix'][0][0]=math.nan
    if problem=='shape':value['nodes'][0]['world_matrix'][0]=[1,0]
    if problem=='projective':value['nodes'][0]['world_matrix'][3][0]=1
    r=Runtime.__new__(Runtime);r.lock=asyncio.Lock()
    async def native(*args):return value
    r._call=native
    with pytest.raises(ValueError):asyncio.run(r.sample_wear_preview_rig('wear'))

def test_duplicate_names_preserve_distinct_native_identities():
    value=sample();other=copy.deepcopy(value['nodes'][0]);other['id']='0x2';value['nodes'].append(other)
    r=Runtime.__new__(Runtime);r.lock=asyncio.Lock()
    async def native(name,args):
        assert name=='sample_wear_preview_rig' and args=={'expected_wear':'wear'}
        return value
    r._call=native
    assert len(asyncio.run(r.sample_wear_preview_rig('wear'))['nodes'])==2
