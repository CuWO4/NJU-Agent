"""Unit tests for session persistence (SessionStore) and pending dump/restore."""

from pathlib import Path

from njuagent.store.persistence import SessionStore
from njuagent.store.snapshots import PendingChanges


def test_session_store_roundtrip(tmp_path: Path):
    store = SessionStore(str(tmp_path))
    store.save_meta({"auto_approve": True, "plan_mode": False})
    store.save_messages(
        [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hello"},
        ]
    )
    store.save_pending({"a.txt": "v1"})

    assert store.load_meta() == {"auto_approve": True, "plan_mode": False}
    assert store.load_messages() == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
    ]
    assert store.load_pending() == {"a.txt": "v1"}


def test_session_store_missing_returns_empty(tmp_path: Path):
    store = SessionStore(str(tmp_path / "nope"))
    assert store.load_meta() == {}
    assert store.load_messages() == []
    assert store.load_pending() == {}


def test_pending_dump_restore_roundtrip(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("v1", encoding="utf-8")
    pending = PendingChanges()
    pending.record(str(f), "v1")

    restored = PendingChanges()
    restored.restore(pending.dump())
    assert restored.is_pending(str(f))
    assert restored.snapshot_of(str(f)) == "v1"


def test_pending_on_change_callback(tmp_path: Path):
    calls = []
    pending = PendingChanges(on_change=lambda: calls.append(1))
    f = tmp_path / "a.txt"
    f.write_text("v1", encoding="utf-8")
    pending.record(str(f), "v1")
    pending.accept(str(f))
    assert len(calls) == 2
