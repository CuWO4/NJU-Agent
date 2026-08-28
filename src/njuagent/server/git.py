"""Git integration for the sidebar (status, init, commit).

This is a product feature: the user drives these operations from the UI.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any


class GitError(Exception):
    pass


async def _git(workdir: str, *args: str) -> tuple[str, int]:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=workdir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    out = (stdout or b"").decode(errors="replace") + (stderr or b"").decode(errors="replace")
    return out, proc.returncode


async def git_status(workdir: str) -> dict[str, Any]:
    if not (Path(workdir) / ".git").exists():
        return {"initialized": False, "branch": None, "changes": []}
    output, _code = await _git(workdir, "status", "--porcelain=v1", "--branch")
    branch: str | None = None
    changes: list[dict[str, str]] = []
    for line in output.splitlines():
        if line.startswith("##"):
            branch = line[3:].split("...")[0].strip() or None
            continue
        if len(line) > 3:
            changes.append({"path": line[3:], "status": line[:2].strip() or "??"})
    return {"initialized": True, "branch": branch, "changes": changes}


async def git_init(workdir: str) -> dict[str, Any]:
    output, code = await _git(workdir, "init")
    if code != 0:
        raise GitError(output.strip())
    return {"ok": True, "output": output.strip()}


async def git_commit(workdir: str, message: str) -> dict[str, Any]:
    if not message.strip():
        raise GitError("commit message is empty")
    add_out, add_code = await _git(workdir, "add", "-A")
    if add_code != 0:
        raise GitError(add_out.strip())
    commit_out, commit_code = await _git(workdir, "commit", "-m", message)
    if commit_code != 0:
        raise GitError(commit_out.strip())
    return {"ok": True, "output": commit_out.strip()}
