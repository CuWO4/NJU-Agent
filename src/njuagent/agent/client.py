"""Direct REST client for the DeepSeek OpenAI-compatible chat completions API.

Uses httpx only as an HTTP transport; request construction, stream parsing,
retries and error handling are implemented here.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

import httpx

from .parser import Completion, ParseError, StreamParser

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
DEFAULT_TIMEOUT = 180.0


class ApiError(Exception):
    """Raised when the model API fails after retries are exhausted."""


class DeepSeekClient:
    """Minimal streaming client for an OpenAI-compatible chat endpoint."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = 3,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        on_content: Callable[[str], None] | None = None,
    ) -> Completion:
        """Send a chat request and return the accumulated completion.

        `on_content` is invoked for each streamed text chunk (for live UI
        updates); tool-call chunks are accumulated internally.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
        if max_tokens:
            payload["max_tokens"] = max_tokens
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if not self.api_key:
            raise ApiError(
                "API key is not configured. Set it in the app Settings "
                "(or via DEEPSEEK_API_KEY)."
            )

        async with httpx.AsyncClient(timeout=self.timeout) as http:
            for attempt in range(self.max_retries + 1):
                try:
                    return await self._stream_once(http, payload, headers, on_content)
                except ApiError as exc:
                    if attempt >= self.max_retries:
                        raise
                    delay = 2**attempt
                    logger.warning(
                        "API error (attempt %d/%d): %s; retrying in %ss",
                        attempt + 1,
                        self.max_retries + 1,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)

    async def _stream_once(
        self,
        http: httpx.AsyncClient,
        payload: dict[str, Any],
        headers: dict[str, str],
        on_content: Callable[[str], None] | None = None,
    ) -> Completion:
        parser = StreamParser()
        try:
            async with http.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            ) as resp:
                if resp.status_code in RETRYABLE_STATUS:
                    raise ApiError(f"HTTP {resp.status_code}")
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if not data:
                        continue
                    if data == "[DONE]":
                        break
                    parser.feed(data, on_content)
        except (httpx.HTTPError, ParseError) as exc:
            raise ApiError(str(exc)) from exc
        return parser.result()
