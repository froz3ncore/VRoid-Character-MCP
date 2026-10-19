import asyncio,copy
import pytest
from vroid_mcp.texture_layer_state import register_layer_state_tools,state_digest,describe_layers

class Native:
    def __init__(self):
        self.layer={'layer_id':'owned','Name':'Makeup','Opacity':1.,'Visibility':True,'CompositionMode':'Normal'};self.writes=[]
    async def parameter_call(self,operation,args,mutating=False):
        if operation=='list_texture_layers':return {'layers':[copy.deepcopy(self.layer)]}
        assert operation=='set_texture_layer_state' and mutating;self.writes.append(args)
        if args['visible'] is not None:self.layer['Visibility']=args['visible']
        if args['opacity'] is not None:self.layer['Opacity']=args['opacity']
        return {'layer':copy.deepcopy(self.layer),'history_command_count':2}

def setup():
    native=Native();tools={}
    def ready(**kwargs):
        def add(fn):tools[fn.__name__]=fn;return fn
        return add
    register_layer_state_tools(ready,native,None,None);return native,tools['set_texture_layer_state']

def test_existing_layer_edit_uses_fresh_metadata_and_returns_new_state_token():
    async def run():
        native,edit=setup();old=state_digest(native.layer)
        result=await edit('model','region','owned',old,False,.4)
        assert result['layer']['Visibility'] is False and result['layer']['Opacity']==.4 and result['saved'] is False
        assert result['layer']['state_sha256']!=old and native.writes[0]['expected_layer']['Opacity']==1.
    asyncio.run(run())

def test_concurrent_layer_changes_fail_before_native_write():
    async def run():
        native,edit=setup();old=state_digest(native.layer);native.layer['Name']='Changed elsewhere'
        with pytest.raises(ValueError,match='metadata'):await edit('model','region','owned',old,False,None)
        assert not native.writes
    asyncio.run(run())

@pytest.mark.parametrize('visible,opacity',[(None,None),('false',None),(None,float('nan')),(None,2),(None,True)])
def test_bad_edits_fail_before_native_write(visible,opacity):
    async def run():
        native,edit=setup()
        with pytest.raises(ValueError):await edit('model','region','owned',state_digest(native.layer),visible,opacity)
        assert not native.writes
    asyncio.run(run())

def test_layer_tokens_do_not_depend_on_response_annotation():
    native,_=setup();token=state_digest(native.layer);result=describe_layers({'layers':[native.layer]})
    assert result['layers'][0]['state_sha256']==state_digest(result['layers'][0])==token
