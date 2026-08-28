"""The agent loop: message assembly, model call, tool execution, termination.

Termination: the model stops requesting tools (natural end) or the user
aborts (stop event). There is no forced interruption from the tool side.
"""

from __future__ import annotations

import asyncio
import logging

from ..approval import ApprovalDenied, ApprovalGate
from ..store.snapshots import PendingChanges
from ..tools.registry import ToolRegistry
from .client import DeepSeekClient
from .parser import ToolCall
from .session import Session

logger = logging.getLogger(__name__)


class AgentLoop:
    def __init__(
        self,
        session: Session,
        client: DeepSeekClient,
        registry: ToolRegistry,
        approval: ApprovalGate,
        pending: PendingChanges,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        self.session = session
        self.client = client
        self.registry = registry
        self.approval = approval
        self.pending = pending
        self.stop_event = stop_event or asyncio.Event()
        self.iterations = 0

    async def run(self, user_input: str) -> str:
        self.session.add_user(user_input)
        while not self.stop_event.is_set():
            self.iterations += 1
            completion = await self.client.chat(
                self.session.messages, tools=self.registry.schemas()
            )
            calls = completion.message.tool_calls
            if not calls:
                text = completion.message.content or "(no output)"
                self.session.add_assistant(text)
                return text
            self.session.add_assistant_tool_calls(completion)
            for call in calls:
                result = await self._run_tool(call)
                self.session.add_tool_result(call.id, call.name, result)
        return "(stopped by user)"

    async def _run_tool(self, call: ToolCall) -> str:
        try:
            await self.approval.request(call.name, call.arguments)
        except ApprovalDenied:
            return "Error: tool call was not approved by the user."
        return await self.registry.execute(call.name, call.arguments)
