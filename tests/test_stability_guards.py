import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from vroid_mcp import closet_guard, lab_lock


def test_closet_guard_clear_raises_when_it_exports_nothing(tmp_path):
    guard = closet_guard
    calls = []

    def absent():
        return False

    original = guard.present
    guard.present = absent
    try:
        assert guard.enforce(tmp_path) == {'closet_key': 'absent', 'key': guard.KEY}
    finally:
        guard.present = original

    assert calls == []


def test_closet_guard_refuses_to_launch_when_key_present(tmp_path):
    original = closet_guard.present
    closet_guard.present = lambda: True
    try:
        with pytest.raises(RuntimeError) as error:
            closet_guard.enforce(tmp_path)
    finally:
        closet_guard.present = original
    message = str(error.value)
    assert 'VROID_CLOSET_CRASH_KEY' in message
    assert 'Nothing was launched' in message
    assert 'reg delete "HKCU\\SOFTWARE\\Classes\\vroid.closet" /f' in message


def test_closet_guard_clears_to_a_lab_backup_when_explicitly_allowed(tmp_path, monkeypatch):
    state = {'present': True}
    original_present = closet_guard.present
    original_export = closet_guard._export
    original_delete = closet_guard._delete
    closet_guard.present = lambda: state['present']

    def export(destination):
        pathlib.Path(destination).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(destination).write_text('Windows Registry Editor Version 5.00\n', encoding='utf-8')

    def delete():
        state['present'] = False

    closet_guard._export = export
    closet_guard._delete = delete
    try:
        result = closet_guard.enforce(tmp_path, clear_when_present=True)
    finally:
        closet_guard.present = original_present
        closet_guard._export = original_export
        closet_guard._delete = original_delete

    assert result['closet_key'] == 'removed'
    backup = pathlib.Path(result['backup'])
    assert backup.is_file()
    assert backup.parent == tmp_path / 'crash-guard'
    assert backup.read_text(encoding='utf-8').startswith('Windows Registry Editor')


@pytest.mark.skipif(os.name != 'nt', reason='Windows byte-range locking')
def test_lab_lock_refuses_a_second_owner_and_names_the_pid(tmp_path):
    handle = lab_lock.acquire(tmp_path)
    try:
        with pytest.raises(RuntimeError) as error:
            lab_lock.acquire(tmp_path)
        assert str(os.getpid()) in str(error.value)
        assert '.mcp-owner.lock' in str(error.value)
    finally:
        lab_lock.release(handle)
    again = lab_lock.acquire(tmp_path)
    try:
        assert lab_lock.owner(tmp_path) == str(os.getpid())
    finally:
        lab_lock.release(again)
