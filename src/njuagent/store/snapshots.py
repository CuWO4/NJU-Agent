"""Pending file changes: snapshots of unconfirmed writes, accept/rollback.

The model's write is persisted to disk immediately. Each write records the
previous content so the user can accept it (baseline moves forward) or
rollback the file to the last confirmed state. This is file-system-level and
invisible to the model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable


class PendingChanges:
    def __init__(self, on_change: Callable[[], None] | None = None) -> None:
        # path -> previous content (None means the file did not exist before)
        self._pending: dict[str, str | None] = {}
        self._on_change = on_change

    def _changed(self) -> None:
        if self._on_change is not None:
            self._on_change()

    def record(self, path: str, previous_content: str | None) -> None:
        if path not in self._pending:
            self._pending[path] = previous_content
            self._changed()

    def is_pending(self, path: str) -> bool:
        return path in self._pending

    def snapshot_of(self, path: str) -> str | None:
        """Return the previous content recorded for a pending path (None if absent)."""
        return self._pending.get(path)

    def list_pending(self) -> list[str]:
        return list(self._pending)

    def accept(self, path: str) -> None:
        if path in self._pending:
            del self._pending[path]
            self._changed()

    def accept_all(self) -> None:
        if self._pending:
            self._pending.clear()
            self._changed()

    def rollback(self, path: str) -> None:
        previous = self._pending.pop(path, None)
        if previous is None:
            Path(path).unlink(missing_ok=True)
        else:
            Path(path).write_text(previous, encoding="utf-8")
        self._changed()

    def rollback_all(self) -> None:
        for path in list(self._pending):
            self.rollback(path)

    def dump(self) -> dict[str, str | None]:
        return dict(self._pending)

    def restore(self, data: dict[str, str | None]) -> None:
        self._pending = dict(data)
