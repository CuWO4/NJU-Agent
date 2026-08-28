"""Unit tests for the local tools (fs, command, search, registry)."""

import asyncio
from pathlib import Path

import pytest

from njuagent.store.snapshots import PendingChanges
from njuagent.tools import build_tool_registry
from njuagent.tools.registry import ToolRegistry


def _run(coro):
    return asyncio.run(coro)


def test_registry_executes_registered_tool(tmp_path: Path):
    reg = build_tool_registry(str(tmp_path), PendingChanges())
    out = _run(reg.execute("list_dir", "{}"))
    assert isinstance(out, str)


def test_registry_unknown_tool_returns_error(tmp_path: Path):
    reg = build_tool_registry(str(tmp_path), PendingChanges())
    out = _run(reg.execute("nope", "{}"))
    assert out.startswith("Error: unknown tool")


def test_registry_bad_arguments_json_returns_error(tmp_path: Path):
    reg = build_tool_registry(str(tmp_path), PendingChanges())
    out = _run(reg.execute("list_dir", "{oops"))
    assert out.startswith("Error: invalid arguments JSON")


def test_read_write_list_roundtrip(tmp_path: Path):
    reg = build_tool_registry(str(tmp_path), PendingChanges())
    out = _run(reg.execute("write_file", '{"path":"sub/x.py","content":"print(1)\\n"}'))
    assert "Wrote" in out
    out = _run(reg.execute("read_file", '{"path":"sub/x.py"}'))
    assert out == "print(1)\n"
    out = _run(reg.execute("list_dir", '{"path":"."}'))
    assert "sub/" in out or "sub" in out


def test_write_file_records_pending(tmp_path: Path):
    pending = PendingChanges()
    reg = build_tool_registry(str(tmp_path), pending)
    f = tmp_path / "a.txt"
    f.write_text("v1", encoding="utf-8")
    _run(reg.execute("write_file", '{"path":"a.txt","content":"v2"}'))
    assert pending.is_pending(str(f))
    assert f.read_text(encoding="utf-8") == "v2"


def test_write_new_file_records_pending_and_rollback_deletes(tmp_path: Path):
    pending = PendingChanges()
    reg = build_tool_registry(str(tmp_path), pending)
    f = tmp_path / "new.txt"
    _run(reg.execute("write_file", '{"path":"new.txt","content":"hello"}'))
    assert pending.is_pending(str(f))
    assert f.read_text(encoding="utf-8") == "hello"
    pending.rollback(str(f))
    assert not f.exists()


def test_search_glob_and_content(tmp_path: Path):
    reg = build_tool_registry(str(tmp_path), PendingChanges())
    (tmp_path / "one.py").write_text("def foo():\n    pass\n", encoding="utf-8")
    (tmp_path / "two.txt").write_text("nothing here\n", encoding="utf-8")
    out = _run(reg.execute("search", '{"pattern":"*.py"}'))
    assert "one.py" in out
    out = _run(reg.execute("search", '{"query":"foo"}'))
    assert "one.py:1:" in out


def test_run_command_captures_output(tmp_path: Path):
    reg = build_tool_registry(str(tmp_path), PendingChanges())
    out = _run(reg.execute("run_command", '{"command":"echo hello"}'))
    assert "hello" in out


def test_run_command_failure_returns_exit_code(tmp_path: Path):
    reg = build_tool_registry(str(tmp_path), PendingChanges())
    out = _run(reg.execute("run_command", '{"command":"exit 3"}'))
    assert "exit code 3" in out


def test_ui_info_returns_display_fields(tmp_path: Path):
    reg = build_tool_registry(str(tmp_path), PendingChanges())
    info = reg.ui_info("run_command", '{"command":"python --version"}')
    assert info["ui_name"] == "run command"
    assert info["ui_args"] == ["python --version"]
    info = reg.ui_info("list_dir", "{}")
    assert info["ui_name"] == "list directory"
    assert info["ui_args"] == []
    info = reg.ui_info("write_file", '{"path":"a.py","content":"secret"}')
    assert info["ui_args"] == ["a.py"]
    info = reg.ui_info("nope", "{}")
    assert info["ui_name"] == "nope"
