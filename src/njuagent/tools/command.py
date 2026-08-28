"""Command execution tool: run a shell command in the working directory."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from typing import Any, Awaitable, Callable

DEFAULT_TIMEOUT = 120.0


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


async def _kill_tree(proc: asyncio.subprocess.Process) -> None:
    """Kill the process and its children on the current platform."""
    if proc.returncode is not None:
        return
    if sys.platform == "win32":
        try:
            sub = await asyncio.create_subprocess_exec(
                "taskkill", "/F", "/T", "/PID", str(proc.pid),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await sub.wait()
        except OSError:
            pass
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
    try:
        proc.kill()
    except ProcessLookupError:
        pass


def make_run_command_impl(workdir: str) -> Callable[[dict[str, Any]], Awaitable[str]]:
    async def impl(args: dict[str, Any]) -> str:
        command = args["command"]
        timeout = float(args.get("timeout", DEFAULT_TIMEOUT))
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=workdir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            await _kill_tree(proc)
            stdout, stderr = await proc.communicate()
            out = (stdout or b"").decode(errors="replace")
            err = (stderr or b"").decode(errors="replace")
            return f"Command timed out after {timeout:.0f}s and was killed.\n{out}{err}"
        out = (stdout or b"").decode(errors="replace")
        err = (stderr or b"").decode(errors="replace")
        text = out + err
        if proc.returncode != 0:
            text = f"exit code {proc.returncode}\n" + text
        return text.strip() or "(no output)"
    return impl
