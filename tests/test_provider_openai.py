"""Tests for the OpenAI Chat Completions adapter."""

from __future__ import annotations

import json

import httpx

from reasonhound.providers.base import (
    Message,
    Role,
    StreamEventType,
    ToolCall,
    ToolResult,
    ToolSpec,
)
from reasonhound.providers.openai import OpenAIProvider

from .conftest import FAST_RETRY, sse

COMPLETION_BODY = {
    "choices": [
        {
            "message": {
                "content": "found it",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "grep", "arguments": '{"pattern": "eval("}'},
                    }
                ],
            },
            "finish_reason": "tool_calls",
        }
    ],
    "usage": {"prompt_tokens": 12, "completion_tokens": 5},
}


def _provider(client: httpx.Client) -> OpenAIProvider:
    return OpenAIProvider(api_key="test-key", model="gpt-5", client=client, policy=FAST_RETRY)


def _body(request: httpx.Request) -> dict:
    return json.loads(request.content)


# --- request shape -----------------------------------------------------------


def test_endpoint_and_bearer_auth(capture) -> None:
    client, requests = capture(httpx.Response(200, json=COMPLETION_BODY))
    _provider(client).complete([Message(role=Role.USER, content="hi")])

    assert str(requests[0].url) == "https://api.openai.com/v1/chat/completions"
    assert requests[0].headers["authorization"] == "Bearer test-key"


def test_system_prompt_leads_the_message_list(capture) -> None:
    client, requests = capture(httpx.Response(200, json=COMPLETION_BODY))
    _provider(client).complete([Message(role=Role.USER, content="hi")], system="be careful")

    messages = _body(requests[0])["messages"]
    assert messages[0] == {"role": "system", "content": "be careful"}


def test_uses_max_completion_tokens(capture) -> None:
    client, requests = capture(httpx.Response(200, json=COMPLETION_BODY))
    _provider(client).complete([Message(role=Role.USER, content="hi")], max_tokens=64)

    body = _body(requests[0])
    assert body["max_completion_tokens"] == 64
    assert "max_tokens" not in body


def test_temperature_omitted_at_the_default_and_sent_otherwise(capture) -> None:
    client, requests = capture(httpx.Response(200, json=COMPLETION_BODY))
    provider = _provider(client)

    provider.complete([Message(role=Role.USER, content="hi")])
    assert "temperature" not in _body(requests[0])

    provider.complete([Message(role=Role.USER, content="hi")], temperature=0.4)
    assert _body(requests[1])["temperature"] == 0.4


def test_tool_arguments_are_sent_as_a_json_string(capture) -> None:
    client, requests = capture(httpx.Response(200, json=COMPLETION_BODY))
    _provider(client).complete(
        [
            Message(
                role=Role.ASSISTANT,
                tool_calls=(ToolCall(id="call_1", name="grep", arguments={"pattern": "x"}),),
            )
        ],
        tools=[ToolSpec(name="grep", description="search", input_schema={"type": "object"})],
    )

    body = _body(requests[0])
    function = body["messages"][0]["tool_calls"][0]["function"]
    assert function["arguments"] == '{"pattern": "x"}', "arguments must be a string, not an object"
    assert body["tools"][0]["type"] == "function"
    assert body["tools"][0]["function"]["parameters"] == {"type": "object"}


def test_each_tool_result_becomes_its_own_message(capture) -> None:
    client, requests = capture(httpx.Response(200, json=COMPLETION_BODY))
    _provider(client).complete(
        [
            Message(
                role=Role.TOOL,
                tool_results=(
                    ToolResult(tool_call_id="call_1", content="a"),
                    ToolResult(tool_call_id="call_2", content="b"),
                ),
            )
        ]
    )

    messages = _body(requests[0])["messages"]
    assert [m["role"] for m in messages] == ["tool", "tool"]
    assert [m["tool_call_id"] for m in messages] == ["call_1", "call_2"]


def test_streaming_requests_usage(capture) -> None:
    client, requests = capture(httpx.Response(200, content=sse("[DONE]")))
    list(_provider(client).stream([Message(role=Role.USER, content="hi")]))

    body = _body(requests[0])
    assert body["stream"] is True
    assert body["stream_options"] == {"include_usage": True}


# --- non-streaming response --------------------------------------------------


def test_complete_parses_text_tool_calls_and_usage(capture) -> None:
    client, _ = capture(httpx.Response(200, json=COMPLETION_BODY))
    out = _provider(client).complete([Message(role=Role.USER, content="hi")])

    assert out.text == "found it"
    assert out.tool_calls == (ToolCall(id="call_1", name="grep", arguments={"pattern": "eval("}),)
    assert out.usage.input_tokens == 12
    assert out.usage.output_tokens == 5
    assert out.stop_reason == "tool_calls"


# --- streaming ---------------------------------------------------------------

STREAM_FRAMES = (
    '{"choices":[{"delta":{"content":"he"}}]}',
    '{"choices":[{"delta":{"content":"llo"}}]}',
    '{"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_9",'
    '"function":{"name":"grep","arguments":"{\\"pattern\\":"}}]}}]}',
    # A later fragment carries neither id nor name -- only more argument text.
    '{"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\\"eval(\\"}"}}]}}]}',
    '{"choices":[{"delta":{},"finish_reason":"tool_calls"}]}',
    '{"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":8}}',
    "[DONE]",
)


def test_stream_emits_text_then_tool_call_then_done(capture) -> None:
    client, _ = capture(httpx.Response(200, content=sse(*STREAM_FRAMES)))
    events = list(_provider(client).stream([Message(role=Role.USER, content="hi")]))

    assert [e.type for e in events] == [
        StreamEventType.TEXT,
        StreamEventType.TEXT,
        StreamEventType.TOOL_CALL,
        StreamEventType.DONE,
    ]


def test_stream_assembles_arguments_across_fragments(capture) -> None:
    client, _ = capture(httpx.Response(200, content=sse(*STREAM_FRAMES)))
    events = list(_provider(client).stream([Message(role=Role.USER, content="hi")]))

    call = next(e.tool_call for e in events if e.type is StreamEventType.TOOL_CALL)
    assert call == ToolCall(id="call_9", name="grep", arguments={"pattern": "eval("})


def test_stream_done_carries_usage_from_the_trailing_frame(capture) -> None:
    client, _ = capture(httpx.Response(200, content=sse(*STREAM_FRAMES)))
    events = list(_provider(client).stream([Message(role=Role.USER, content="hi")]))

    done = events[-1].completion
    assert done is not None
    assert done.text == "hello"
    assert done.stop_reason == "tool_calls"
    assert done.usage.input_tokens == 3
    assert done.usage.output_tokens == 8
