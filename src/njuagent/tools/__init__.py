"""Tool registry assembly for a working directory."""

from __future__ import annotations

from ..agent.client import DeepSeekClient
from ..approval import ApprovalGate
from ..store.snapshots import PendingChanges
from . import agents, command, fs, search
from .registry import ToolRegistry


def build_tool_registry(
    workdir: str,
    pending: PendingChanges,
    client: DeepSeekClient | None = None,
    approval: ApprovalGate | None = None,
) -> ToolRegistry:
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
    if client is not None and approval is not None:
        reg.register(
            agents.run_subagent_schema(),
            agents.make_run_subagent_impl(client, workdir, pending, approval, reg),
            ui_name="run sub-agent",
            ui_args=["task"],
        )
    return reg
