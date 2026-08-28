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
    ) -> None:
        self.session = session
        self.client = client
        self.registry = registry
        self.approval = approval
        self.pending = pending
        self.stop_event = stop_event or asyncio.Event()
        self.emit: Emit = emit or (lambda _event: None)
        self.on_state_change: Callable[[], None] = on_state_change or (lambda: None)
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
            calls = completion.message.tool_calls
            if not calls:
                text = completion.message.content or "(no output)"
                self.emit({"type": "message.done", "content": text})
                self.session.add_assistant(text)
                self.on_state_change()
                return text
            self.session.add_assistant_tool_calls(completion)
            self.on_state_change()
            for call in calls:
                result = await self._run_tool(call)
                self.session.add_tool_result(call.id, call.name, result)
                self.on_state_change()
        return "(stopped by user)"

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
        return result
