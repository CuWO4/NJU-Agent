"""Structured workspace search for the Search sidebar.

Returns matching files with line numbers, unlike the model-facing search tool
which returns plain text.
"""

from __future__ import annotations

import os
import re
from typing import Any

SKIP_DIRS = {".git", ".njuagent", "__pycache__", ".venv", "node_modules"}
MAX_FILES = 100
MAX_MATCHES_PER_FILE = 20


def search_files(
    base: str,
    query: str,
    *,
    case_sensitive: bool = False,
    whole_word: bool = False,
    regex: bool = False,
) -> list[dict[str, Any]]:
    """Return [{path, matches: [{line, text}]}] for files containing the query."""
    if not query.strip():
        return []
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = query if regex else re.escape(query)
    if whole_word:
        pattern = rf"\b{pattern}\b"
    try:
        compiled = re.compile(pattern, flags)
    except re.error:
        return []

    results: list[dict[str, Any]] = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, base)
            matches: list[dict[str, Any]] = []
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as fh:
                    for lineno, line in enumerate(fh, 1):
                        if compiled.search(line):
                            matches.append({"line": lineno, "text": line.rstrip()})
                            if len(matches) >= MAX_MATCHES_PER_FILE:
                                break
            except OSError:
                continue
            if matches:
                results.append({"path": rel, "matches": matches})
            if len(results) >= MAX_FILES:
                return results
    return results
