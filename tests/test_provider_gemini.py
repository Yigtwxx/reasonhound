"""Tests for the Google Gemini adapter."""

from __future__ import annotations

import json

import httpx
import pytest

from reasonhound.providers.base import (
    Message,
    ProviderError,
    Role,
    StreamEventType,
    ToolCall,
    ToolResult,
    ToolSpec,
)
from reasonhound.providers.gemini import GeminiProvider

from .conftest import FAST_RETRY, sse

COMPLETION_BODY = {
    "candidates": [
        {
            "content": {
                "parts": [
                    {"text": "found it"},
                    {"functionCall": {"name": "grep", "args": {"pattern": "eval("}}},
                ]
            },
            "finishReason": "STOP",
        }
    ],
    "usageMetadata": {"promptTokenCount": 13, "candidatesTokenCount": 6},
}


def _provider(client: httpx.Client, model: str = "gemini-2.5-pro") -> GeminiProvider:
    return GeminiProvider(api_key="test-key", model=model, client=client, policy=FAST_RETRY)


def _body(request: httpx.Request) -> dict:
    return json.loads(request.content)


# --- request shape -----------------------------------------------------------


def test_non_streaming_endpoint_and_header_auth(capture) -> None:
    client, requests = capture(httpx.Response(200, json=COMPLETION_BODY))
    _provider(client).complete([Message(role=Role.USER, content="hi")])

    url = str(requests[0].url)
    assert url.endswith("/v1beta/models/gemini-2.5-pro:generateContent")
    assert requests[0].headers["x-goog-api-key"] == "test-key"


def test_api_key_never_appears_in_the_url(capture) -> None:
    """httpx embeds the URL in transport errors, so a ?key= would leak it."""
    client, requests = capture(httpx.Response(200, json=COMPLETION_BODY))
    _provider(client).complete([Message(role=Role.USER, content="hi")])

    assert "test-key" not in str(requests[0].url)


def test_streaming_endpoint_requests_sse(capture) -> None:
    client, requests = capture(httpx.Response(200, content=sse('{"candidates":[]}')))
    list(_provider(client).stream([Message(role=Role.USER, content="hi")]))

    assert str(requests[0].url).endswith(":streamGenerateContent?alt=sse")


def test_model_prefix_is_stripped_and_escaped(capture) -> None:
    client, requests = capture(httpx.Response(200, json=COMPLETION_BODY))
    _provider(client, model="models/gemini-2.5-pro").complete(
        [Message(role=Role.USER, content="hi")]
    )

    assert "models/models" not in str(requests[0].url)


def test_assistant_role_is_renamed_to_model(capture) -> None:
    client, requests = capture(httpx.Response(200, json=COMPLETION_BODY))
    _provider(client).complete(
        [
            Message(role=Role.USER, content="hi"),
            Message(role=Role.ASSISTANT, content="hello"),
        ]
    )

    assert [c["role"] for c in _body(requests[0])["contents"]] == ["user", "model"]


def test_system_prompt_becomes_system_instruction(capture) -> None:
    client, requests = capture(httpx.Response(200, json=COMPLETION_BODY))
    _provider(client).complete([Message(role=Role.USER, content="hi")], system="be careful")

    body = _body(requests[0])
    assert body["systemInstruction"] == {"parts": [{"text": "be careful"}]}
    assert all(c["role"] != "system" for c in body["contents"])


def test_generation_config_carries_limits(capture) -> None:
    client, requests = capture(httpx.Response(200, json=COMPLETION_BODY))
    provider = _provider(client)

    provider.complete([Message(role=Role.USER, content="hi")], max_tokens=64)
    assert _body(requests[0])["generationConfig"] == {"maxOutputTokens": 64}

    provider.complete([Message(role=Role.USER, content="hi")], temperature=0.3)
    assert _body(requests[1])["generationConfig"]["temperature"] == 0.3


def test_tool_result_resolves_the_tool_name_from_history(capture) -> None:
    """Gemini keys a functionResponse by tool name, but ToolResult only has an id."""
    client, requests = capture(httpx.Response(200, json=COMPLETION_BODY))
    _provider(client).complete(
        [
            Message(
                role=Role.ASSISTANT,
                tool_calls=(ToolCall(id="t1", name="grep", arguments={"pattern": "x"}),),
            ),
            Message(role=Role.TOOL, tool_results=(ToolResult(tool_call_id="t1", content="ok"),)),
        ],
        tools=[ToolSpec(name="grep", description="search", input_schema={"type": "object"})],
    )

    body = _body(requests[0])
    assert body["contents"][0]["parts"][0]["functionCall"]["name"] == "grep"
    response_part = body["contents"][1]["parts"][0]["functionResponse"]
    assert response_part == {"name": "grep", "response": {"output": "ok"}}
    assert body["tools"][0]["functionDeclarations"][0]["name"] == "grep"


def test_tool_error_result_uses_the_error_key(capture) -> None:
    client, requests = capture(httpx.Response(200, json=COMPLETION_BODY))
    _provider(client).complete(
        [
            Message(
                role=Role.ASSISTANT, tool_calls=(ToolCall(id="t1", name="grep", arguments={}),)
            ),
            Message(
                role=Role.TOOL,
                tool_results=(ToolResult(tool_call_id="t1", content="boom", is_error=True),),
            ),
        ]
    )

    part = _body(requests[0])["contents"][1]["parts"][0]["functionResponse"]
    assert part["response"] == {"error": "boom"}


def test_orphan_tool_result_raises(capture) -> None:
    client, _ = capture(httpx.Response(200, json=COMPLETION_BODY))

    with pytest.raises(ProviderError, match="no matching call"):
        _provider(client).complete(
            [Message(role=Role.TOOL, tool_results=(ToolResult(tool_call_id="ghost", content="?"),))]
        )


# --- response ----------------------------------------------------------------


def test_complete_parses_parts_and_usage(capture) -> None:
    client, _ = capture(httpx.Response(200, json=COMPLETION_BODY))
    out = _provider(client).complete([Message(role=Role.USER, content="hi")])

    assert out.text == "found it"
    assert out.usage.input_tokens == 13
    assert out.usage.output_tokens == 6
    assert out.stop_reason == "STOP"


def test_function_call_ids_are_synthesized_deterministically(capture) -> None:
    """Gemini sends no id, so one is derived from the name and position."""
    client, _ = capture(httpx.Response(200, json=COMPLETION_BODY))
    first = _provider(client).complete([Message(role=Role.USER, content="hi")])

    client2, _ = capture(httpx.Response(200, json=COMPLETION_BODY))
    second = _provider(client2).complete([Message(role=Role.USER, content="hi")])

    assert first.tool_calls[0].id == "grep-0"
    assert first.tool_calls == second.tool_calls, "ids must be reproducible across runs"


def test_blocked_prompt_raises(capture) -> None:
    client, _ = capture(
        httpx.Response(200, json={"candidates": [], "promptFeedback": {"blockReason": "SAFETY"}})
    )

    with pytest.raises(ProviderError, match="SAFETY"):
        _provider(client).complete([Message(role=Role.USER, content="hi")])


# --- streaming ---------------------------------------------------------------

STREAM_FRAMES = (
    '{"candidates":[{"content":{"parts":[{"text":"he"}]}}]}',
    '{"candidates":[{"content":{"parts":[{"text":"llo"}]}}]}',
    '{"candidates":[{"content":{"parts":[{"functionCall":{"name":"grep",'
    '"args":{"pattern":"eval("}}}]},"finishReason":"STOP"}],'
    '"usageMetadata":{"promptTokenCount":4,"candidatesTokenCount":9}}',
)


def test_stream_emits_whole_tool_calls_in_one_frame(capture) -> None:
    client, _ = capture(httpx.Response(200, content=sse(*STREAM_FRAMES)))
    events = list(_provider(client).stream([Message(role=Role.USER, content="hi")]))

    assert [e.type for e in events] == [
        StreamEventType.TEXT,
        StreamEventType.TEXT,
        StreamEventType.TOOL_CALL,
        StreamEventType.DONE,
    ]
    call = next(e.tool_call for e in events if e.type is StreamEventType.TOOL_CALL)
    assert call == ToolCall(id="grep-0", name="grep", arguments={"pattern": "eval("})


def test_stream_done_carries_cumulative_usage(capture) -> None:
    client, _ = capture(httpx.Response(200, content=sse(*STREAM_FRAMES)))
    events = list(_provider(client).stream([Message(role=Role.USER, content="hi")]))

    done = events[-1].completion
    assert done is not None
    assert done.text == "hello"
    assert done.usage.input_tokens == 4
    assert done.usage.output_tokens == 9
    assert done.stop_reason == "STOP"
