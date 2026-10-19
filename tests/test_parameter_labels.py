import asyncio
import hashlib
import json

import pytest

from vroid_mcp.parameter_labels import DATA, corrections, name_parameter, name_parameters
from vroid_mcp.runtime import Runtime


def test_pinned_corrections_and_mit_notice_are_bundled_verbatim():
    source=json.loads((DATA/'source.json').read_text(encoding='utf-8'))
    assert source['commit']=='a6b0719d01fa6cac9a857956907243d9916390b2'
    assert source['sha256']==hashlib.sha256((DATA/'en.json').read_bytes()).hexdigest()
    assert len(corrections())==source['entries']==269
    assert 'MIT License' in (DATA/'LICENSE').read_text(encoding='utf-8')


def test_same_native_label_is_disambiguated_by_exact_message_key_not_text():
    first={'id':'face/Nose/000','label':'Nose Size','translation_key':'Main.ModelEditor.Category.ParameterModel.name.NoseSize',
           'value':.25,'min':-1,'max':1,'semantic_key':'native_height'}
    second={**first,'id':'face/Nose/001','translation_key':'Main.ModelEditor.Category.ParameterModel.name.NoseWidth','semantic_key':'native_width'}
    a,b=name_parameter(first),name_parameter(second)
    assert a['name']=='Nose Height' and b['name']=='Nose Width'
    assert a['name_key']==first['translation_key'] and a['name_source']=='brainrom_correction'
    assert all(a[k]==v for k,v in first.items()) and 'name' not in first


@pytest.mark.parametrize('key',[None,'NoseSize','wrong.namespace.NoseSize','Main.ModelEditor.Category.ParameterModel.name.Unknown'])
def test_unknown_or_partial_message_keys_never_guess_a_correction(key):
    p=name_parameter({'id':'face/x','label':'NoseSize','translation_key':key})
    assert p['name']=='NoseSize' and p['name_source']=='native_label'
    assert p['name_key'] is None and p['name_language'] is None


def test_combined_bindings_and_unknown_status_survive_name_enrichment():
    p={'id':'body/x','label':'Native','semantic_key':'negative|positive',
       'semantic_bindings':[{'role':'negative','key':'negative'},{'role':'positive','key':'positive'}],
       'semantic_status':'complete'}
    result=name_parameters({'model_token':'token','next_offset':500,'parameters':[p,{**p,'id':'body/y','semantic_key':None,'semantic_status':'unavailable'}]})
    assert result['model_token']=='token' and result['next_offset']==500
    assert result['parameters'][0]['semantic_bindings']==p['semantic_bindings']
    assert result['parameters'][1]['semantic_key'] is None


def test_legacy_and_typed_lists_both_get_names_without_affecting_set_results():
    async def run():
        r=Runtime.__new__(Runtime);r.lock=asyncio.Lock()
        p={'id':'body/000','label':'Native','translation_key':'Main.ModelEditor.Category.ParameterModel.name.HeightFemale'}
        async def native(op,args=None):
            if op.startswith('list_'):return {'parameters':[p],'model_token':'token'}
            return {'ok':True,'frame':10}
        async def settle(*a):return {'model_token':'token'}
        r._call=native;r._settle=settle
        assert (await r.list_params('body'))['parameters'][0]['name']=='Female Height'
        assert (await r.parameter_call('list_parameters',{'domain':'body'}))['parameters'][0]['name']=='Female Height'
        assert await r.parameter_call('set_parameters',{'expected_model':'token'},True)=={'ok':True,'frame':10,'settled':True}
    asyncio.run(run())
