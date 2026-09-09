"""Cross-cutting tests for the shared HTTP base, run against all four adapters.

The redaction cases here are the acceptance gate for the always-on egress layer
in ``docs/DESIGN.md`` section 7: they are parametrized over every adapter, so an
adapter that bypassed the base would fail them.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from reasonhound.providers.anthropic import AnthropicProvider
from reasonhound.providers.base import (
    Message,
    ProviderError,
    Role,
    ToolCall,
    ToolResult,
)
from reasonhound.providers.gemini import GeminiProvider
from reasonhound.providers.http import HttpProvider, iter_ndjson, iter_sse_data
from reasonhound.providers.ollama import OllamaProvider
from reasonhound.providers.openai import OpenAIProvider
from reasonhound.providers.retry import RetryPolicy

from .conftest import FAST_RETRY

# A tool id long enough to trip the redactor's high-entropy rule if the base did
# not exempt structural fields.
TOOL_ID = "toolu_01A09q90qw90lq917835lq9zXcVbNmQwErTy"
AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
PASSWORD_LINE = 'password = "hunter2000"'

_EMPTY_BODY: dict[str, dict[str, object]] = {
    "anthropic": {"content": [], "usage": {}},
    "openai": {"choices": [{"message": {}}]},
    "gemini": {"candidates": [{"content": {"parts": []}}]},
    "ollama": {"message": {}},
}

ProviderFactory = Callable[[httpx.Client], HttpProvider]

_FACTORIES: dict[str, ProviderFactory] = {
    "anthropic": lambda client: AnthropicProvider(
        api_key="secret-anthropic-key", model="claude-opus-5", client=client, policy=FAST_RETRY
    ),
    "openai": lambda client: OpenAIProvider(
        api_key="secret-openai-key", model="gpt-5", client=client, policy=FAST_RETRY
    ),
    "gemini": lambda client: GeminiProvider(
        api_key="secret-gemini-key", model="gemini-2.5-pro", client=client, policy=FAST_RETRY
    ),
    "ollama": lambda client: OllamaProvider(model="llama3.1", client=client, policy=FAST_RETRY),
}

ALL_PROVIDERS = sorted(_FACTORIES)


def _conversation() -> list[Message]:
    """A history that exercises every field the redactor must leave alone."""
    return [
        Message(role=Role.USER, content=f"review this:\n{PASSWORD_LINE}\nkey={AWS_KEY}"),
        Message(
            role=Role.ASSISTANT,
            content="checking",
            tool_calls=(ToolCall(id=TOOL_ID, name="read_file", arguments={"path": "app.py"}),),
        ),
        Message(
            role=Role.USER,
            tool_results=(ToolResult(tool_call_id=TOOL_ID, content=f"contents: {AWS_KEY}"),),
        ),
    ]


def _run(name: str, capture, response: httpx.Response) -> tuple[HttpProvider, httpx.Request]:
    client, requests = capture(response)
    provider = _FACTORIES[name](client)
    provider.complete(_conversation(), system=f"never leak {AWS_KEY}")
    return provider, requests[0]


# --- egress redaction --------------------------------------------------------


@pytest.mark.parametrize("name", ALL_PROVIDERS)
def test_outbound_body_is_redacted(name: str, capture) -> None:
    _, request = _run(name, capture, httpx.Response(200, json=_EMPTY_BODY[name]))
    body = request.content.decode("utf-8")

    assert AWS_KEY not in body, f"{name} leaked an AWS key to the wire"
    assert "hunter2000" not in body, f"{name} leaked a password value to the wire"
    assert "[REDACTED:" in body, f"{name} sent no redaction placeholders at all"


@pytest.mark.parametrize("name", ALL_PROVIDERS)
def test_redacted_body_is_still_valid_json(name: str, capture) -> None:
    _, request = _run(name, capture, httpx.Response(200, json=_EMPTY_BODY[name]))
    assert isinstance(json.loads(request.content), dict)


@pytest.mark.parametrize("name", ALL_PROVIDERS)
def test_tool_call_id_survives_redaction(name: str, capture) -> None:
    _, request = _run(name, capture, httpx.Response(200, json=_EMPTY_BODY[name]))
    body = request.content.decode("utf-8")

    # Gemini and Ollama key tool results by name rather than id, so the id itself
    # is only on the wire for the two that use it.
    if name in {"anthropic", "openai"}:
        assert TOOL_ID in body, f"{name} mangled a tool call id during redaction"
    assert "read_file" in body, f"{name} mangled a tool name during redaction"


@pytest.mark.parametrize("name", ALL_PROVIDERS)
def test_model_name_survives_redaction(name: str, capture) -> None:
    _, request = _run(name, capture, httpx.Response(200, json=_EMPTY_BODY[name]))
    provider = _FACTORIES[name](
        httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    )
    body = request.content.decode("utf-8")
    if name != "gemini":  # Gemini carries the model in the URL, not the body
        assert provider.model in body
    provider.close()


@pytest.mark.parametrize("name", ["anthropic", "openai", "gemini"])
def test_api_key_header_is_never_redacted(name: str, capture) -> None:
    """The key rides in a header; masking it would turn every call into a 401."""
    _, request = _run(name, capture, httpx.Response(200, json=_EMPTY_BODY[name]))
    header_blob = " ".join(request.headers.values())

    assert f"secret-{name}-key" in header_blob, f"{name} redacted its own credential"


# --- error mapping -----------------------------------------------------------


@pytest.mark.parametrize("status", [400, 401, 403, 404, 413])
def test_client_error_maps_to_provider_error(status: int, capture) -> None:
    client, requests = capture(httpx.Response(status, json={"error": {"message": "nope"}}))
    provider = _FACTORIES["anthropic"](client)

    with pytest.raises(ProviderError) as excinfo:
        provider.complete([Message(role=Role.USER, content="hi")])

    assert f"HTTP {status}" in str(excinfo.value)
    assert "nope" in str(excinfo.value)
    assert len(requests) == 1, f"a {status} must not be retried, saw {len(requests)} requests"


def test_error_detail_is_redacted(capture) -> None:
    client, _ = capture(httpx.Response(400, json={"error": {"message": f"bad key {AWS_KEY}"}}))
    provider = _FACTORIES["anthropic"](client)

    with pytest.raises(ProviderError) as excinfo:
        provider.complete([Message(role=Role.USER, content="hi")])

    assert AWS_KEY not in str(excinfo.value), "an echoed secret leaked through the error path"


def test_non_json_error_body_still_raises(capture) -> None:
    client, _ = capture(httpx.Response(500, text="<html>gateway</html>"))
    provider = _FACTORIES["anthropic"](client)

    with pytest.raises(ProviderError, match="HTTP 500"):
        provider.complete([Message(role=Role.USER, content="hi")])


def test_non_json_success_body_raises(capture) -> None:
    client, _ = capture(httpx.Response(200, text="not json"))
    provider = _FACTORIES["anthropic"](client)

    with pytest.raises(ProviderError, match="non-JSON"):
        provider.complete([Message(role=Role.USER, content="hi")])


# --- retries through the real request path -----------------------------------


def test_retryable_status_is_retried_then_succeeds(capture) -> None:
    responses = [httpx.Response(503), httpx.Response(200, json=_EMPTY_BODY["anthropic"])]
    client, requests = capture(handler=lambda request: responses.pop(0))
    provider = _FACTORIES["anthropic"](client)

    provider.complete([Message(role=Role.USER, content="hi")])

    assert len(requests) == 2, f"expected one retry, saw {len(requests)} requests"


def test_retry_exhaustion_raises_the_mapped_error(capture) -> None:
    client, requests = capture(httpx.Response(529, json={"error": {"message": "overloaded"}}))
    provider = _FACTORIES["anthropic"](client)

    with pytest.raises(ProviderError, match="HTTP 529"):
        provider.complete([Message(role=Role.USER, content="hi")])

    assert len(requests) == FAST_RETRY.max_attempts


def test_ollama_connection_failure_names_the_daemon(capture) -> None:
    def _refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client, _ = capture(handler=_refuse)
    provider = _FACTORIES["ollama"](client)

    with pytest.raises(ProviderError, match="ollama serve"):
        provider.complete([Message(role=Role.USER, content="hi")])


# --- client lifecycle --------------------------------------------------------


def test_injected_client_is_not_closed_by_the_provider(capture) -> None:
    client, _ = capture(httpx.Response(200, json=_EMPTY_BODY["anthropic"]))
    provider = _FACTORIES["anthropic"](client)

    provider.close()

    assert not client.is_closed, "a borrowed client must outlive the provider"
    client.close()


def test_owned_client_is_closed() -> None:
    provider = AnthropicProvider(api_key="k", model="claude-opus-5")
    provider.close()
    assert provider._client.is_closed


def test_close_is_idempotent() -> None:
    """The orchestrator may close a provider it already closed on a kill-switch."""
    provider = AnthropicProvider(api_key="k", model="claude-opus-5")
    provider.close()
    provider.close()
    assert provider._client.is_closed


def test_context_manager_closes_an_owned_client() -> None:
    with AnthropicProvider(api_key="k", model="claude-opus-5") as provider:
        pass
    assert provider._client.is_closed


# --- streaming behavior ------------------------------------------------------


def test_stream_raises_at_call_time_not_first_next(capture) -> None:
    """A bad request must surface where it was made, not on the first token."""
    client, _ = capture(httpx.Response(401, json={"error": {"message": "bad key"}}))
    provider = _FACTORIES["anthropic"](client)

    with pytest.raises(ProviderError, match="HTTP 401"):
        provider.stream([Message(role=Role.USER, content="hi")])


def test_abandoned_stream_closes_the_response(capture) -> None:
    body = b'data: {"type":"content_block_delta","index":0,'
    body += b'"delta":{"type":"text_delta","text":"hi"}}\n\n'
    client, _ = capture(httpx.Response(200, content=body))
    provider = _FACTORIES["anthropic"](client)

    events = provider.stream([Message(role=Role.USER, content="hi")])
    next(events)
    events.close()  # simulates the TUI kill-switch dropping the iterator


# --- line parsers ------------------------------------------------------------


def _response(body: bytes) -> httpx.Response:
    return httpx.Response(200, content=body)


def test_iter_sse_data_yields_payloads_and_skips_noise() -> None:
    body = b': keep-alive\n\nevent: ping\ndata: {"a":1}\n\ndata: [DONE]\n\n'
    assert list(iter_sse_data(_response(body))) == ['{"a":1}', "[DONE]"]


def test_iter_sse_data_tolerates_crlf_and_missing_space() -> None:
    body = b'data:{"a":1}\r\n\r\ndata: {"b":2}\r\n\r\n'
    assert list(iter_sse_data(_response(body))) == ['{"a":1}', '{"b":2}']


def test_iter_ndjson_parses_lines_and_skips_blanks() -> None:
    body = b'{"a":1}\n\n{"b":2}\n'
    assert list(iter_ndjson(_response(body))) == [{"a": 1}, {"b": 2}]


def test_iter_ndjson_raises_on_a_malformed_line() -> None:
    with pytest.raises(ProviderError, match="malformed NDJSON"):
        list(iter_ndjson(_response(b"{not json}\n")))


def test_retry_policy_is_configurable_per_provider() -> None:
    provider = AnthropicProvider(
        api_key="k", model="claude-opus-5", policy=RetryPolicy(max_attempts=9)
    )
    assert provider.policy.max_attempts == 9
    provider.close()
