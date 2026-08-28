"""Unit tests for config loading (.env fallback)."""

import pytest

from njuagent.config import ConfigError, load_config


def test_dotenv_loading(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        'DEEPSEEK_API_KEY=sk-test-123\nNJUAGENT_MODEL="deepseek-chat"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("NJUAGENT_API_KEY", raising=False)
    monkeypatch.delenv("NJUAGENT_MODEL", raising=False)
    c = load_config()
    assert c.api_key == "sk-test-123"
    assert c.model == "deepseek-chat"
    assert c.base_url == "https://api.deepseek.com"


def test_environment_overrides_dotenv(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=sk-from-file\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-from-env")
    c = load_config()
    assert c.api_key == "sk-from-env"


def test_missing_key_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("NJUAGENT_API_KEY", raising=False)
    with pytest.raises(ConfigError):
        load_config()
