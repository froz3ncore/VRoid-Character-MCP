import asyncio,copy
import pytest
from vroid_mcp.color_state import attach_color_readback
from vroid_mcp.runtime import Runtime

def row(i='left',color=None):
    value=color or [.95,.52,.08,1]
    return {'id':i,'type':'color','value':value,'mixed':False,'color_binding_status':'complete',
            'color_bindings':[{'value_status':'read','value':value}]}
def result():return {'ok':True,'applied':[{'id':'left','before':[0,0,1,1],'requested_value':[.95,.52,.08,1]}],'affected_color_parameter_ids':['left','both']}

def test_settled_binding_verification_includes_aggregate_effect():
    r=result();both=row('both');both.update(value=None,mixed=True)
    x=attach_color_readback(r,[row(),both])
    assert x['ok'] and x['color_verification_status']=='complete' and x['applied'][0]['verified'] is True
    assert {p['id'] for p in x['affected_parameters']}=={'left','both'}
    assert next(p for p in x['affected_parameters'] if p['id']=='both')['value'] is None

def test_native_setter_success_does_not_mask_readback_mismatch():
    r=attach_color_readback(result(),[row(color=[0,0,1,1])])
    assert not r['ok'] and r['color_verification_status']=='failed'
    assert r['applied'][0]['after']==[0,0,1,1] and r['applied'][0]['verified'] is False

def test_unknown_bindings_are_not_verified_from_one_representative_value():
    p=row();p.update(color_binding_status='unavailable',color_bindings=[],mixed=None)
    r=attach_color_readback(result(),[p])
    assert r['ok'] and r['color_verification_status']=='partial' and r['applied'][0]['verified'] is None

def test_all_aggregate_bindings_must_match_requested_color():
    p=row();p['color_bindings'].append({'value_status':'read','value':[0,0,1,1]})
    assert attach_color_readback(result(),[p])['color_verification_status']=='failed'

def test_partial_native_batch_keeps_error_and_applied_evidence():
    r=result();r.update(ok=False,error='Native operation failed')
    x=attach_color_readback(r,[row()])
    assert not x['ok'] and x['error']=='Native operation failed' and x['applied'][0]['verified']
    assert x['color_verification_status']=='partial'

def test_missing_applied_color_rejected():
    with pytest.raises(ValueError,match='missing'):attach_color_readback(result(),[])

def test_runtime_readback_follows_every_page_and_never_retries_write(tmp_path):
    r=Runtime.__new__(Runtime);r.lock=asyncio.Lock();calls=[]
    async def settle(*args):return {'model_token':'token'}
    async def native(operation,args):
        calls.append((operation,copy.deepcopy(args)))
        if operation=='set_parameters':return result()|{'frame':10}
        assert operation=='list_parameters'
        return {'model_token':'token','parameters':[row('both') if args['offset'] else row()],
                'next_offset':None if args['offset'] else 500}
    r._settle=settle;r._call=native
    x=asyncio.run(r.parameter_call('set_parameters',{'domain':'colors','expected_model':'token','changes':[]},True))
    assert x['settled'] and x['color_verification_status']=='complete'
    assert [c[0] for c in calls]==['set_parameters','list_parameters','list_parameters']
    assert calls[2][1]['offset']==500

def test_runtime_does_not_accept_another_model_readback():
    r=Runtime.__new__(Runtime);r.lock=asyncio.Lock()
    async def settle(*args):return {'model_token':'token'}
    async def native(operation,args):
        return result()|{'frame':1} if operation=='set_parameters' else {'model_token':'other'}
    r._settle=settle;r._call=native
    with pytest.raises(RuntimeError,match='COLOR_READBACK'):
        asyncio.run(r.parameter_call('set_parameters',{'domain':'colors','expected_model':'token'},True))
