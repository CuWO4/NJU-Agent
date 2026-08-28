"""Pending file changes: snapshots of unconfirmed writes, accept/rollback.

The model's write is persisted to disk immediately. Each write records the
previous content so the user can accept it (baseline moves forward) or
rollback the file to the last confirmed state. This is file-system-level and
invisible to the model.
"""

from __future__ import annotations

import os
from pathlib import Path


class PendingChanges:
    def __init__(self) -> None:
        # path -> previous content (None means the file did not exist before)
        self._pending: dict[str, str | None] = {}

    def record(self, path: str, previous_content: str | None) -> None:
        if path not in self._pending:
            self._pending[path] = previous_content

    def is_pending(self, path: str) -> bool:
        return path in self._pending

    def snapshot_of(self, path: str) -> str | None:
        """Return the previous content recorded for a pending path (None if absent)."""
        return self._pending.get(path)

    def list_pending(self) -> list[str]:
        return list(self._pending)

    def accept(self, path: str) -> None:
        self._pending.pop(path, None)

    def accept_all(self) -> None:
        self._pending.clear()

    def rollback(self, path: str) -> None:
        previous = self._pending.pop(path, None)
        if previous is None:
            Path(path).unlink(missing_ok=True)
        else:
            Path(path).write_text(previous, encoding="utf-8")

    def rollback_all(self) -> None:
        for path in list(self._pending):
            self.rollback(path)
