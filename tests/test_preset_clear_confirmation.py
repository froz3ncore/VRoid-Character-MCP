import asyncio
from vroid_mcp.runtime import Runtime

def run_clear(after):
    async def run():
        runtime=Runtime.__new__(Runtime);runtime.lock=asyncio.Lock()
        before=[{'id':'clothes','revision':'1'},{'id':'shoes','revision':'2'}]
        async def native(name,args):
            if name=='apply_preset':return {'clear':True,'frame':10,'before_groups':before,'changed':True}
            assert name=='preset_state';return {'selected':None,'active_groups':after}
        async def settle(*args):return {}
        runtime._call=native;runtime._settle=settle
        return await runtime.apply_preset('clothing','token','clothing/Onepiece/none')
    return asyncio.run(run())

def test_actual_removed_group_is_reported():
    result=run_clear([{'id':'shoes','revision':'2'}])
    assert result['changed'] and result['confirmation']=='groups_removed'
    assert [g['id'] for g in result['removed_groups']]==['clothes']

def test_repeated_clear_does_not_invent_change():
    result=run_clear([{'id':'clothes','revision':'1'},{'id':'shoes','revision':'2'}])
    assert not result['changed'] and result['confirmation']=='no_group_removed'
    assert result['removed_groups']==[]
