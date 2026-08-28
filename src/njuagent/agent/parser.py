"""Streaming SSE parser for OpenAI-compatible chat completions.

The DeepSeek chat completions endpoint returns Server-Sent Events when
`stream=true`. Each event is a `data:` line holding one JSON chunk. Tool-call
chunks arrive incrementally: the function name and arguments are split across
many chunks and must be accumulated here (this is the self-implemented "model
output parsing" of the task requirements).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


class ParseError(Exception):
    """Raised when a streamed chunk is malformed."""


@dataclass
class ToolCall:
    index: int
    id: str = ""
    name: str = ""
    arguments: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments},
        }


@dataclass
class StreamedMessage:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class Completion:
    id: str | None = None
    message: StreamedMessage = field(default_factory=StreamedMessage)
    finish_reason: str | None = None
    usage: dict | None = None


class StreamParser:
    """Accumulates SSE chunks into a single Completion object."""

    def __init__(self) -> None:
        self._id: str | None = None
        self._content_parts: list[str] = []
        self._tool_calls: dict[int, ToolCall] = {}
        self._finish_reason: str | None = None
        self._usage: dict | None = None

    def feed(self, data: str) -> None:
        """Feed one `data:` payload (already stripped of the prefix)."""
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ParseError(f"malformed SSE chunk: {data!r}") from exc

        if self._id is None:
            self._id = chunk.get("id")
        if chunk.get("usage"):
            self._usage = chunk["usage"]
        for choice in chunk.get("choices") or []:
            if choice.get("finish_reason"):
                self._finish_reason = choice["finish_reason"]
            delta = choice.get("delta") or {}
            content = delta.get("content")
            if content:
                self._content_parts.append(content)
            for tc in delta.get("tool_calls") or []:
                index = tc.get("index", 0)
                call = self._tool_calls.setdefault(index, ToolCall(index=index))
                if tc.get("id"):
                    call.id = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    call.name += fn["name"]
                if fn.get("arguments"):
                    call.arguments += fn["arguments"]

    def result(self) -> Completion:
        return Completion(
            id=self._id,
            message=StreamedMessage(
                content="".join(self._content_parts),
                tool_calls=[self._tool_calls[i] for i in sorted(self._tool_calls)],
            ),
            finish_reason=self._finish_reason,
            usage=self._usage,
        )
