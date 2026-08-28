"""Tool registry assembly for a working directory."""

from __future__ import annotations

from ..store.snapshots import PendingChanges
from . import command, fs, search
from .registry import ToolRegistry


def build_tool_registry(workdir: str, pending: PendingChanges) -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(fs.list_dir_schema(), fs.make_list_dir_impl(workdir), ui_name="list directory", ui_args=["path"])
    reg.register(fs.read_file_schema(), fs.make_read_file_impl(workdir), ui_name="read file", ui_args=["path"])
    reg.register(
        fs.write_file_schema(),
        fs.make_write_file_impl(workdir, pending),
        ui_name="write file",
        ui_args=["path"],
    )
    reg.register(
        command.run_command_schema(),
        command.make_run_command_impl(workdir),
        ui_name="run command",
        ui_args=["command"],
    )
    reg.register(
        search.search_schema(),
        search.make_search_impl(workdir),
        ui_name="search files",
        ui_args=["pattern", "query", "path"],
    )
    return reg
