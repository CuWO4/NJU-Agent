"""Unit tests for config loading (environment variables only)."""

from njuagent.config import load_config


def test_environment_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-from-env")
    monkeypatch.delenv("NJUAGENT_API_KEY", raising=False)
    monkeypatch.delenv("NJUAGENT_MODEL", raising=False)
    c = load_config()
    assert c.api_key == "sk-from-env"
    assert c.model == "deepseek-chat"
    assert c.base_url == "https://api.deepseek.com"


def test_njuagent_key_env(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("NJUAGENT_API_KEY", "sk-injected")
    c = load_config()
    assert c.api_key == "sk-injected"


def test_missing_key_returns_empty(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("NJUAGENT_API_KEY", raising=False)
    c = load_config()
    assert c.api_key == ""
