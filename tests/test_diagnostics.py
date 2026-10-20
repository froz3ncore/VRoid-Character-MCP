import errno
import json
import os
from pathlib import Path
import subprocess

import pytest

from vroid_mcp import diagnostics as doctor, lab_lock


def snapshot(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file()}


@pytest.fixture
def installation(tmp_path, monkeypatch):
    repo = tmp_path / 'repo'
    bridge = repo / 'node_modules/frida-il2cpp-bridge'
    (bridge / 'dist').mkdir(parents=True)
    (bridge / 'dist/index.js').write_text('bridge')
    (bridge / 'package.json').write_text('{"version":"0.14.0"}')
    (repo / 'package.json').write_text('{"dependencies":{"frida-il2cpp-bridge":"0.14.0"}}')
    source = tmp_path / 'installation'
    (source / 'VRoidStudio_Data/il2cpp_data/Metadata').mkdir(parents=True)
    for name in ('VRoidStudio.exe', 'GameAssembly.dll', 'UnityPlayer.dll',
                 'VRoidStudio_Data/il2cpp_data/Metadata/global-metadata.dat'):
        (source / name).write_bytes(b'fixture')
    digest = doctor.hashlib.sha256(b'fixture').hexdigest()
    monkeypatch.setattr(doctor, 'SUPPORTED_ASSEMBLIES', {digest: 'test build'})
    monkeypatch.setattr(doctor.importlib.metadata, 'version', doctor.REQUIRED_PACKAGES.__getitem__)
    monkeypatch.setattr(doctor, 'probe_asyncio', lambda: {'state': 'ok'})
    monkeypatch.setattr(doctor, 'probe_imports', lambda: {'state': 'ok'})
    monkeypatch.setattr(doctor, 'inspect_registry', lambda: {'state': 'absent'})
    return source, repo


def row(report, code):
    return next(r for r in report['checks'] if r['code'] == code)


def test_complete_source_is_read_only_even_with_auto_clear_enabled(installation, monkeypatch):
    source, repo = installation
    before = snapshot(source.parent)
    monkeypatch.setenv('VROID_MCP_CLEAR_CLOSET_KEY', '1')
    monkeypatch.setattr(doctor.closet_guard, 'clear', lambda *a: pytest.fail('No registry writes'))
    report = doctor.build_report(source=source, repo=repo)
    assert row(report, 'application.build')['status'] == 'pass'
    assert snapshot(source.parent) == before
    assert 'lab.ownership' not in [r['code'] for r in report['checks']]


def test_unknown_build_is_reported_with_hash_and_does_not_bypass_allowlist(installation, monkeypatch):
    source, repo = installation
    monkeypatch.setattr(doctor, 'SUPPORTED_ASSEMBLIES', {})
    report = doctor.build_report(source=source, repo=repo)
    assert not report['ok'] and report['exit_code'] == 1
    assert row(report, 'application.build')['detail']['sha256']
    assert 'application.build' in report['blocked_checks']


def test_failures_are_aggregated_instead_of_hiding_later_checks(installation, monkeypatch):
    source, repo = installation
    (source / 'UnityPlayer.dll').unlink()
    (repo / 'node_modules/frida-il2cpp-bridge/package.json').write_text('{}')
    monkeypatch.setattr(doctor, 'probe_asyncio', lambda: {'state': 'timeout'})
    monkeypatch.setattr(doctor, 'inspect_registry', lambda: {'state': 'unreadable'})
    report = doctor.build_report(source=source, repo=repo)
    assert {'application.build', 'environment.asyncio', 'registry.closet',
            'dependency.bridge'} <= set(report['blocked_checks'])


def test_missing_dependency_and_wrong_version_have_actionable_results(installation, monkeypatch):
    source, repo = installation
    def version(name):
        if name == 'mcp':
            raise doctor.importlib.metadata.PackageNotFoundError(name)
        return '0.0'
    monkeypatch.setattr(doctor.importlib.metadata, 'version', version)
    result = doctor.build_report(source=source, repo=repo)
    for name in ('mcp', 'frida'):
        assert row(result, 'dependency.' + name)['status'] == 'blocked'
        assert 'requirements.txt' in row(result, 'dependency.' + name)['recovery']


def test_asyncio_probe_is_bounded_and_import_failure_is_reported(monkeypatch):
    def timeout(*a, **kw):
        assert kw['timeout'] == 0.02
        raise subprocess.TimeoutExpired(a[0], kw['timeout'])
    monkeypatch.setattr(subprocess, 'run', timeout)
    assert doctor.probe_asyncio(.02)['state'] == 'timeout'
    assert doctor.probe_imports(.02)['state'] == 'timeout'
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw:
                        subprocess.CompletedProcess(a[0], 1, '', 'broken module'))
    assert doctor.probe_imports()['error'] == 'broken module'


def test_diagnosing_a_missing_lab_never_creates_it(tmp_path, monkeypatch):
    lab = tmp_path / 'missing'
    monkeypatch.setattr(doctor, 'probe_asyncio', lambda: {'state': 'ok'})
    monkeypatch.setattr(doctor, 'probe_imports', lambda: {'state': 'ok'})
    report = doctor.build_report(lab=lab, repo=tmp_path)
    assert not report['ok'] and not lab.exists()


def test_cli_preserves_existing_report(tmp_path, monkeypatch):
    report = tmp_path / 'report.json'
    report.write_text('keep')
    monkeypatch.setattr(doctor, 'build_report', lambda **kw: pytest.fail('must fail first'))
    with pytest.raises(SystemExit) as error:
        doctor.main(['--lab', str(tmp_path), '--json', str(report)])
    assert error.value.code == 2 and report.read_text() == 'keep'


@pytest.mark.skipif(os.name != 'nt', reason='Windows byte-range lock')
def test_inspection_distinguishes_live_lock_from_stale_pid_and_preserves_both(tmp_path):
    path = lab_lock.lock_path(tmp_path)
    assert doctor.inspect_lock(tmp_path)['state'] == 'unreserved'
    assert not path.exists()
    path.write_bytes(b'\0' + b'999999\n')
    before = path.read_bytes(), path.stat().st_mtime_ns
    assert doctor.inspect_lock(tmp_path)['state'] == 'available'
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    handle = lab_lock.acquire(tmp_path)
    try:
        before_time = path.stat().st_mtime_ns
        live = doctor.inspect_lock(tmp_path)
        assert live['state'] == 'busy' and live['recorded_pid'] == str(os.getpid())
        assert path.stat().st_mtime_ns == before_time
    finally:
        lab_lock.release(handle)


@pytest.mark.skipif(os.name != 'nt', reason='Windows byte-range lock')
def test_empty_legacy_lock_is_not_rewritten(tmp_path):
    path = lab_lock.lock_path(tmp_path)
    path.write_bytes(b'')
    before = path.stat().st_mtime_ns
    assert doctor.inspect_lock(tmp_path)['state'] == 'available'
    assert path.read_bytes() == b'' and path.stat().st_mtime_ns == before


@pytest.mark.skipif(os.name != 'nt', reason='Windows junction paths')
def test_linked_installation_is_rejected_before_binary_reads(installation, monkeypatch):
    source, repo = installation
    # A simulated redirected application path also covers environments in which
    # symlink creation itself requires privileges.
    original = Path.resolve
    monkeypatch.setattr(Path, 'resolve', lambda p, *a, **kw:
                        source.parent / 'elsewhere' if p == source else original(p, *a, **kw))
    result = doctor.build_report(source=source, repo=repo)
    assert row(result, 'paths.physical')['status'] == 'blocked'
    assert row(result, 'application.build')['status'] == 'blocked'
