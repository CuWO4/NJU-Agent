"""Search tool: glob filename match and/or regex content search.

Pure Python implementation (no system grep dependency) so it works on any
host OS. Skips hidden directories (.git, .njuagent, __pycache__).
"""

from __future__ import annotations

import fnmatch
import os
import re
from typing import Any, Awaitable, Callable

from .fs import resolve

SKIP_DIRS = {".git", ".njuagent", "__pycache__", ".venv", "node_modules"}
MAX_RESULTS = 100


def search_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search files: match paths by glob pattern and/or match lines by regex.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern matched against file paths or names."},
                    "query": {"type": "string", "description": "Regex matched against file contents (returns 'path:line: text')."},
                    "path": {"type": "string", "description": "Directory to search in, relative to the working directory (default '.')."},
                },
                "required": [],
            },
        },
    }


def _walk(base: str):
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            yield os.path.join(root, name)


def make_search_impl(workdir: str) -> Callable[[dict[str, Any]], Awaitable[str]]:
    async def impl(args: dict[str, Any]) -> str:
        base = resolve(workdir, args.get("path", "."))
        if not base.is_dir():
            return f"Error: not a directory: {base}"
        pattern = args.get("pattern")
        query = args.get("query")
        if not pattern and not query:
            return "Error: provide 'pattern' and/or 'query'"
        results: list[str] = []
        regex = re.compile(query) if query else None
        for full in _walk(str(base)):
            rel = os.path.relpath(full, str(base))
            if pattern and not (
                fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(os.path.basename(rel), pattern)
            ):
                continue
            if regex is not None:
                try:
                    with open(full, "r", encoding="utf-8", errors="replace") as fh:
                        for lineno, line in enumerate(fh, 1):
                            if regex.search(line):
                                results.append(f"{rel}:{lineno}: {line.rstrip()}")
                except OSError:
                    continue
            else:
                results.append(rel)
            if len(results) >= MAX_RESULTS:
                break
        return "\n".join(results) if results else "(no matches)"
    return impl
