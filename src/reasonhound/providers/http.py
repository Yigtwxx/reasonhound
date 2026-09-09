"""Shared HTTP machinery for the BYOK adapters.

Every adapter is the same program with a different wire format: build a JSON
body, POST it, map the response back to the provider-neutral vocabulary in
:mod:`reasonhound.providers.base`. That shared half lives here so the four
adapters only own their translation tables.

It is also the single chokepoint for the **always-on egress redaction** required
by ``docs/DESIGN.md`` section 7: the request body is passed through the redactor
in :meth:`HttpProvider._post`, so an adapter physically cannot forget to do it.

Known limitation: tool *arguments* are redacted along with everything else, so a
tool invoked with a credential-shaped argument -- ``grep(pattern="AKIA[0-9A-Z]{16}")``
is the obvious case for a secret-scanning agent -- has that argument masked and
the call silently loses its meaning. Over-redaction is the stated policy, and
the right fix is a per-tool exemption owned by ``tools/``, which does not exist
yet. Revisit when it does.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from typing import Any, Self

import httpx

from reasonhound.providers.base import (
    Completion,
    Message,
    ProviderError,
    StreamEvent,
    ToolSpec,
)
from reasonhound.providers.retry import RetryPolicy, request_with_retry
from reasonhound.security.redactor import DEFAULT_REDACTOR, Redactor

__all__ = ["DEFAULT_TIMEOUT", "HttpProvider", "iter_ndjson", "iter_sse_data"]

# Reasoning calls are slow by nature (a hunter may think for minutes), so the read
# timeout is generous while connect/write stay short enough to fail fast.
DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)

# Keys whose values are protocol plumbing, not user data: correlation ids, tool
# and model names, block/role discriminators. Redacting them would corrupt the
# conversation (a mangled tool id breaks the call/result round-trip), and they
# never carry anything the redactor exists to contain.
_STRUCTURAL_KEYS: frozenset[str] = frozenset(
    {
        "id",
        "index",
        "model",
        "name",
        "role",
        "tool_call_id",
        "tool_use_id",
        "type",
    }
)

# Whole subtrees that are Reasonhound-authored rather than user-supplied: tool
# definitions and their JSON schemas. Redacting a schema could rewrite an enum
# value or a regex example and silently change what a tool accepts.
_STRUCTURAL_SUBTREES: frozenset[str] = frozenset(
    {"functionDeclarations", "input_schema", "parameters", "tools"}
)


def iter_sse_data(response: httpx.Response) -> Iterator[str]:
    """Yield the ``data:`` payload of each Server-Sent Event in *response*.

    Only the payload is yielded; ``event:`` lines are ignored because every
    provider we speak to repeats the event type inside the JSON payload. Comment
    lines (``:`` keep-alives) and blank separators are skipped. The ``[DONE]``
    sentinel is yielded verbatim so the caller can recognize it.
    """
    for raw_line in response.iter_lines():
        line = raw_line.rstrip("\r")
        if not line or line.startswith(":"):
            continue
        if not line.startswith("data:"):
            continue
        yield line[len("data:") :].strip()


def iter_ndjson(response: httpx.Response) -> Iterator[dict[str, Any]]:
    """Yield one decoded JSON object per non-empty line (Ollama's stream format)."""
    for raw_line in response.iter_lines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"malformed NDJSON line in stream: {exc.msg}") from exc
        if isinstance(payload, dict):
            yield payload


class HttpProvider:
    """Base for the four HTTP adapters; implements :class:`.base.LLMProvider`.

    Subclasses supply the wire format through the ``_``-prefixed hooks and get
    the client lifecycle, retries, redaction, and error mapping for free.
    """

    #: Provider identifier surfaced on the object and used in error messages.
    name: str = "http"

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        policy: RetryPolicy | None = None,
        redactor: Redactor | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.policy = policy or RetryPolicy()
        self._redactor = redactor or DEFAULT_REDACTOR
        # An injected client belongs to the caller (tests pass a MockTransport
        # client); one we build ourselves is ours to close.
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout)

    # --- lifecycle ------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying client if this provider created it. Idempotent."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # --- hooks for subclasses -------------------------------------------------

    def _headers(self) -> dict[str, str]:
        """Provider-specific request headers (auth lives here, never in the body)."""
        raise NotImplementedError

    def _endpoint(self, *, stream: bool) -> str:
        """Absolute URL for a completion request."""
        raise NotImplementedError

    def _build_body(
        self,
        messages: Sequence[Message],
        *,
        system: str | None,
        tools: Sequence[ToolSpec],
        max_tokens: int,
        temperature: float,
        stream: bool,
    ) -> dict[str, Any]:
        """Translate the neutral vocabulary into this provider's request shape."""
        raise NotImplementedError

    def _parse_completion(self, data: dict[str, Any]) -> Completion:
        """Translate a non-streaming response body back into a :class:`Completion`."""
        raise NotImplementedError

    def _iter_events(self, response: httpx.Response) -> Iterator[StreamEvent]:
        """Translate a streaming response into :class:`StreamEvent` objects."""
        raise NotImplementedError

    def _error_detail(self, data: object) -> str | None:
        """Extract a human-readable message from a provider error body.

        The default handles the ``{"error": {"message": ...}}`` shape used by
        Anthropic, OpenAI, and Gemini; Ollama overrides it.
        """
        if isinstance(data, dict):
            error = data.get("error")
            if isinstance(error, dict):
                message = error.get("message")
                if isinstance(message, str):
                    return message
            if isinstance(error, str):
                return error
        return None

    # --- the LLMProvider surface ----------------------------------------------

    def complete(
        self,
        messages: Sequence[Message],
        *,
        system: str | None = None,
        tools: Sequence[ToolSpec] = (),
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> Completion:
        body = self._build_body(
            messages,
            system=system,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=False,
        )
        response = self._post(body, stream=False)
        try:
            self._raise_for_status(response)
            return self._parse_completion(self._decode(response))
        finally:
            response.close()

    def stream(
        self,
        messages: Sequence[Message],
        *,
        system: str | None = None,
        tools: Sequence[ToolSpec] = (),
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> Iterator[StreamEvent]:
        body = self._build_body(
            messages,
            system=system,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        response = self._post(body, stream=True)
        try:
            self._raise_for_status(response)
        except BaseException:
            response.close()
            raise
        return self._drain(response)

    def _drain(self, response: httpx.Response) -> Iterator[StreamEvent]:
        """Yield events from an already-opened stream, always closing it.

        Retries stop once the connection is live: the caller has begun consuming
        tokens, and replaying a half-delivered stream would duplicate text and
        double-count usage. Recovering from that belongs to the orchestrator,
        which can re-run the whole reasoning round.
        """
        try:
            yield from self._iter_events(response)
        finally:
            response.close()

    # --- internals ------------------------------------------------------------

    def _post(self, body: dict[str, Any], *, stream: bool) -> httpx.Response:
        """Send *body* with retries, after redacting it.

        Redaction is applied to the **body only**. Headers carry the API key and
        must reach the provider intact -- masking them would turn every call into
        a 401.
        """
        safe_body = self._sanitize(body)
        request = self._client.build_request(
            "POST",
            self._endpoint(stream=stream),
            headers=self._headers(),
            content=json.dumps(safe_body).encode("utf-8"),
        )
        return request_with_retry(
            lambda: self._client.send(request, stream=stream),
            policy=self.policy,
        )

    def _sanitize(self, body: dict[str, Any]) -> dict[str, Any]:
        """Mask secrets/PII in the outbound payload (the always-on egress layer).

        Everything is redacted except the structural fields listed in
        :data:`_STRUCTURAL_KEYS` and :data:`_STRUCTURAL_SUBTREES`. Those carry no
        user data, and passing them through the redactor would break the protocol
        rather than protect anything.
        """
        cleaned = self._redact_value(body)
        if not isinstance(cleaned, dict):  # pragma: no cover - the walk keeps shape
            raise ProviderError("redaction produced a non-object request body")
        return cleaned

    def _redact_value(self, value: Any) -> Any:
        """Recursively redact *value*, leaving structural fields untouched."""
        if isinstance(value, str):
            return self._redactor.redact(value)
        if isinstance(value, dict):
            return {
                key: (
                    item
                    if key in _STRUCTURAL_KEYS or key in _STRUCTURAL_SUBTREES
                    else self._redact_value(item)
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._redact_value(item) for item in value]
        return value

    def _decode(self, response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError(f"{self.name} returned a non-JSON response") from exc
        if not isinstance(payload, dict):
            raise ProviderError(f"{self.name} returned an unexpected response shape")
        return payload

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Map a non-2xx response to :class:`ProviderError`.

        The provider's own message is included so the failure is actionable, but
        it is redacted first: an echoed request can carry the very secrets the
        redactor exists to contain.
        """
        if response.is_success:
            return
        response.read()  # a streamed error body is not loaded yet
        detail: str | None = None
        try:
            detail = self._error_detail(response.json())
        except ValueError:
            detail = None
        message = f"{self.name} request failed (HTTP {response.status_code})"
        if detail:
            message = f"{message}: {self._redactor.redact(detail)}"
        raise ProviderError(message)
