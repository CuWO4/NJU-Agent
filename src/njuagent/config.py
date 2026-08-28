"""Configuration loaded from environment variables and an optional .env file.

Credentials are provided via environment variables or an untracked .env file;
they must never be committed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(RuntimeError):
    """Raised when required configuration is missing."""


def _load_dotenv(path: str | Path | None = None) -> None:
    """Load KEY=VALUE pairs from a .env file into os.environ (no override).

    Minimal parser: one KEY=VALUE per line; blank lines and lines starting
    with '#' are ignored.
    """
    env_path = Path(path) if path is not None else Path.cwd() / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


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
    """Load config from the environment, falling back to a .env file in the CWD."""
    _load_dotenv()
    key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("NJUAGENT_API_KEY")
    if not key:
        raise ConfigError(
            "DEEPSEEK_API_KEY is not set. Set it in the environment or in a "
            ".env file next to the working directory."
        )
    return Config(
        api_key=key,
        base_url=os.environ.get("NJUAGENT_BASE_URL", "https://api.deepseek.com"),
        model=os.environ.get("NJUAGENT_MODEL", "deepseek-chat"),
        context_limit=_env_int("NJUAGENT_CONTEXT_LIMIT", 1_000_000),
    )
