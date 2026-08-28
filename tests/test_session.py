"""Unit tests for session message assembly."""

from njuagent.agent.parser import Completion, StreamedMessage, ToolCall
from njuagent.agent.prompts import build_main_prompt
from njuagent.agent.session import Session, sanitize_messages


def test_session_message_structure(tmp_path):
    s = Session(str(tmp_path), build_main_prompt())
    assert s.messages[0]["role"] == "system"
    s.add_user("task")
    assert s.messages[-1] == {"role": "user", "content": "task"}
    s.add_assistant("ok")
    assert s.messages[-1] == {"role": "assistant", "content": "ok"}


def test_session_tool_calls_and_results(tmp_path):
    s = Session(str(tmp_path), build_main_prompt())
    s.add_user("go")
    comp = Completion(
        message=StreamedMessage(
            content="let me look",
            tool_calls=[ToolCall(index=0, id="c1", name="list_dir", arguments="{}")],
        ),
        finish_reason="tool_calls",
    )
    s.add_assistant_tool_calls(comp)
    assistant = s.messages[-1]
    assert assistant["tool_calls"][0]["id"] == "c1"
    assert assistant["tool_calls"][0]["function"]["name"] == "list_dir"
    s.add_tool_result("c1", "list_dir", "a.txt")
    tool = s.messages[-1]
    assert tool == {
        "role": "tool",
        "tool_call_id": "c1",
        "name": "list_dir",
        "content": "a.txt",
    }


def test_sanitize_removes_incomplete_tool_calls():
    messages = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]},
    ]
    assert sanitize_messages(messages) == messages[:2]


def test_sanitize_keeps_complete_tool_calls():
    messages = [
        {"role": "system", "content": "s"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]},
        {"role": "tool", "tool_call_id": "c1", "content": "ok"},
    ]
    assert sanitize_messages(messages) == messages


def test_sanitize_removes_partial_parallel_calls():
    messages = [
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}, {"id": "c2"}]},
        {"role": "tool", "tool_call_id": "c1", "content": "ok"},
    ]
    assert sanitize_messages(messages) == []
