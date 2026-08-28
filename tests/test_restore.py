"""Integration test: AgentApp persists and restores full session state."""

from pathlib import Path

from njuagent.config import Config
from njuagent.server.app import AgentApp


def test_agent_app_restores_state(tmp_path: Path):
    ws = str(tmp_path)
    config = Config(api_key="sk-fake")

    app1 = AgentApp(ws, config)
    app1.auto_approve = True
    app1.plan_mode = True
    app1.session.add_user("hello")
    app1.session.add_assistant("hi there")
    f = tmp_path / "a.txt"
    f.write_text("v1", encoding="utf-8")
    app1.pending.record(str(f), "v1")
    app1._save_state()
    app1._save_settings()

    app2 = AgentApp(ws, config)
    assert app2.auto_approve is True
    assert app2.plan_mode is True
    assert app2.session.messages[1] == {"role": "user", "content": "hello"}
    assert app2.session.messages[2] == {"role": "assistant", "content": "hi there"}
    assert app2.pending.is_pending(str(f))
    assert app2.pending.snapshot_of(str(f)) == "v1"


def test_agent_app_starts_fresh_when_no_state(tmp_path: Path):
    ws = str(tmp_path)
    config = Config(api_key="sk-fake")
    app = AgentApp(ws, config)
    assert app.auto_approve is False
    assert app.plan_mode is False
    assert app.session.messages[0]["role"] == "system"
    assert app.pending.list_pending() == []
