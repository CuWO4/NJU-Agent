"""Command execution tool: run a shell command through the shared shell session."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from .shell import DEFAULT_TIMEOUT, ShellSession


def run_command_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command in the working directory and return its output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The shell command to run."},
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 120).",
                    },
                },
                "required": ["command"],
            },
        },
    }


def make_run_command_impl(shell: ShellSession) -> Callable[[dict[str, Any]], Awaitable[str]]:
    async def impl(args: dict[str, Any]) -> str:
        command = args["command"]
        timeout = float(args.get("timeout", DEFAULT_TIMEOUT))
        entry = await shell.run(command, source="agent", timeout=timeout)
        text = entry["output"]
        if entry["status"] == "timeout":
            return f"Command timed out after {timeout:.0f}s and was killed.\n{text}"
        if entry["exit_code"] != 0:
            return f"Command failed (exit code {entry['exit_code']}).\n{text}"
        return text.strip() or "(no output)"

    return impl
