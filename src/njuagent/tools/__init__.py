"""Tool registry assembly for a working directory."""

from __future__ import annotations

from ..store.snapshots import PendingChanges
from . import command, fs, search
from .registry import ToolRegistry


def build_tool_registry(workdir: str, pending: PendingChanges) -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(fs.list_dir_schema(), fs.make_list_dir_impl(workdir))
    reg.register(fs.read_file_schema(), fs.make_read_file_impl(workdir))
    reg.register(fs.write_file_schema(), fs.make_write_file_impl(workdir, pending))
    reg.register(command.run_command_schema(), command.make_run_command_impl(workdir))
    reg.register(search.search_schema(), search.make_search_impl(workdir))
    return reg
