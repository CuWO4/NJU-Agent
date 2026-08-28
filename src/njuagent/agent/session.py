"""Conversation state for one session (one working directory)."""

from __future__ import annotations

from typing import Any

from .parser import Completion


class Session:
    def __init__(self, workdir: str, system_prompt: str) -> None:
        self.workdir = workdir
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]

    def add_user(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_assistant(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})

    def add_assistant_tool_calls(self, completion: Completion) -> None:
        msg: dict[str, Any] = {
            "role": "assistant",
            "content": completion.message.content or None,
        }
        calls = [c.to_dict() for c in completion.message.tool_calls]
        if calls:
            msg["tool_calls"] = calls
        self.messages.append(msg)

    def add_tool_result(self, call_id: str, name: str, content: str) -> None:
        self.messages.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "name": name,
                "content": content,
            }
        )
