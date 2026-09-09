"""Tests for the Anthropic Messages API adapter."""

from __future__ import annotations

import json

import httpx
import pytest

from reasonhound.providers.anthropic import AnthropicProvider
from reasonhound.providers.base import (
    Message,
    ProviderError,
    Role,
    StreamEventType,
    ToolCall,
    ToolResult,
    ToolSpec,
)

from .conftest import FAST_RETRY, sse

COMPLETION_BODY = {
    "content": [
        {"type": "text", "text": "found it"},
        {"type": "tool_use", "id": "toolu_1", "name": "read_file", "input": {"path": "a.py"}},
    ],
    "stop_reason": "tool_use",
    "usage": {"input_tokens": 11, "output_tokens": 4},
}


def _provider(client: httpx.Client) -> AnthropicProvider:
    return AnthropicProvider(
        api_key="test-key", model="claude-opus-5", client=client, policy=FAST_RETRY
    )


def _body(request: httpx.Request) -> dict:
    return json.loads(request.content)


# --- request shape -----------------------------------------------------------


def test_endpoint_and_headers(capture) -> None:
    client, requests = capture(httpx.Response(200, json=COMPLETION_BODY))
    _provider(client).complete([Message(role=Role.USER, content="hi")])

    request = requests[0]
    assert str(request.url) == "https://api.anthropic.com/v1/messages"
    assert request.headers["x-api-key"] == "test-key"
    assert request.headers["anthropic-version"] == "2023-06-01"


def test_temperature_is_never_sent(capture) -> None:
    """Current Claude models reject the parameter with a 400."""
    client, requests = capture(httpx.Response(200, json=COMPLETION_BODY))
    _provider(client).complete([Message(role=Role.USER, content="hi")], temperature=0.7)

    assert "temperature" not in _body(requests[0])


def test_system_param_and_system_messages_both_hoist(capture) -> None:
    client, requests = capture(httpx.Response(200, json=COMPLETION_BODY))
    _provider(client).complete(
        [
            Message(role=Role.SYSTEM, content="second"),
            Message(role=Role.USER, content="hi"),
        ],
        system="first",
    )

    body = _body(requests[0])
    assert body["system"] == "first\n\nsecond"
    assert [m["role"] for m in body["messages"]] == ["user"]


def test_adjacent_same_role_turns_are_merged(capture) -> None:
    """Anthropic rejects two turns in a row with the same role."""
    client, requests = capture(httpx.Response(200, json=COMPLETION_BODY))
    _provider(client).complete(
        [
            Message(role=Role.ASSISTANT, tool_calls=(ToolCall(id="t1", name="ls", arguments={}),)),
            Message(role=Role.TOOL, tool_results=(ToolResult(tool_call_id="t1", content="ok"),)),
            Message(role=Role.USER, content="and now?"),
        ]
    )

    body = _body(requests[0])
    assert [m["role"] for m in body["messages"]] == ["assistant", "user"]
    types = [block["type"] for block in body["messages"][1]["content"]]
    assert types == ["tool_result", "text"], f"merged blocks in the wrong order: {types}"


def test_empty_turns_are_dropped(capture) -> None:
    client, requests = capture(httpx.Response(200, json=COMPLETION_BODY))
    _provider(client).complete(
        [Message(role=Role.USER, content=""), Message(role=Role.USER, content="hi")]
    )

    assert len(_body(requests[0])["messages"]) == 1


def test_tool_spec_and_tool_call_round_trip(capture) -> None:
    client, requests = capture(httpx.Response(200, json=COMPLETION_BODY))
    _provider(client).complete(
        [
            Message(
                role=Role.ASSISTANT,
                tool_calls=(ToolCall(id="t1", name="grep", arguments={"pattern": "eval("}),),
            ),
            Message(
                role=Role.USER,
                tool_results=(ToolResult(tool_call_id="t1", content="boom", is_error=True),),
            ),
        ],
        tools=[ToolSpec(name="grep", description="search", input_schema={"type": "object"})],
    )

    body = _body(requests[0])
    assert body["tools"] == [
        {"name": "grep", "description": "search", "input_schema": {"type": "object"}}
    ]
    use = body["messages"][0]["content"][0]
    assert use == {"type": "tool_use", "id": "t1", "name": "grep", "input": {"pattern": "eval("}}
    result = body["messages"][1]["content"][0]
    assert result["type"] == "tool_result"
    assert result["tool_use_id"] == "t1"
    assert result["is_error"] is True


def test_stream_flag_is_set_only_when_streaming(capture) -> None:
    client, requests = capture(httpx.Response(200, content=sse('{"type":"message_stop"}')))
    list(_provider(client).stream([Message(role=Role.USER, content="hi")]))

    assert _body(requests[0])["stream"] is True


# --- non-streaming response --------------------------------------------------


def test_complete_parses_text_tool_calls_and_usage(capture) -> None:
    client, _ = capture(httpx.Response(200, json=COMPLETION_BODY))
    out = _provider(client).complete([Message(role=Role.USER, content="hi")])

    assert out.text == "found it"
    assert out.tool_calls == (ToolCall(id="toolu_1", name="read_file", arguments={"path": "a.py"}),)
    assert out.usage.input_tokens == 11
    assert out.usage.output_tokens == 4
    assert out.stop_reason == "tool_use"


# --- streaming ---------------------------------------------------------------

STREAM_FRAMES = (
    '{"type":"message_start","message":{"usage":{"input_tokens":9}}}',
    '{"type":"ping"}',
    '{"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}',
    '{"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"he"}}',
    '{"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"llo"}}',
    '{"type":"content_block_stop","index":0}',
    '{"type":"content_block_start","index":1,'
    '"content_block":{"type":"tool_use","id":"toolu_9","name":"grep"}}',
    '{"type":"content_block_delta","index":1,'
    '"delta":{"type":"input_json_delta","partial_json":"{\\"pattern\\":"}}',
    '{"type":"content_block_delta","index":1,'
    '"delta":{"type":"input_json_delta","partial_json":"\\"eval(\\"}"}}',
    '{"type":"content_block_stop","index":1}',
    '{"type":"message_delta","delta":{"stop_reason":"tool_use"},"usage":{"output_tokens":7}}',
    '{"type":"message_stop"}',
)


def test_stream_emits_text_then_tool_call_then_done(capture) -> None:
    client, _ = capture(httpx.Response(200, content=sse(*STREAM_FRAMES)))
    events = list(_provider(client).stream([Message(role=Role.USER, content="hi")]))

    kinds = [event.type for event in events]
    assert kinds == [
        StreamEventType.TEXT,
        StreamEventType.TEXT,
        StreamEventType.TOOL_CALL,
        StreamEventType.DONE,
    ]
    assert "".join(e.text for e in events if e.type is StreamEventType.TEXT) == "hello"


def test_stream_assembles_partial_tool_arguments(capture) -> None:
    client, _ = capture(httpx.Response(200, content=sse(*STREAM_FRAMES)))
    events = list(_provider(client).stream([Message(role=Role.USER, content="hi")]))

    call = next(e.tool_call for e in events if e.type is StreamEventType.TOOL_CALL)
    assert call == ToolCall(id="toolu_9", name="grep", arguments={"pattern": "eval("})


def test_stream_done_carries_the_assembled_completion(capture) -> None:
    client, _ = capture(httpx.Response(200, content=sse(*STREAM_FRAMES)))
    events = list(_provider(client).stream([Message(role=Role.USER, content="hi")]))

    done = events[-1].completion
    assert done is not None
    assert done.text == "hello"
    assert done.stop_reason == "tool_use"
    assert done.usage.input_tokens == 9
    assert done.usage.output_tokens == 7
    assert len(done.tool_calls) == 1


def test_stream_raises_on_unparseable_tool_arguments(capture) -> None:
    frames = (
        '{"type":"content_block_start","index":0,'
        '"content_block":{"type":"tool_use","id":"t","name":"grep"}}',
        '{"type":"content_block_delta","index":0,'
        '"delta":{"type":"input_json_delta","partial_json":"{oops"}}',
        '{"type":"content_block_stop","index":0}',
    )
    client, _ = capture(httpx.Response(200, content=sse(*frames)))

    with pytest.raises(ProviderError, match="unparseable tool arguments"):
        list(_provider(client).stream([Message(role=Role.USER, content="hi")]))


def test_stream_error_frame_raises(capture) -> None:
    frame = '{"type":"error","error":{"type":"overloaded_error","message":"busy"}}'
    client, _ = capture(httpx.Response(200, content=sse(frame)))

    with pytest.raises(ProviderError, match="busy"):
        list(_provider(client).stream([Message(role=Role.USER, content="hi")]))
