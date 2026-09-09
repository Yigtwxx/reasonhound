"""Google Gemini adapter for the Generative Language API.

Wire reference: ``POST .../v1beta/models/{model}:generateContent`` and
``:streamGenerateContent?alt=sse``. Gemini differs from the other three in three
ways that shape this module: the assistant role is called ``model``, a tool
result is keyed by the tool's **name** rather than a call id, and a streamed
function call arrives as one whole object instead of a sequence of fragments.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from typing import Any
from urllib.parse import quote

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
from reasonhound.providers.http import HttpProvider, iter_sse_data

__all__ = ["GEMINI_BASE_URL", "GeminiProvider"]

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com"


class GeminiProvider(HttpProvider):
    """Speaks the Gemini ``generateContent`` API.

    The API key travels in the ``x-goog-api-key`` header, never as a ``?key=``
    query parameter: httpx embeds the request URL in transport error messages,
    so a key in the URL would leak into every traceback and log line.
    """

    name = "gemini"

    def __init__(self, *, api_key: str, model: str, **kwargs: Any) -> None:
        super().__init__(model=model, base_url=kwargs.pop("base_url", GEMINI_BASE_URL), **kwargs)
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self._api_key, "content-type": "application/json"}

    def _endpoint(self, *, stream: bool) -> str:
        model = quote(self.model.removeprefix("models/"), safe="")
        if stream:
            return f"{self.base_url}/v1beta/models/{model}:streamGenerateContent?alt=sse"
        return f"{self.base_url}/v1beta/models/{model}:generateContent"

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
        del stream  # the endpoint, not the body, selects streaming
        # A tool result must name the tool, but ToolResult only knows the call
        # id. Recover the mapping from the calls already in the history.
        names_by_id = {call.id: call.name for message in messages for call in message.tool_calls}

        system_parts = [system] if system else []
        contents: list[dict[str, Any]] = []
        for message in messages:
            if message.role is Role.SYSTEM:
                if message.content:
                    system_parts.append(message.content)
                continue
            role = "model" if message.role is Role.ASSISTANT else "user"
            parts = self._message_parts(message, names_by_id)
            if parts:
                contents.append({"role": role, "parts": parts})

        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens},
        }
        if temperature != 0.0:
            body["generationConfig"]["temperature"] = temperature
        if system_parts:
            body["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        if tools:
            body["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.input_schema,
                        }
                        for tool in tools
                    ]
                }
            ]
        return body

    @staticmethod
    def _message_parts(message: Message, names_by_id: dict[str, str]) -> list[dict[str, Any]]:
        """Render one turn as Gemini parts."""
        parts: list[dict[str, Any]] = []
        for result in message.tool_results:
            name = names_by_id.get(result.tool_call_id)
            if name is None:
                raise ProviderError(
                    f"gemini needs the tool name for result {result.tool_call_id!r}, "
                    "but no matching call is present in the history"
                )
            payload = {"error": result.content} if result.is_error else {"output": result.content}
            parts.append({"functionResponse": {"name": name, "response": payload}})
        if message.content:
            parts.append({"text": message.content})
        for call in message.tool_calls:
            parts.append({"functionCall": {"name": call.name, "args": call.arguments}})
        return parts

    # --- response --------------------------------------------------------------

    def _parse_completion(self, data: dict[str, Any]) -> Completion:
        candidates = data.get("candidates") or []
        candidate = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
        if not candidates:
            reason = (data.get("promptFeedback") or {}).get("blockReason")
            if reason:
                raise ProviderError(f"gemini blocked the prompt: {reason}")
        text_parts, tool_calls = _split_parts((candidate.get("content") or {}).get("parts") or [])
        return Completion(
            text="".join(text_parts),
            tool_calls=tuple(tool_calls),
            usage=_usage_from_wire(data.get("usageMetadata")),
            stop_reason=candidate.get("finishReason"),
        )

    def _iter_events(self, response: httpx.Response) -> Iterator[StreamEvent]:
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        usage = Usage()
        stop_reason: str | None = None

        for payload in iter_sse_data(response):
            if not payload:
                continue
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if not isinstance(chunk, dict):
                continue

            if chunk.get("usageMetadata"):
                # Cumulative across the stream, so the last one seen wins.
                usage = _usage_from_wire(chunk["usageMetadata"])

            for candidate in chunk.get("candidates") or []:
                if not isinstance(candidate, dict):
                    continue
                stop_reason = candidate.get("finishReason") or stop_reason
                parts = (candidate.get("content") or {}).get("parts") or []
                chunk_text, chunk_calls = _split_parts(parts, offset=len(tool_calls))
                for text in chunk_text:
                    text_parts.append(text)
                    yield StreamEvent(type=StreamEventType.TEXT, text=text)
                for call in chunk_calls:
                    tool_calls.append(call)
                    yield StreamEvent(type=StreamEventType.TOOL_CALL, tool_call=call)

        yield StreamEvent(
            type=StreamEventType.DONE,
            completion=Completion(
                text="".join(text_parts),
                tool_calls=tuple(tool_calls),
                usage=usage,
                stop_reason=stop_reason,
            ),
        )


def _split_parts(parts: object, *, offset: int = 0) -> tuple[list[str], list[ToolCall]]:
    """Split a ``parts`` array into text fragments and tool calls.

    Gemini returns no id for a ``functionCall``; one is synthesized from the
    tool name and its position so the call/result round-trip stays reversible
    and reproducible across runs.
    """
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    if not isinstance(parts, list):
        return text_parts, tool_calls
    for part in parts:
        if not isinstance(part, dict):
            continue
        if isinstance(part.get("text"), str) and part["text"]:
            text_parts.append(part["text"])
        call = part.get("functionCall")
        if isinstance(call, dict):
            name = str(call.get("name", ""))
            tool_calls.append(
                ToolCall(
                    id=f"{name}-{offset + len(tool_calls)}",
                    name=name,
                    arguments=call.get("args") or {},
                )
            )
    return text_parts, tool_calls


def _usage_from_wire(usage: object) -> Usage:
    if not isinstance(usage, dict):
        return Usage()
    return Usage(
        input_tokens=int(usage.get("promptTokenCount", 0) or 0),
        output_tokens=int(usage.get("candidatesTokenCount", 0) or 0),
    )
