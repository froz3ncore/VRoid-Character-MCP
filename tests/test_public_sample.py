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
    import json
    import os
    import subprocess
    import sys
    import tempfile
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
    import e2e_clean_lab as e2e
    monkeypatch.setenv('TEMP', str(tmp_path / 'bad-host-temp'))
    monkeypatch.setenv('TMP', str(tmp_path / 'bad-host-temp'))
    monkeypatch.setenv('TMPDIR', str(tmp_path / 'inherited-host-temp'))
    monkeypatch.setattr(tempfile, 'tempdir', str(tmp_path / 'cached-bad-temp'))
    scratch = e2e.configure_scratch(tmp_path / 'lab')
    assert scratch == tmp_path / 'lab/e2e-temp'
    assert {os.environ[key] for key in ('TEMP', 'TMP', 'TMPDIR')} == {str(scratch)}
    assert tempfile.gettempdir() == str(scratch)
    with tempfile.TemporaryDirectory() as created:
        assert Path(created).parent == scratch
    child = subprocess.run([sys.executable, '-c',
        'import json,os,tempfile; print(json.dumps({'
        '"temp":tempfile.gettempdir(),'
        '"env":[os.environ[key] for key in ("TEMP","TMP","TMPDIR")]}))'],
        check=True, capture_output=True, text=True, timeout=15)
    assert json.loads(child.stdout) == {'temp': str(scratch), 'env': [str(scratch)] * 3}


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


@pytest.mark.parametrize('module_name', [
    'check_attached_sessions', 'check_attached_editing', 'check_continuous_editing',
    'check_native_domains', 'replay_makeup_recipe',
])
def test_check_entrypoints_scope_parent_and_child_scratch_before_native_work(tmp_path, monkeypatch, module_name):
    import asyncio
    import importlib
    import os
    import sys
    import tempfile
    from contextlib import asynccontextmanager

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
    module = importlib.import_module(module_name)
    out, lab = tmp_path / 'out', tmp_path / 'lab'
    monkeypatch.setenv('TEMP', str(tmp_path / 'bad-host-temp'))
    monkeypatch.setenv('TMP', str(tmp_path / 'bad-host-temp'))
    inherited = tmp_path / 'inherited-host-temp'
    inherited.mkdir()
    monkeypatch.setenv('TMPDIR', str(inherited))
    monkeypatch.setattr(tempfile, 'tempdir', str(inherited))
    scratch = (lab if module_name == 'check_native_domains' else out) / 'temp'

    class BeforeNative(Exception):
        pass

    def verify(child_temp=None):
        assert {os.environ[key] for key in ('TEMP', 'TMP', 'TMPDIR')} == {str(scratch)}
        assert tempfile.gettempdir() == str(scratch)
        assert scratch.is_dir()
        if child_temp is not None:
            assert set(child_temp) == {str(scratch)}
        raise BeforeNative

    @asynccontextmanager
    async def stop_transport(params, **kwargs):
        verify([params.env[key] for key in ('TEMP', 'TMP', 'TMPDIR')])
        yield  # pragma: no cover - never start transport/native process

    if module_name.startswith('check_attached_'):
        monkeypatch.setattr(module.prepare_lab, 'check_directories', lambda *args: None)
        monkeypatch.setattr(module.prepare_lab, 'check_install', lambda *args: None)
        monkeypatch.setattr(module.prepare_lab, 'main', lambda *args: verify())
        call = module.check(tmp_path / 'source', out, 'F00')
    else:
        monkeypatch.setattr(module, 'stdio_client', stop_transport)
        if module_name == 'check_continuous_editing':
            lab.mkdir()
            call = module.run(lab, out, 'F00', 1)
        elif module_name == 'check_native_domains':
            (lab / 'app').mkdir(parents=True)
            (lab / 'app/VRoidStudio.exe').write_bytes(b'not an executable')
            monkeypatch.setattr(module.lab_lock, 'probe', lambda *args: None)
            call = module.run(lab, [], out / 'report.json')
        else:
            out.mkdir()
            async def enter_recipe():
                async with module.client_for(lab, tmp_path / 'source.vroid', out, 'check'):
                    pytest.fail('Native transport must not start')
            call = enter_recipe()
    with pytest.raises(BeforeNative):
        asyncio.run(call)


def test_powershell_checks_pin_all_child_temp_variables_to_project_scratch(tmp_path):
    import json
    import os
    import shutil
    import subprocess

    shell = shutil.which('pwsh') or shutil.which('powershell')
    if os.name != 'nt' or shell is None:
        pytest.skip('Windows PowerShell check entrypoint')
    probe = tmp_path / 'python-probe.cmd'
    probe.write_text('@echo %TEMP%^|%TMP%^|%TMPDIR%\r\n', encoding='utf-8', newline='')
    out = tmp_path / 'checks'
    script = Path(__file__).resolve().parents[1] / 'tools/run_checks.ps1'
    env = dict(os.environ, TEMP=str(tmp_path), TMP=str(tmp_path),
               TMPDIR=str(tmp_path / 'inherited-host-temp'))
    subprocess.run([shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script),
        '-Python', str(probe), '-Out', str(out), '-SkipUnit', '-SkipTools', '-SkipJs'],
        check=True, capture_output=True, text=True, timeout=30, env=env)
    report = json.loads((out / 'checks.json').read_text(encoding='utf-8-sig'))
    evidence = next(stage['detail'] for stage in report['stages'] if stage['name'] == 'environment')
    scratch = Path(evidence['temp'])
    assert scratch.is_relative_to(script.parents[1] / 'temp')
    assert evidence['python'].split('|') == [str(scratch)] * 3


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
