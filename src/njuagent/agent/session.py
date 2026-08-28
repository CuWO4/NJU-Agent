"""Conversation state for one session (one working directory)."""

from __future__ import annotations

from typing import Any

from .parser import Completion


def sanitize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop trailing incomplete tool-call sequences.

    If the loop is stopped mid-iteration, an assistant message with tool_calls
    may lack the matching tool results. The model API rejects such sequences
    with 400. Truncate from the first incomplete assistant tool-call message.
    """
    i = len(messages)
    while i > 0:
        i -= 1
        msg = messages[i]
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            calls = msg["tool_calls"]
            j = i + 1
            tool_count = 0
            while j < len(messages) and messages[j].get("role") == "tool":
                tool_count += 1
                j += 1
            if tool_count < len(calls):
                return messages[:i]
    return messages


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
