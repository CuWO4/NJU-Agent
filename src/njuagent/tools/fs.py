"""File system tools: list_dir, read_file, write_file.

Paths are resolved against the working directory. Writes are persisted to
disk immediately; the previous content is handed to the pending-change store
so the user can accept or rollback later (the model is unaware of this).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Awaitable, Callable

from ..store.snapshots import PendingChanges


def resolve(workdir: str, path: str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = Path(workdir) / p
    return p


def list_dir_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List entries of a directory (relative to the working directory).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path relative to the working directory. Defaults to '.'.",
                    }
                },
                "required": [],
            },
        },
    }


def read_file_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a text file, optionally a line range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to the working directory."},
                    "start_line": {"type": "integer", "description": "1-based start line (default 1)."},
                    "end_line": {"type": "integer", "description": "Inclusive end line; omit for the rest of the file."},
                },
                "required": ["path"],
            },
        },
    }


def write_file_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file (overwrites), creating parent directories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to the working directory."},
                    "content": {"type": "string", "description": "Full new content of the file."},
                },
                "required": ["path", "content"],
            },
        },
    }


def make_list_dir_impl(workdir: str) -> Callable[[dict[str, Any]], Awaitable[str]]:
    async def impl(args: dict[str, Any]) -> str:
        base = resolve(workdir, args.get("path", "."))
        if not base.is_dir():
            return f"Error: not a directory: {base}"
        entries = sorted(os.listdir(base))
        lines = [("d " if (base / e).is_dir() else "f ") + e for e in entries]
        return "\n".join(lines) if lines else "(empty directory)"
    return impl


def make_read_file_impl(workdir: str) -> Callable[[dict[str, Any]], Awaitable[str]]:
    async def impl(args: dict[str, Any]) -> str:
        path = resolve(workdir, args["path"])
        if not path.is_file():
            return f"Error: not a file: {path}"
        start = int(args.get("start_line", 1))
        end = args.get("end_line")
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
        total = len(lines)
        sel = lines[start - 1 : end] if end else lines[start - 1 :]
        text = "".join(sel)
        if end and end < total:
            text += f"\n[... {total - end} more lines ...]"
        return text
    return impl


def make_write_file_impl(
    workdir: str, pending: PendingChanges
) -> Callable[[dict[str, Any]], Awaitable[str]]:
    async def impl(args: dict[str, Any]) -> str:
        path = resolve(workdir, args["path"])
        content = args["content"]
        path.parent.mkdir(parents=True, exist_ok=True)
        previous = path.read_text(encoding="utf-8", errors="replace") if path.exists() else None
        path.write_text(content, encoding="utf-8")
        if previous is not None:
            pending.record(str(path), previous)
        return f"Wrote {len(content)} chars to {path}"
    return impl
