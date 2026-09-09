"""Ollama adapter for locally hosted models.

Wire reference: ``POST {host}/api/chat``. No API key -- the model runs on the
user's machine. Two shape differences from OpenAI, which it otherwise resembles:
tool arguments are a JSON **object** rather than a string, and the stream is
newline-delimited JSON instead of Server-Sent Events.
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Sequence
from typing import Any

import httpx

from reasonhound.providers.base import (
    Completion,
    Message,
    ProviderError,
    Role,
    StreamEvent,
    StreamEventType,
    ToolCall,
    ToolSpec,
    Usage,
)
from reasonhound.providers.http import HttpProvider, iter_ndjson

__all__ = ["OLLAMA_DEFAULT_HOST", "OLLAMA_HOST_ENV", "OllamaProvider", "resolve_host"]

OLLAMA_DEFAULT_HOST = "http://localhost:11434"
OLLAMA_HOST_ENV = "OLLAMA_HOST"


def resolve_host(host: str | None = None) -> str:
    """Return the Ollama base URL, normalizing the common bare-host form.

    ``OLLAMA_HOST`` is conventionally set without a scheme (``localhost:11434``),
    which httpx rejects, so a scheme is added when one is missing.
    """
    raw = (host if host is not None else os.environ.get(OLLAMA_HOST_ENV, "")).strip()
    if not raw:
        return OLLAMA_DEFAULT_HOST
    if "://" not in raw:
        raw = f"http://{raw}"
    return raw.rstrip("/")


class OllamaProvider(HttpProvider):
    """Speaks the Ollama chat API against a local (or self-hosted) daemon."""

    name = "ollama"

    def __init__(self, *, model: str, **kwargs: Any) -> None:
        super().__init__(model=model, base_url=resolve_host(kwargs.pop("base_url", None)), **kwargs)

    def _headers(self) -> dict[str, str]:
        return {"content-type": "application/json"}

    def _endpoint(self, *, stream: bool) -> str:
        del stream  # one endpoint; streaming is a body flag
        return f"{self.base_url}/api/chat"

    def _post(self, body: dict[str, Any], *, stream: bool) -> httpx.Response:
        # A bare connection error is unhelpful here: by far the most common cause
        # is that the daemon simply is not running.
        try:
            return super()._post(body, stream=stream)
        except ProviderError as exc:
            raise ProviderError(
                f"cannot reach Ollama at {self.base_url} ({exc}); is `ollama serve` running?"
            ) from exc

    def _error_detail(self, data: object) -> str | None:
        # "model 'x' not found" is the usual first-run failure: the tag simply is
        # not pulled yet. Say what to do about it.
        detail = super()._error_detail(data)
        if detail and "not found" in detail.lower():
            return f"{detail} -- run `ollama pull {self.model}`, or pass --model"
        return detail

    # --- request ---------------------------------------------------------------

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
        names_by_id = {call.id: call.name for message in messages for call in message.tool_calls}
        wire_messages: list[dict[str, Any]] = []
        if system:
            wire_messages.append({"role": "system", "content": system})
        for message in messages:
            wire_messages.extend(self._render_message(message, names_by_id))

        options: dict[str, Any] = {"num_predict": max_tokens}
        if temperature != 0.0:
            options["temperature"] = temperature
        body: dict[str, Any] = {
            "model": self.model,
            "messages": wire_messages,
            "options": options,
            # Ollama streams by default, so a non-streaming call must say so.
            "stream": stream,
        }
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema,
                    },
                }
                for tool in tools
            ]
        return body

    @staticmethod
    def _render_message(message: Message, names_by_id: dict[str, str]) -> list[dict[str, Any]]:
        rendered: list[dict[str, Any]] = []
        for result in message.tool_results:
            entry: dict[str, Any] = {"role": "tool", "content": result.content}
            name = names_by_id.get(result.tool_call_id)
            if name is not None:
                entry["tool_name"] = name
            rendered.append(entry)
        if message.role is Role.TOOL:
            return rendered

        role = {Role.SYSTEM: "system", Role.ASSISTANT: "assistant"}.get(message.role, "user")
        if message.content or message.tool_calls:
            entry = {"role": role, "content": message.content}
            if message.tool_calls:
                entry["tool_calls"] = [
                    {"function": {"name": call.name, "arguments": call.arguments}}
                    for call in message.tool_calls
                ]
            rendered.append(entry)
        return rendered

    # --- response --------------------------------------------------------------

    def _parse_completion(self, data: dict[str, Any]) -> Completion:
        message = data.get("message") or {}
        return Completion(
            text=str(message.get("content") or ""),
            tool_calls=tuple(_tool_calls_from_wire(message.get("tool_calls"))),
            usage=_usage_from_wire(data),
            stop_reason=data.get("done_reason"),
        )

    def _iter_events(self, response: httpx.Response) -> Iterator[StreamEvent]:
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        usage = Usage()
        stop_reason: str | None = None

        for chunk in iter_ndjson(response):
            if chunk.get("error"):
                detail = self._redactor.redact(str(chunk["error"]))
                raise ProviderError(f"ollama stream failed: {detail}")

            message = chunk.get("message") or {}
            text = message.get("content")
            if text:
                text_parts.append(str(text))
                yield StreamEvent(type=StreamEventType.TEXT, text=str(text))
            for call in _tool_calls_from_wire(message.get("tool_calls"), offset=len(tool_calls)):
                tool_calls.append(call)
                yield StreamEvent(type=StreamEventType.TOOL_CALL, tool_call=call)

            if chunk.get("done"):
                stop_reason = chunk.get("done_reason") or stop_reason
                usage = _usage_from_wire(chunk)
                break

        yield StreamEvent(
            type=StreamEventType.DONE,
            completion=Completion(
                text="".join(text_parts),
                tool_calls=tuple(tool_calls),
                usage=usage,
                stop_reason=stop_reason,
            ),
        )


def _tool_calls_from_wire(entries: object, *, offset: int = 0) -> list[ToolCall]:
    """Translate Ollama tool calls, synthesizing the ids the API does not send."""
    calls: list[ToolCall] = []
    if not isinstance(entries, list):
        return calls
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        function = entry.get("function") or {}
        name = str(function.get("name", ""))
        arguments = function.get("arguments")
        calls.append(
            ToolCall(
                id=str(entry.get("id") or f"{name}-{offset + len(calls)}"),
                name=name,
                arguments=arguments if isinstance(arguments, dict) else {},
            )
        )
    return calls


def _usage_from_wire(data: dict[str, Any]) -> Usage:
    return Usage(
        input_tokens=int(data.get("prompt_eval_count", 0) or 0),
        output_tokens=int(data.get("eval_count", 0) or 0),
    )
