import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('public_sample_runner',
    Path(__file__).resolve().parents[1] / 'tools/run_sample.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_existing_lab_or_output_are_never_reused(tmp_path):
    source, repo = tmp_path / 'source', tmp_path / 'repo'
    lab, out = tmp_path / 'lab', tmp_path / 'out'
    lab.mkdir()
    protected = lab / 'save.vroid'
    protected.write_bytes(b'preserve')
    with pytest.raises(FileExistsError):
        runner.validate_paths(source, lab, out, repo)
    assert protected.read_bytes() == b'preserve' and not out.exists()


@pytest.mark.parametrize('mode', ['lab-in-source', 'output-in-repo', 'lab-in-output', 'output-in-lab'])
def test_overlapping_paths_are_rejected_before_creating_any_output(tmp_path, mode):
    source, repo = tmp_path / 'source', tmp_path / 'repo'
    lab, out = tmp_path / 'lab', tmp_path / 'out'
    if mode == 'lab-in-source': lab = source / 'nested'
    if mode == 'output-in-repo': out = repo / 'nested'
    if mode == 'lab-in-output': lab = out / 'nested'
    if mode == 'output-in-lab': out = lab / 'nested'
    with pytest.raises(ValueError):
        runner.validate_paths(source, lab, out, repo)
    assert not list(tmp_path.iterdir())


def test_e2e_parent_and_child_share_lab_scoped_temp_even_after_host_temp_was_cached(tmp_path, monkeypatch):
    import sys
    import tempfile
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
    import e2e_clean_lab as e2e
    monkeypatch.setenv('TEMP', str(tmp_path / 'bad-host-temp'))
    monkeypatch.setenv('TMP', str(tmp_path / 'bad-host-temp'))
    monkeypatch.setattr(tempfile, 'tempdir', str(tmp_path / 'cached-bad-temp'))
    scratch = e2e.configure_scratch(tmp_path / 'lab')
    assert scratch == tmp_path / 'lab/e2e-temp'
    assert tempfile.gettempdir() == str(scratch)
    with tempfile.TemporaryDirectory() as created:
        assert Path(created).parent == scratch


def test_mcp_capture_result_wrapper_is_decoded_as_summary_without_embedding_image_data():
    import sys
    from types import SimpleNamespace
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
    import e2e_clean_lab as e2e
    result = SimpleNamespace(isError=False, structuredContent={'result': [
        {'type': 'text', 'text': '{"capture_id":"example","manifest_path":"review.json"}'},
        {'type': 'image', 'data': 'not part of the summary'}]}, content=[])
    assert e2e.status_text(result) == {'capture_id': 'example', 'manifest_path': 'review.json'}
    result.structuredContent = {'ok': True, 'native': 'ordinary structured dict'}
    assert e2e.status_text(result)['native'] == 'ordinary structured dict'


def test_wear_phase_refuses_changed_saved_source_before_any_native_call(tmp_path):
    import asyncio
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
    import e2e_clean_lab as e2e
    source = tmp_path / 'saves/base.vroid'
    source.parent.mkdir()
    source.write_bytes(b'changed source')
    async def forbidden(*args, **kwargs):
        pytest.fail('No native calls before validating saved source')
    with pytest.raises(RuntimeError, match='Saved base changed'):
        asyncio.run(e2e.phase_wear(forbidden, tmp_path, {
            'base_model': str(source), 'base_filename': source.name, 'base_sha256': '0' * 64}, e2e.Steps()))
