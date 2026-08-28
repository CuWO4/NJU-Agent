"""The agent loop: message assembly, model call, tool execution, termination.

Termination: the model stops requesting tools (natural end) or the user
aborts (stop event). There is no forced interruption from the tool side.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Callable

from ..approval import ApprovalDenied, ApprovalGate
from ..store.snapshots import PendingChanges
from ..tools.fs import resolve
from ..tools.registry import ToolRegistry
from .client import DeepSeekClient
from .parser import ToolCall
from .session import Session, sanitize_messages

logger = logging.getLogger(__name__)

Emit = Callable[[dict[str, Any]], None]


class AgentLoop:
    def __init__(
        self,
        session: Session,
        client: DeepSeekClient,
        registry: ToolRegistry,
        approval: ApprovalGate,
        pending: PendingChanges,
        stop_event: asyncio.Event | None = None,
        emit: Emit | None = None,
        on_state_change: Callable[[], None] | None = None,
        context_limit: int = 1_000_000,
        keep_recent: int = 3,
    ) -> None:
        self.session = session
        self.client = client
        self.registry = registry
        self.approval = approval
        self.pending = pending
        self.stop_event = stop_event or asyncio.Event()
        self.emit: Emit = emit or (lambda _event: None)
        self.on_state_change: Callable[[], None] = on_state_change or (lambda: None)
        self.context_limit = context_limit
        self.keep_recent = keep_recent
        self.iterations = 0

    async def run(self, user_input: str) -> str:
        self.session.add_user(user_input)
        self.on_state_change()
        while not self.stop_event.is_set():
            self.session.messages = sanitize_messages(self.session.messages)
            self.iterations += 1
            completion = await self.client.chat(
                self.session.messages,
                tools=self.registry.schemas(),
                on_content=lambda chunk: self.emit(
                    {"type": "message.delta", "content": chunk}
                ),
            )
            if completion.usage:
                self.emit({"type": "cost", "usage": completion.usage})
            usage = completion.usage
            if isinstance(usage, dict) and usage.get("prompt_tokens", 0) > self.context_limit:
                await self._compress()
            calls = completion.message.tool_calls
            if not calls:
                text = completion.message.content or "(no output)"
                self.emit({"type": "message.done", "content": text})
                self.session.add_assistant(text)
                self.on_state_change()
                return text
            self.session.add_assistant_tool_calls(completion)
            self.on_state_change()
            results: dict[str, str] = {}

            async def run_one(call: ToolCall) -> None:
                results[call.id] = await self._run_tool(call)

            free_calls = [c for c in calls if not self._needs_approval(c)]
            blocked_calls = [c for c in calls if self._needs_approval(c)]
            if free_calls:
                await asyncio.gather(*(run_one(c) for c in free_calls))
            for call in blocked_calls:
                await run_one(call)
            for call in calls:
                self.session.add_tool_result(call.id, call.name, results[call.id])
                self.on_state_change()
        return "(stopped by user)"

    @staticmethod
    def _split_for_compression(
        messages: list[dict[str, Any]], keep_recent: int
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Split messages into (compress, keep) on whole turn boundaries.

        Tool messages are never counted toward `keep_recent`; a turn (a user
        or assistant message plus its tool results) is always kept whole so a
        tool-call block is never split.
        """
        kept: list[dict[str, Any]] = []
        visible = 0
        for msg in reversed(messages):
            kept.append(msg)
            if msg.get("role") != "tool":
                visible += 1
                if visible >= keep_recent:
                    break
        kept.reverse()
        split = len(messages) - len(kept)
        return messages[:split], kept

    async def _compress(self) -> None:
        """Replace older messages with an API-generated summary when the
        context exceeds the limit. Keeps the system prompt and the most recent
        whole turns intact."""
        system = self.session.messages[:1]
        old, recent = self._split_for_compression(
            self.session.messages[1:], self.keep_recent
        )
        if not old:
            return
        try:
            summary = await self._summarize(old)
        except Exception as exc:  # noqa: BLE001 - compression is best-effort
            logger.warning("conversation compression failed: %s", exc)
            return
        self.session.messages = system + [
            {
                "role": "system",
                "content": f"Summary of the earlier conversation:\n{summary}",
            }
        ] + recent
        logger.info(
            "compressed conversation: %d -> %d messages",
            len(self.session.messages) + len(old),
            len(self.session.messages),
        )
        self.on_state_change()

    async def _summarize(self, messages: list[dict[str, Any]]) -> str:
        completion = await self.client.chat(
            [
                {
                    "role": "system",
                    "content": "Summarize the following conversation concisely, "
                    "preserving important details such as file paths, decisions, "
                    "and the current task state.",
                },
                *messages,
            ],
            max_tokens=1024,
        )
        return completion.message.content or ""

    def _outside_workdir(self, path: str) -> bool:
        """True if a path resolves outside the working directory."""
        if not path:
            return False
        try:
            p = resolve(self.session.workdir, path).resolve()
            wd = Path(self.session.workdir).resolve()
        except OSError:
            return True
        return not p.is_relative_to(wd)

    def _needs_approval(self, call: ToolCall) -> bool:
        """Commands and out-of-workdir file I/O require approval."""
        if self.approval.is_auto():
            return False
        if call.name == "run_command":
            return True
        if call.name in ("read_file", "write_file"):
            try:
                args = json.loads(call.arguments or "{}")
            except json.JSONDecodeError:
                return True
            return self._outside_workdir(args.get("path", ""))
        return False

    async def _run_tool(self, call: ToolCall) -> str:
        ui = self.registry.ui_info(call.name, call.arguments)
        needs_approval = self._needs_approval(call)
        if needs_approval:
            self.emit(
                {
                    "type": "tool.call",
                    "id": call.id,
                    "name": call.name,
                    "ui_name": ui["ui_name"],
                    "ui_args": ui["ui_args"],
                    "arguments": call.arguments,
                    "status": "waiting_approval",
                }
            )
            self.emit(
                {
                    "type": "approval.request",
                    "id": call.id,
                    "name": call.name,
                    "arguments": call.arguments,
                }
            )
            try:
                await self.approval.request(call.name, call.arguments)
                approved = True
            except ApprovalDenied:
                approved = False
            self.emit(
                {"type": "approval.resolved", "id": call.id, "approved": approved}
            )
            if not approved:
                return "Error: tool call was not approved by the user."
        else:
            self.emit(
                {
                    "type": "tool.call",
                    "id": call.id,
                    "name": call.name,
                    "ui_name": ui["ui_name"],
                    "ui_args": ui["ui_args"],
                    "arguments": call.arguments,
                    "status": "running",
                }
            )
        result = await self.registry.execute(call.name, call.arguments)
        self.emit(
            {"type": "tool.result", "id": call.id, "name": call.name, "output": result}
        )
        self.emit({"type": "pending.changed", "paths": self.pending.list_pending()})
        if call.name == "run_command":
            self.emit({"type": "shell.changed"})
        return result
