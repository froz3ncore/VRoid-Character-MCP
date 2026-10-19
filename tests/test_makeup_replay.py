import copy,importlib.util,json
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('makeup_replay',Path(__file__).resolve().parents[1]/'tools/replay_makeup_recipe.py')
replay=importlib.util.module_from_spec(spec);spec.loader.exec_module(replay)

def recipe():return {'schema':'vroid-bounded-makeup-recipe-v1','reference_base_sha256':'a'*64,'parts':[{'part':'Cheek','image_dimensions':[32,32],'expected_mask_png_sha256':'b'*64,'marks':[{'points':[[.5,.5]],'color':[.8,.2,.3,.2]}]}]}
def read(tmp_path,value):
    path=tmp_path/'recipe.json';path.write_text(json.dumps(value),encoding='utf8');return replay.read_recipe(path)

def test_existing_recipe_format_normalizes_without_session_addresses(tmp_path):
    original,parts=read(tmp_path,recipe());assert parts[0]['part']=='Cheek' and parts[0]['area']=='region' and parts[0]['layer_name']=='MCP_recipe_Cheek_1'
    assert 'model_token' not in parts[0]

@pytest.mark.parametrize('mutation',[
    lambda d:d.update(reference_base_sha256=''),
    lambda d:d['parts'][0].update(part='Mouth'),
    lambda d:d['parts'][0].update(image_dimensions=[9999999,3]),
    lambda d:d['parts'][0].update(expected_mask_png_sha256='bad'),
    lambda d:d['parts'][0].update(opacity=float('nan')),
    lambda d:d['parts'][0].update(mask_options={'unknown':1}),
    lambda d:d['parts'][0].update(part='FaceSkin'),
])
def test_unsafe_recipe_is_rejected_before_any_client_starts(tmp_path,mutation):
    data=recipe();mutation(data)
    with pytest.raises(ValueError):read(tmp_path,data)

def test_bad_base_hash_never_enters_native_session(tmp_path,monkeypatch):
    import argparse,asyncio
    source=tmp_path/'input.vroid';source.write_bytes(b'untouched');entered=[]
    def forbidden(*args):entered.append(True);raise AssertionError('Native session must not start')
    monkeypatch.setattr(replay,'client_for',forbidden)
    args=argparse.Namespace(model=source)
    with pytest.raises(ValueError,match='hash'):asyncio.run(replay.replay(args,recipe(),[],{}))
    assert not entered and source.read_bytes()==b'untouched'

def test_nested_transport_errors_preserve_the_actual_failure_reason():
    from exceptiongroup import ExceptionGroup
    error=ExceptionGroup('transport wrapper',[ExceptionGroup('session wrapper',[ValueError('Recipe mask mismatch')])])
    assert replay.error_summary(error)=='Recipe mask mismatch'

def test_multiple_entries_for_one_region_are_rejected_before_edits(tmp_path):
    data=recipe();data['parts'].append(copy.deepcopy(data['parts'][0]))
    with pytest.raises(ValueError,match='combined'):read(tmp_path,data)
