"""Tests for the Ollama adapter (local models, NDJSON streaming)."""

from __future__ import annotations

import json

import httpx
import pytest

from reasonhound.providers.base import (
    Message,
    Role,
    StreamEventType,
    ToolCall,
    ToolResult,
    ToolSpec,
)
from reasonhound.providers.ollama import (
    OLLAMA_DEFAULT_HOST,
    OLLAMA_HOST_ENV,
    OllamaProvider,
    resolve_host,
)

from .conftest import FAST_RETRY, ndjson

COMPLETION_BODY = {
    "message": {
        "content": "found it",
        "tool_calls": [{"function": {"name": "grep", "arguments": {"pattern": "eval("}}}],
    },
    "done_reason": "stop",
    "prompt_eval_count": 14,
    "eval_count": 7,
}


def _provider(client: httpx.Client) -> OllamaProvider:
    return OllamaProvider(model="llama3.1", client=client, policy=FAST_RETRY)


def _body(request: httpx.Request) -> dict:
    return json.loads(request.content)


# --- host resolution ---------------------------------------------------------


def test_default_host(no_api_keys: None) -> None:
    assert resolve_host() == OLLAMA_DEFAULT_HOST


def test_host_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OLLAMA_HOST_ENV, "http://box.local:9999")
    assert resolve_host() == "http://box.local:9999"


def test_bare_host_gets_a_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    """OLLAMA_HOST is conventionally set without a scheme, which httpx rejects."""
    monkeypatch.setenv(OLLAMA_HOST_ENV, "localhost:11434")
    assert resolve_host() == "http://localhost:11434"


def test_trailing_slash_is_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OLLAMA_HOST_ENV, "http://localhost:11434/")
    assert resolve_host() == "http://localhost:11434"


def test_blank_host_falls_back_to_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OLLAMA_HOST_ENV, "   ")
    assert resolve_host() == OLLAMA_DEFAULT_HOST


# --- request shape -----------------------------------------------------------


def test_endpoint_and_no_auth_header(capture, no_api_keys: None) -> None:
    client, requests = capture(httpx.Response(200, json=COMPLETION_BODY))
    _provider(client).complete([Message(role=Role.USER, content="hi")])

    assert str(requests[0].url) == f"{OLLAMA_DEFAULT_HOST}/api/chat"
    assert "authorization" not in requests[0].headers
    assert "x-api-key" not in requests[0].headers


def test_stream_flag_is_explicit_for_a_blocking_call(capture, no_api_keys: None) -> None:
    """Ollama streams by default, so a non-streaming call must say otherwise."""
    client, requests = capture(httpx.Response(200, json=COMPLETION_BODY))
    _provider(client).complete([Message(role=Role.USER, content="hi")])

    assert _body(requests[0])["stream"] is False


def test_system_prompt_leads_the_message_list(capture, no_api_keys: None) -> None:
    client, requests = capture(httpx.Response(200, json=COMPLETION_BODY))
    _provider(client).complete([Message(role=Role.USER, content="hi")], system="be careful")

    messages = _body(requests[0])["messages"]
    assert messages[0] == {"role": "system", "content": "be careful"}


def test_options_carry_limits(capture, no_api_keys: None) -> None:
    client, requests = capture(httpx.Response(200, json=COMPLETION_BODY))
    provider = _provider(client)

    provider.complete([Message(role=Role.USER, content="hi")], max_tokens=64)
    assert _body(requests[0])["options"] == {"num_predict": 64}

    provider.complete([Message(role=Role.USER, content="hi")], temperature=0.2)
    assert _body(requests[1])["options"]["temperature"] == 0.2


def test_tool_arguments_are_sent_as_an_object(capture, no_api_keys: None) -> None:
    """Unlike OpenAI, Ollama expects the arguments object rather than a string."""
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
    assert body["messages"][0]["tool_calls"][0]["function"]["arguments"] == {"pattern": "x"}
    assert body["messages"][1] == {"role": "tool", "content": "ok", "tool_name": "grep"}
    assert body["tools"][0]["function"]["name"] == "grep"


# --- response ----------------------------------------------------------------


def test_complete_parses_message_and_counts(capture, no_api_keys: None) -> None:
    client, _ = capture(httpx.Response(200, json=COMPLETION_BODY))
    out = _provider(client).complete([Message(role=Role.USER, content="hi")])

    assert out.text == "found it"
    assert out.tool_calls == (ToolCall(id="grep-0", name="grep", arguments={"pattern": "eval("}),)
    assert out.usage.input_tokens == 14
    assert out.usage.output_tokens == 7
    assert out.stop_reason == "stop"


def test_absent_counts_default_to_zero(capture, no_api_keys: None) -> None:
    client, _ = capture(httpx.Response(200, json={"message": {"content": "hi"}}))
    out = _provider(client).complete([Message(role=Role.USER, content="hi")])

    assert out.usage.input_tokens == 0
    assert out.usage.output_tokens == 0


# --- streaming ---------------------------------------------------------------

STREAM_FRAMES = (
    '{"message":{"content":"he"},"done":false}',
    '{"message":{"content":"llo"},"done":false}',
    '{"message":{"tool_calls":[{"function":{"name":"grep","arguments":{"pattern":"eval("}}}]},'
    '"done":false}',
    '{"message":{"content":""},"done":true,"done_reason":"stop",'
    '"prompt_eval_count":5,"eval_count":10}',
)


def test_ndjson_stream_emits_text_tool_call_then_done(capture, no_api_keys: None) -> None:
    client, _ = capture(httpx.Response(200, content=ndjson(*STREAM_FRAMES)))
    events = list(_provider(client).stream([Message(role=Role.USER, content="hi")]))

    assert [e.type for e in events] == [
        StreamEventType.TEXT,
        StreamEventType.TEXT,
        StreamEventType.TOOL_CALL,
        StreamEventType.DONE,
    ]
    call = next(e.tool_call for e in events if e.type is StreamEventType.TOOL_CALL)
    assert call == ToolCall(id="grep-0", name="grep", arguments={"pattern": "eval("})


def test_stream_done_carries_the_final_counts(capture, no_api_keys: None) -> None:
    client, _ = capture(httpx.Response(200, content=ndjson(*STREAM_FRAMES)))
    events = list(_provider(client).stream([Message(role=Role.USER, content="hi")]))

    done = events[-1].completion
    assert done is not None
    assert done.text == "hello"
    assert done.stop_reason == "stop"
    assert done.usage.input_tokens == 5
    assert done.usage.output_tokens == 10


def test_model_not_found_error_says_how_to_fix_it(capture, no_api_keys: None) -> None:
    """A bare tag 404s on a real daemon, so the error must name the remedy."""
    import pytest

    from reasonhound.providers.base import ProviderError

    client, _ = capture(httpx.Response(404, json={"error": "model 'llama3.1' not found"}))

    with pytest.raises(ProviderError) as excinfo:
        _provider(client).complete([Message(role=Role.USER, content="hi")])

    assert "ollama pull llama3.1" in str(excinfo.value)
    assert "--model" in str(excinfo.value)
