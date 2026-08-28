"""Shared shell session: user and agent commands run through one session.

Commands are serialized, recorded in a history, and can be interrupted
(kill the running process) from the UI. This is the "shared shell" behind the
Ctrl+` panel.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import time
import uuid
from typing import Any

DEFAULT_TIMEOUT = 120.0


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


def _decode(data: bytes) -> str:
    if not data:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("gbk", errors="replace")


class ShellSession:
    def __init__(self, workdir: str) -> None:
        self.workdir = workdir
        self.history: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._proc: asyncio.subprocess.Process | None = None

    @property
    def running(self) -> bool:
        return self._proc is not None

    async def run(
        self,
        command: str,
        source: str = "agent",
        timeout: float = DEFAULT_TIMEOUT,
    ) -> dict[str, Any]:
        """Run a command; returns its history entry (with output)."""
        async with self._lock:
            entry: dict[str, Any] = {
                "id": uuid.uuid4().hex,
                "source": source,
                "command": command,
                "output": "",
                "exit_code": None,
                "status": "running",
                "ts": time.time(),
            }
            self.history.append(entry)
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=self.workdir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._proc = proc
            timed_out = False
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                await _kill_tree(proc)
                stdout, stderr = await proc.communicate()
                timed_out = True
            finally:
                self._proc = None
            entry["output"] = _decode(stdout or b"") + _decode(stderr or b"")
            entry["exit_code"] = proc.returncode
            entry["status"] = "timeout" if timed_out else "done"
            return entry

    async def stop(self) -> None:
        """Interrupt the currently running command, if any."""
        if self._proc is not None:
            await _kill_tree(self._proc)
