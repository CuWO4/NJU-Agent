"""Sub-agent tool: run an isolated agent with a special system prompt.

Sub-agents are invisible to the user. Unless the session is in auto-approve
mode, any tool requiring approval is denied for sub-agents (per their system
prompt). Sub-agents share the client, tool registry and pending-change store.

The agent-core imports here are deferred to function scope to avoid a circular
import (tools/__init__ -> agents -> agent.loop -> tools.fs).
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from ..approval import ApprovalDenied
from ..store.snapshots import PendingChanges


class SubAgentGate:
    """Approval gate for sub-agents: deny anything requiring approval unless
    the session is in auto-approve mode."""

    def __init__(self, parent: "ApprovalGate") -> None:
        self.parent = parent

    def is_auto(self) -> bool:
        return self.parent.is_auto()

    async def request(
        self,
        tool_name: str,
        arguments: str,
        *,
        auto_approved: bool = False,
    ) -> None:
        if auto_approved or self.parent.is_auto():
            return
        raise ApprovalDenied(
            "tool call denied for sub-agent: requires approval"
        )


def run_subagent_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "run_subagent",
            "description": (
                "Run an isolated sub-agent with a special system prompt to "
                "complete a sub-task, and return its final report. Sub-agents "
                "cannot run commands or touch files outside the working "
                "directory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "The sub-task for the sub-agent.",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Optional additional instructions appended to the sub-agent's system prompt.",
                    },
                },
                "required": ["task"],
            },
        },
    }


def make_run_subagent_impl(
    client: "DeepSeekClient",
    workdir: str,
    pending: PendingChanges,
    approval: "ApprovalGate",
    registry: "ToolRegistry",
) -> Callable[[dict[str, Any]], Awaitable[str]]:
    from ..agent.loop import AgentLoop
    from ..agent.prompts import SUBAGENT_SYSTEM_PROMPT
    from ..agent.session import Session

    async def impl(args: dict[str, Any]) -> str:
        task = args["task"]
        custom = args.get("prompt")
        prompt = SUBAGENT_SYSTEM_PROMPT
        if custom:
            prompt += f"\n\nAdditional instructions:\n{custom}"
        sub_session = Session(workdir, prompt)
        gate = SubAgentGate(approval)
        loop = AgentLoop(sub_session, client, registry, gate, pending)
        return await loop.run(task)

    return impl
