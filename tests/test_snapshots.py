"""Unit tests for pending-change snapshots (accept/rollback)."""

from pathlib import Path

from njuagent.store.snapshots import PendingChanges


def test_record_and_list(tmp_path: Path):
    pending = PendingChanges()
    f = tmp_path / "a.txt"
    f.write_text("v1", encoding="utf-8")
    pending.record(str(f), "v1")
    assert pending.list_pending() == [str(f)]
    assert pending.is_pending(str(f))


def test_accept_keeps_file_and_clears_pending(tmp_path: Path):
    pending = PendingChanges()
    f = tmp_path / "a.txt"
    f.write_text("v1", encoding="utf-8")
    pending.record(str(f), "v1")
    f.write_text("v2", encoding="utf-8")
    pending.accept(str(f))
    assert not pending.is_pending(str(f))
    assert f.read_text(encoding="utf-8") == "v2"


def test_rollback_restores_previous_content(tmp_path: Path):
    pending = PendingChanges()
    f = tmp_path / "a.txt"
    f.write_text("v1", encoding="utf-8")
    pending.record(str(f), "v1")
    f.write_text("v2", encoding="utf-8")
    pending.rollback(str(f))
    assert f.read_text(encoding="utf-8") == "v1"
    assert not pending.is_pending(str(f))


def test_rollback_new_file_deletes_it(tmp_path: Path):
    pending = PendingChanges()
    f = tmp_path / "new.txt"
    pending.record(str(f), None)
    f.write_text("hello", encoding="utf-8")
    pending.rollback(str(f))
    assert not f.exists()


def test_rollback_all(tmp_path: Path):
    pending = PendingChanges()
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("a1", encoding="utf-8")
    b.write_text("b1", encoding="utf-8")
    pending.record(str(a), "a1")
    pending.record(str(b), "b1")
    a.write_text("a2", encoding="utf-8")
    b.write_text("b2", encoding="utf-8")
    pending.rollback_all()
    assert a.read_text(encoding="utf-8") == "a1"
    assert b.read_text(encoding="utf-8") == "b1"
    assert pending.list_pending() == []
