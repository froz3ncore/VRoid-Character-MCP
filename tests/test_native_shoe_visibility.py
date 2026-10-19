import asyncio
import pytest
from vroid_mcp.native_shoe_visibility import describe,prepare

def state():
    return {'wear_token':'wear:1','renderer_name':'Cloth','renderer_id':'shoe1','material_names':['N00_009_01_Shoes_01_CLOTH'],'default_mesh_id':'mesh1','default_vertex_count':3,'source_positions':[[0,0,0],[1,0,0],[0,1,0]],'source_triangles':[0,1,2],'hidden_vertices':[]}

def test_full_shoe_hide_and_restore_use_original_indices():
    s=state();token=describe(s)['visibility_token'];assert prepare(s,token,False)['hidden_vertices']==[0,1,2]
    s['hidden_vertices']=[0,1,2];assert prepare(s,describe(s)['visibility_token'],True)['hidden_vertices']==[]

@pytest.mark.parametrize('field,value',[('renderer_name','Body'),('material_names',['N00_000_00_Body_00_SKIN']),('material_names',['N00_009_01_Shoes_01_CLOTH','Dress_CLOTH']),('hidden_vertices',[1])])
def test_never_hide_body_mixed_clothes_or_overwrite_partial_mask(field,value):
    s=state();s[field]=value
    with pytest.raises(ValueError):describe(s)

@pytest.mark.parametrize('field,value',[('wear_token','wear:2'),('renderer_id','shoe2'),('default_mesh_id','mesh2'),('hidden_vertices',[0,1,2]),('source_triangles',[0,2,1])])
def test_stale_identity_or_mask_is_rejected(field,value):
    s=state();token=describe(s)['visibility_token'];s[field]=value
    with pytest.raises(ValueError):prepare(s,token,False)

@pytest.mark.parametrize('failure',['native_exception','wrong_readback'])
def test_uncertain_mutation_blocks_followup_and_never_retries(failure):
    from vroid_mcp.runtime import Runtime
    async def run():
        runtime=Runtime.__new__(Runtime);runtime.lock=asyncio.Lock();runtime.uncertain=False;mutations=[]
        async def call(name,args):
            if name=='inspect_wear_native_shoes':return state()
            mutations.append(name)
            if failure=='native_exception':raise RuntimeError('NATIVE_SHOE_MUTATION_UNCERTAIN: readback unavailable')
            return {'hidden_vertices':[]}
        runtime._call=call
        with pytest.raises(RuntimeError):await runtime.set_wear_native_shoes_visible('wear:1',describe(state())['visibility_token'],False)
        assert runtime.uncertain and mutations==['set_wear_native_shoes_visible']
    asyncio.run(run())
