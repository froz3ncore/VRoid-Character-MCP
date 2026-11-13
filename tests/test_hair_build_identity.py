"""The verified procedural descriptor receives the same digest that passed allowlist validation."""
import hashlib
from types import SimpleNamespace

from vroid_mcp import bridge, supported_builds


def test_validated_assembly_identity_reads_once_and_preserves_public_build_label(tmp_path, monkeypatch):
    path = tmp_path / 'GameAssembly.dll'
    path.write_bytes(b'fixture binary')
    metadata = tmp_path / supported_builds.METADATA_PATH
    metadata.parent.mkdir(parents=True)
    metadata.write_bytes(b'fixture metadata')
    metadata_digest = hashlib.sha256(metadata.read_bytes()).hexdigest()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    build = supported_builds.Build('fixture', 'test build', None)
    monkeypatch.setitem(supported_builds.BUILDS, digest, build)
    opened = []
    original_open = type(path).open
    def count_open(target, *args, **kwargs):
        if target == path:
            opened.append(target)
        return original_open(target, *args, **kwargs)
    monkeypatch.setattr(type(path), 'open', count_open)
    assert supported_builds.assembly_identity(path) == {
        'sha256': digest, 'build': build.label, 'metadata_sha256': metadata_digest}
    assert len(opened) == 1
    assert supported_builds.validate_assembly(path) == build.label
    assert len(opened) == 2


def test_script_source_carries_verified_digest_without_conferring_support(tmp_path):
    native_bridge = tmp_path / 'bridge.js'
    native_bridge.write_text('// fixture', encoding='utf-8', newline='\r\n')
    text = bridge.script_text(None, native_bridge, attached=True, assembly_sha256='exact-validated-digest')
    assert 'const VROID_ASSEMBLY_SHA256="exact-validated-digest";' in text
    assert 'const ATTACHED=true;' in text


def test_copy_and_attachment_propagate_validated_digest_to_agent(tmp_path, monkeypatch):
    digests = []
    class Script:
        def on(self, *a): pass
        def load(self): pass
        exports_sync = SimpleNamespace(health=lambda: {'copy_protocol_isolated': True})
    class Session:
        def on(self, *a): pass
        def create_script(self, text):
            digests.append(text)
            return Script()
    class Device:
        def spawn(self, *a, **kw): return 123
        def attach(self, *a): return Session()
        def resume(self, *a): pass
    native_bridge = tmp_path / 'bridge.js'
    native_bridge.write_text('// fixture', encoding='utf-8', newline='\r\n')
    subject = SimpleNamespace(lab=tmp_path, exe=tmp_path / 'VRoidStudio.exe', bridge_js=native_bridge,
                              run_dir=tmp_path / 'run', events=[], mode='copy')
    monkeypatch.setattr(bridge, '_check_copy', lambda _: 'copy-validated')
    monkeypatch.setattr(bridge, '_environment', lambda _: {})
    monkeypatch.setattr(bridge, '_probe_config', lambda _: {})
    monkeypatch.setattr(bridge, 'prepare_run_directory', lambda _: None)
    monkeypatch.setattr(bridge, 'record', lambda *a: None)
    monkeypatch.setattr(bridge.closet_guard, 'enforce', lambda _: {})
    monkeypatch.setattr(bridge.lab_lock, 'acquire', lambda _: None)
    monkeypatch.setattr(bridge.frida, 'get_local_device', lambda: Device())
    bridge.start(subject)
    assert 'const VROID_ASSEMBLY_SHA256="copy-validated";' in digests[0]
    if bridge.os.name != 'nt':
        attached = bridge.script_text(None, native_bridge, attached=True, assembly_sha256='attach-validated')
        assert 'const VROID_ASSEMBLY_SHA256="attach-validated";' in attached
        return
    monkeypatch.setattr(bridge, 'find_open_vroid', lambda _: [{'pid': 123, 'path': str(subject.exe)}])
    monkeypatch.setattr(bridge, 'assembly_identity', lambda _: {'sha256': 'attach-validated', 'build': 'fixture'})
    bridge.attach(subject, 123)
    assert 'const VROID_ASSEMBLY_SHA256="attach-validated";' in digests[1]
