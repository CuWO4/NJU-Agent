"""Approval gate for tools that need explicit user confirmation.

Auto-approve is a per-session toggle; sub-agents inherit the session state.
When approval is required, the loop blocks the tool until the user decides
(interactive approval is wired in at the server/UI layer).
"""

from __future__ import annotations

import asyncio
from enum import Enum


class ApprovalMode(str, Enum):
    AUTO = "auto"
    REQUIRE = "require"


class ApprovalDenied(Exception):
    """Raised when the user (or policy) denies a tool call."""


class ApprovalGate:
    def __init__(self, mode: ApprovalMode = ApprovalMode.AUTO) -> None:
        self.mode = mode
        self._waiter: asyncio.Future | None = None

    def set_mode(self, mode: ApprovalMode) -> None:
        self.mode = mode
        if mode == ApprovalMode.AUTO and self._waiter is not None and not self._waiter.done():
            self.resolve(True)

    def is_auto(self) -> bool:
        return self.mode == ApprovalMode.AUTO

    async def request(
        self,
        tool_name: str,
        arguments: str,
        *,
        auto_approved: bool = False,
    ) -> None:
        """Block until the tool call is approved; raise ApprovalDenied if not.

        In auto mode (or when `auto_approved` is set, e.g. in-dir file I/O)
        this returns immediately.
        """
        if self.mode == ApprovalMode.AUTO or auto_approved:
            return
        loop = asyncio.get_running_loop()
        self._waiter = loop.create_future()
        try:
            await self._waiter
        finally:
            self._waiter = None

    def resolve(self, approved: bool) -> None:
        if self._waiter is None or self._waiter.done():
            return
        if approved:
            self._waiter.set_result(None)
        else:
            self._waiter.set_exception(ApprovalDenied("tool call denied by user"))
