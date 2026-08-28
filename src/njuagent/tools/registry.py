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

    def register(
        self,
        schema: dict[str, Any],
        impl: Impl,
        ui_name: str | None = None,
        ui_args: list[str] | None = None,
    ) -> None:
        name = schema["function"]["name"]
        self._tools[name] = {
            "schema": schema,
            "impl": impl,
            "ui_name": ui_name or name,
            "ui_args": list(ui_args) if ui_args else None,
        }

    def schemas(self) -> list[dict[str, Any]]:
        return [t["schema"] for t in self._tools.values()]

    def has(self, name: str) -> bool:
        return name in self._tools

    def manifest(self) -> list[dict[str, Any]]:
        """UI metadata for every tool (used to render historical calls)."""
        return [
            {"name": name, "ui_name": t["ui_name"], "ui_args": t["ui_args"]}
            for name, t in self._tools.items()
        ]

    def ui_info(self, name: str, arguments: str) -> dict[str, Any]:
        """User-facing presentation for a tool call: display name and arg values.

        Only the arguments listed in `ui_args` are shown (values only, no
        keys); if `ui_args` is unset all argument values are shown.
        """
        tool = self._tools.get(name)
        if tool is None:
            return {"ui_name": name, "ui_args": [arguments]}
        try:
            args = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            return {"ui_name": tool["ui_name"], "ui_args": [arguments]}
        if not isinstance(args, dict):
            return {"ui_name": tool["ui_name"], "ui_args": [str(args)]}
        keys = tool["ui_args"] if tool["ui_args"] is not None else list(args)
        values = []
        for key in keys:
            if key in args:
                value = args[key]
                values.append(
                    value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
                )
        return {"ui_name": tool["ui_name"], "ui_args": values}

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
