import asyncio
import pytest
from vroid_mcp.runtime import Runtime

def run_add(after,token='model:1'):
    async def run():
        runtime=Runtime.__new__(Runtime);runtime.lock=asyncio.Lock()
        async def call(name,args):
            if name=='add_shoe_template':return {'model_token':'model:1','template_id':'heel','frame':12,'before_groups':[{'id':'body','type':'Body'}]}
            assert name=='shoe_template_state';return {'model_token':token,'active_groups':after}
        async def settle(*a):return {}
        runtime._call=call;runtime._settle=settle
        return await runtime.add_shoe_template('model:1','heel')
    return asyncio.run(run())

def test_native_group_readback_required_for_success():
    result=run_add([{'id':'body','type':'Body'},{'id':'heel-instance','type':'Level1.Shoes'}])
    assert result['ok'] and result['confirmation']=='native_shoe_group_added'
    assert result['added_groups'][0]['id']=='heel-instance' and not result['retry_safe']

@pytest.mark.parametrize('after',[
    [{'id':'body','type':'Body'}],
    [{'id':'body','type':'Body'},{'id':'wrong','type':'Socks'}],
    [{'id':'heel-instance','type':'Shoes'}],
    [{'id':'body','type':'Body'},{'id':'heel1','type':'Shoes'},{'id':'heel2','type':'Shoes'}],
])
def test_noop_wrong_group_removal_or_multiple_additions_are_unconfirmed(after):
    assert not run_add(after)['ok']

def test_changed_model_is_rejected_after_mutation_without_retry():
    with pytest.raises(RuntimeError,match='MODEL_CHANGED'):run_add([],token='other')
