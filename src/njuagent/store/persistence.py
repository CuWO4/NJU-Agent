"""Session persistence under ./.njuagent/.

One session per working directory; state lives under
`.njuagent/sessions/default/` (meta.json, messages.jsonl, pending.json).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SessionStore:
    def __init__(self, workdir: str) -> None:
        self.session_dir = Path(workdir) / ".njuagent" / "sessions" / "default"
        self.meta_path = self.session_dir / "meta.json"
        self.messages_path = self.session_dir / "messages.jsonl"
        self.pending_path = self.session_dir / "pending.json"

    def _ensure(self) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def save_meta(self, meta: dict[str, Any]) -> None:
        self._ensure()
        self.meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def load_meta(self) -> dict[str, Any]:
        if not self.meta_path.is_file():
            return {}
        try:
            return json.loads(self.meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def save_messages(self, messages: list[dict[str, Any]]) -> None:
        self._ensure()
        with open(self.messages_path, "w", encoding="utf-8") as fh:
            for msg in messages:
                fh.write(json.dumps(msg, ensure_ascii=False) + "\n")

    def load_messages(self) -> list[dict[str, Any]]:
        if not self.messages_path.is_file():
            return []
        messages: list[dict[str, Any]] = []
        with open(self.messages_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return messages

    def save_pending(self, pending: dict[str, str | None]) -> None:
        self._ensure()
        self.pending_path.write_text(
            json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def load_pending(self) -> dict[str, str | None]:
        if not self.pending_path.is_file():
            return {}
        try:
            data = json.loads(self.pending_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {}
            return {str(key): value for key, value in data.items()}
        except (json.JSONDecodeError, OSError):
            return {}
