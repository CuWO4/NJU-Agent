"""Tool registry: schemas + local implementations.

Tool schemas follow the OpenAI function-calling format. Implementations are
async callables taking an arguments dict and returning a text result. Errors
are captured and returned as text so the model can self-correct.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

Impl = Callable[[dict[str, Any]], Awaitable[str]]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, dict[str, Any]] = {}

    def register(self, schema: dict[str, Any], impl: Impl) -> None:
        name = schema["function"]["name"]
        self._tools[name] = {"schema": schema, "impl": impl}

    def schemas(self) -> list[dict[str, Any]]:
        return [t["schema"] for t in self._tools.values()]

    def has(self, name: str) -> bool:
        return name in self._tools

    async def execute(self, name: str, arguments: str) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"Error: unknown tool '{name}'"
        try:
            args = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError as exc:
            return f"Error: invalid arguments JSON for '{name}': {exc}"
        try:
            return await tool["impl"](args)
        except Exception as exc:  # noqa: BLE001 - report to the model
            logger.warning("tool %s failed: %s", name, exc)
            return f"Error: tool '{name}' failed: {exc}"
