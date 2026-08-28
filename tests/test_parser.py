"""Unit tests for the streaming SSE parser."""

import pytest

from njuagent.agent.parser import StreamParser


def _feed_all(parser, chunks):
    for c in chunks:
        parser.feed(c)


def test_plain_text_stream():
    parser = StreamParser()
    _feed_all(
        parser,
        [
            '{"id":"x","choices":[{"delta":{"content":"Hello"},"index":0}]}',
            '{"id":"x","choices":[{"delta":{"content":" world"},"index":0}]}',
            '{"id":"x","choices":[{"delta":{},"index":0,"finish_reason":"stop"}]}',
        ],
    )
    comp = parser.result()
    assert comp.message.content == "Hello world"
    assert comp.finish_reason == "stop"
    assert comp.message.tool_calls == []


def test_tool_call_incremental_accumulation():
    parser = StreamParser()
    _feed_all(
        parser,
        [
            '{"id":"x","choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"read","arguments":""}}]},"index":0}]}',
            '{"id":"x","choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\"path\\":"}}]},"index":0}]}',
            '{"id":"x","choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\\"a.txt\\"}"}}]},"index":0}]}',
            '{"id":"x","choices":[{"delta":{},"index":0,"finish_reason":"tool_calls"}]}',
        ],
    )
    comp = parser.result()
    assert len(comp.message.tool_calls) == 1
    call = comp.message.tool_calls[0]
    assert call.id == "call_1"
    assert call.name == "read"
    assert call.arguments == '{"path":"a.txt"}'


def test_multiple_parallel_tool_calls_ordered_by_index():
    parser = StreamParser()
    _feed_all(
        parser,
        [
            '{"id":"x","choices":[{"delta":{"tool_calls":[{"index":1,"id":"c2","function":{"name":"b","arguments":"{}"}}]},"index":0}]}',
            '{"id":"x","choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1","function":{"name":"a","arguments":"{}"}}]},"index":0}]}',
        ],
    )
    comp = parser.result()
    names = [c.name for c in comp.message.tool_calls]
    assert names == ["a", "b"]


def test_usage_captured():
    parser = StreamParser()
    _feed_all(
        parser,
        [
            '{"id":"x","choices":[{"delta":{"content":"ok"},"index":0}]}',
            '{"id":"x","choices":[],"usage":{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15}}',
        ],
    )
    comp = parser.result()
    assert comp.usage["total_tokens"] == 15


def test_malformed_chunk_raises():
    parser = StreamParser()
    with pytest.raises(Exception):
        parser.feed("not json")
