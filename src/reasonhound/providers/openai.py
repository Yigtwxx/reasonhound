"""OpenAI adapter for the Chat Completions API.

Wire reference: ``POST https://api.openai.com/v1/chat/completions`` with bearer
auth. Tool calls arrive as ``tool_calls`` entries whose ``function.arguments``
is a JSON *string*, and tool results are their own ``role: "tool"`` messages.
"""

from __future__ import annotations

import json
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
from reasonhound.providers.http import HttpProvider, iter_sse_data

__all__ = ["OPENAI_BASE_URL", "OpenAIProvider"]

OPENAI_BASE_URL = "https://api.openai.com"
_SSE_DONE = "[DONE]"


class OpenAIProvider(HttpProvider):
    """Speaks the OpenAI Chat Completions API.

    ``temperature`` is sent only when it differs from the interface default of
    ``0.0``: the current reasoning models reject an explicit temperature, and
    omitting it keeps the default path working on every model.
    """

    name = "openai"

    def __init__(self, *, api_key: str, model: str, **kwargs: Any) -> None:
        super().__init__(model=model, base_url=kwargs.pop("base_url", OPENAI_BASE_URL), **kwargs)
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {
            "authorization": f"Bearer {self._api_key}",
            "content-type": "application/json",
        }

    def _endpoint(self, *, stream: bool) -> str:
        del stream  # one endpoint; streaming is a body flag
        return f"{self.base_url}/v1/chat/completions"

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
        wire_messages: list[dict[str, Any]] = []
        if system:
            wire_messages.append({"role": "system", "content": system})
        for message in messages:
            wire_messages.extend(self._render_message(message))

        body: dict[str, Any] = {
            "model": self.model,
            "max_completion_tokens": max_tokens,
            "messages": wire_messages,
        }
        if temperature != 0.0:
            body["temperature"] = temperature
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
        if stream:
            body["stream"] = True
            # Without this the terminal chunk carries no usage and the budget
            # ledger would see every streamed call as free.
            body["stream_options"] = {"include_usage": True}
        return body

    @staticmethod
    def _render_message(message: Message) -> list[dict[str, Any]]:
        """Render one neutral turn as one or more OpenAI messages."""
        rendered: list[dict[str, Any]] = []
        # Each tool result is its own message, keyed by the call it answers.
        for result in message.tool_results:
            rendered.append(
                {
                    "role": "tool",
                    "tool_call_id": result.tool_call_id,
                    "content": result.content,
                }
            )
        if message.role is Role.TOOL:
            return rendered

        role = {Role.SYSTEM: "system", Role.ASSISTANT: "assistant"}.get(message.role, "user")
        if message.tool_calls:
            rendered.append(
                {
                    "role": "assistant",
                    "content": message.content or None,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": json.dumps(call.arguments),
                            },
                        }
                        for call in message.tool_calls
                    ],
                }
            )
        elif message.content:
            rendered.append({"role": role, "content": message.content})
        return rendered

    # --- response --------------------------------------------------------------

    def _parse_completion(self, data: dict[str, Any]) -> Completion:
        choices = data.get("choices") or []
        choice = choices[0] if choices and isinstance(choices[0], dict) else {}
        message = choice.get("message") or {}
        tool_calls = tuple(
            _tool_call_from_wire(entry)
            for entry in (message.get("tool_calls") or [])
            if isinstance(entry, dict)
        )
        return Completion(
            text=str(message.get("content") or ""),
            tool_calls=tool_calls,
            usage=_usage_from_wire(data.get("usage")),
            stop_reason=choice.get("finish_reason"),
        )

    def _iter_events(self, response: httpx.Response) -> Iterator[StreamEvent]:
        text_parts: list[str] = []
        # index -> partially received tool call; OpenAI streams `arguments` as a
        # sequence of string fragments that only parse once the stream ends.
        pending: dict[int, dict[str, str]] = {}
        usage = Usage()
        stop_reason: str | None = None

        for payload in iter_sse_data(response):
            if payload == _SSE_DONE:
                break
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if not isinstance(chunk, dict):
                continue

            if chunk.get("usage"):
                usage = _usage_from_wire(chunk["usage"])

            for choice in chunk.get("choices") or []:
                if not isinstance(choice, dict):
                    continue
                stop_reason = choice.get("finish_reason") or stop_reason
                delta = choice.get("delta") or {}
                text = delta.get("content")
                if text:
                    text_parts.append(str(text))
                    yield StreamEvent(type=StreamEventType.TEXT, text=str(text))
                for entry in delta.get("tool_calls") or []:
                    if isinstance(entry, dict):
                        _accumulate_tool_call(pending, entry)

        tool_calls: list[ToolCall] = []
        for index in sorted(pending):
            slot = pending[index]
            call = ToolCall(
                id=slot["id"],
                name=slot["name"],
                arguments=_decode_arguments(slot["arguments"]),
            )
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


def _accumulate_tool_call(pending: dict[int, dict[str, str]], entry: dict[str, Any]) -> None:
    """Merge one streamed ``tool_calls`` fragment into the slot for its index."""
    index = int(entry.get("index", 0) or 0)
    slot = pending.setdefault(index, {"id": "", "name": "", "arguments": ""})
    if entry.get("id"):
        slot["id"] = str(entry["id"])
    function = entry.get("function") or {}
    if function.get("name"):
        slot["name"] = str(function["name"])
    if function.get("arguments"):
        slot["arguments"] += str(function["arguments"])


def _tool_call_from_wire(entry: dict[str, Any]) -> ToolCall:
    function = entry.get("function") or {}
    return ToolCall(
        id=str(entry.get("id", "")),
        name=str(function.get("name", "")),
        arguments=_decode_arguments(str(function.get("arguments") or "")),
    )


def _usage_from_wire(usage: object) -> Usage:
    if not isinstance(usage, dict):
        return Usage()
    return Usage(
        input_tokens=int(usage.get("prompt_tokens", 0) or 0),
        output_tokens=int(usage.get("completion_tokens", 0) or 0),
    )


def _decode_arguments(buffer: str) -> dict[str, Any]:
    """Parse a tool-argument JSON string; an empty buffer means no arguments."""
    if not buffer.strip():
        return {}
    try:
        arguments = json.loads(buffer)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"openai sent unparseable tool arguments: {exc.msg}") from exc
    if not isinstance(arguments, dict):
        raise ProviderError("openai sent non-object tool arguments")
    return arguments
