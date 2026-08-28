"""Unit tests for the agent loop with a fake model client."""

import asyncio
from pathlib import Path

from njuagent.agent.loop import AgentLoop
from njuagent.agent.parser import Completion, StreamedMessage, ToolCall
from njuagent.agent.prompts import build_main_prompt
from njuagent.agent.session import Session
from njuagent.approval import ApprovalGate
from njuagent.store.snapshots import PendingChanges
from njuagent.tools import build_tool_registry


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requested_messages = []

    async def chat(self, messages, tools=None, max_tokens=None):
        self.requested_messages.append(list(messages))
        return self.responses.pop(0)


def _text_completion(content):
    return Completion(message=StreamedMessage(content=content), finish_reason="stop")


def _tool_completion(*calls):
    return Completion(
        message=StreamedMessage(tool_calls=list(calls)), finish_reason="tool_calls"
    )


def _run(coro):
    return asyncio.run(coro)


def test_loop_ends_on_no_tool_calls(tmp_path: Path):
    client = FakeClient([_text_completion("done")])
    loop = AgentLoop(
        Session(str(tmp_path), build_main_prompt()),
        client,
        build_tool_registry(str(tmp_path), PendingChanges()),
        ApprovalGate(),
        PendingChanges(),
    )
    result = _run(loop.run("hello"))
    assert result == "done"
    # user message was added
    assert loop.session.messages[1] == {"role": "user", "content": "hello"}


def test_loop_executes_tool_then_ends(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("v1", encoding="utf-8")
    client = FakeClient(
        [
            _tool_completion(
                ToolCall(index=0, id="c1", name="read_file", arguments='{"path":"a.txt"}')
            ),
            _text_completion("I read it."),
        ]
    )
    loop = AgentLoop(
        Session(str(tmp_path), build_main_prompt()),
        client,
        build_tool_registry(str(tmp_path), PendingChanges()),
        ApprovalGate(),
        PendingChanges(),
    )
    result = _run(loop.run("read a.txt"))
    assert result == "I read it."
    roles = [m["role"] for m in loop.session.messages]
    assert roles == ["system", "user", "assistant", "tool", "assistant"]
    # tool result contains file content
    tool_msg = loop.session.messages[3]
    assert tool_msg["role"] == "tool"
    assert "v1" in tool_msg["content"]


def test_loop_stop_event_aborts(tmp_path: Path):
    client = FakeClient(
        [
            _tool_completion(
                ToolCall(index=0, id="c1", name="list_dir", arguments="{}")
            )
        ]
    )
    stop = asyncio.Event()
    loop = AgentLoop(
        Session(str(tmp_path), build_main_prompt()),
        client,
        build_tool_registry(str(tmp_path), PendingChanges()),
        ApprovalGate(),
        PendingChanges(),
        stop_event=stop,
    )
    stop.set()
    result = _run(loop.run("hi"))
    assert result == "(stopped by user)"
