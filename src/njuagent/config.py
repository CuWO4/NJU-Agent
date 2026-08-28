"""Configuration loaded from environment variables only.

The API key is injected by the Electron shell as NJUAGENT_API_KEY when it
spawns the backend; in development set DEEPSEEK_API_KEY / NJUAGENT_API_KEY.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Config:
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    # Compression is a heavy loss, so the limit is set to the model's real
    # context size (1M tokens); it is never triggered in practice.
    context_limit: int = 1_000_000


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def load_config() -> Config:
    """Load config from environment variables only."""
    key = (
        os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("NJUAGENT_API_KEY")
        or ""
    )
    if not key:
        logger.warning(
            "no API key configured; set DEEPSEEK_API_KEY or NJUAGENT_API_KEY"
        )
    return Config(
        api_key=key,
        base_url=os.environ.get("NJUAGENT_BASE_URL", "https://api.deepseek.com"),
        model=os.environ.get("NJUAGENT_MODEL", "deepseek-chat"),
        context_limit=_env_int("NJUAGENT_CONTEXT_LIMIT", 1_000_000),
    )
