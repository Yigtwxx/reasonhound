"""Anthropic (Claude) adapter for the Messages API.

Wire reference: ``POST https://api.anthropic.com/v1/messages`` with the
``anthropic-version: 2023-06-01`` header. Conversation content is a list of
typed blocks (``text`` / ``tool_use`` / ``tool_result``) rather than a plain
string, and the system prompt is a top-level field instead of a message.
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

__all__ = ["ANTHROPIC_BASE_URL", "ANTHROPIC_VERSION", "AnthropicProvider"]

ANTHROPIC_BASE_URL = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(HttpProvider):
    """Speaks the Anthropic Messages API.

    ``temperature`` is accepted for interface compatibility but never sent: the
    current Claude models reject the parameter with a 400, and the reasoning
    loop wants deterministic output anyway.
    """

    name = "anthropic"

    def __init__(self, *, api_key: str, model: str, **kwargs: Any) -> None:
        super().__init__(model=model, base_url=kwargs.pop("base_url", ANTHROPIC_BASE_URL), **kwargs)
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    def _endpoint(self, *, stream: bool) -> str:
        del stream  # one endpoint; streaming is a body flag
        return f"{self.base_url}/v1/messages"

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
        del temperature  # never sent; see the class docstring
        system_parts = [system] if system else []
        wire_messages: list[dict[str, Any]] = []

        for message in messages:
            if message.role is Role.SYSTEM:
                # Anthropic has no system turn; hoist it into the top-level field.
                if message.content:
                    system_parts.append(message.content)
                continue
            role = "assistant" if message.role is Role.ASSISTANT else "user"
            blocks = self._message_blocks(message)
            if blocks:
                wire_messages.append({"role": role, "content": blocks})

        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": _merge_adjacent(wire_messages),
        }
        if system_parts:
            body["system"] = "\n\n".join(system_parts)
        if tools:
            body["tools"] = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                }
                for tool in tools
            ]
        if stream:
            body["stream"] = True
        return body

    @staticmethod
    def _message_blocks(message: Message) -> list[dict[str, Any]]:
        """Render one turn as Anthropic content blocks."""
        blocks: list[dict[str, Any]] = []
        # Tool results lead their turn so the model sees the answers it asked for
        # before any accompanying commentary.
        for result in message.tool_results:
            blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": result.tool_call_id,
                    "content": result.content,
                    "is_error": result.is_error,
                }
            )
        if message.content:
            blocks.append({"type": "text", "text": message.content})
        for call in message.tool_calls:
            blocks.append(
                {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
            )
        return blocks

    # --- response --------------------------------------------------------------

    def _parse_completion(self, data: dict[str, Any]) -> Completion:
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in data.get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text_parts.append(str(block.get("text", "")))
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=str(block.get("id", "")),
                        name=str(block.get("name", "")),
                        arguments=block.get("input") or {},
                    )
                )
        usage = data.get("usage") or {}
        return Completion(
            text="".join(text_parts),
            tool_calls=tuple(tool_calls),
            usage=Usage(
                input_tokens=int(usage.get("input_tokens", 0) or 0),
                output_tokens=int(usage.get("output_tokens", 0) or 0),
            ),
            stop_reason=data.get("stop_reason"),
        )

    def _iter_events(self, response: httpx.Response) -> Iterator[StreamEvent]:
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        # index -> partially received tool_use block; Anthropic streams the tool
        # arguments as a sequence of JSON fragments that only parse once complete.
        pending: dict[int, dict[str, Any]] = {}
        input_tokens = 0
        output_tokens = 0
        stop_reason: str | None = None

        for payload in iter_sse_data(response):
            event = _decode_event(payload)
            if event is None:
                continue
            kind = event.get("type")

            if kind == "error":
                detail = self._error_detail(event) or "unknown streaming error"
                raise ProviderError(f"{self.name} stream failed: {self._redactor.redact(detail)}")

            if kind == "message_start":
                usage = (event.get("message") or {}).get("usage") or {}
                input_tokens = int(usage.get("input_tokens", 0) or 0)

            elif kind == "content_block_start":
                block = event.get("content_block") or {}
                if block.get("type") == "tool_use":
                    pending[int(event.get("index", 0))] = {
                        "id": str(block.get("id", "")),
                        "name": str(block.get("name", "")),
                        "json": "",
                    }

            elif kind == "content_block_delta":
                delta = event.get("delta") or {}
                if delta.get("type") == "text_delta":
                    text = str(delta.get("text", ""))
                    if text:
                        text_parts.append(text)
                        yield StreamEvent(type=StreamEventType.TEXT, text=text)
                elif delta.get("type") == "input_json_delta":
                    slot = pending.get(int(event.get("index", 0)))
                    if slot is not None:
                        slot["json"] += str(delta.get("partial_json", ""))

            elif kind == "content_block_stop":
                slot = pending.pop(int(event.get("index", 0)), None)
                if slot is not None:
                    call = ToolCall(
                        id=slot["id"],
                        name=slot["name"],
                        arguments=_decode_arguments(slot["json"]),
                    )
                    tool_calls.append(call)
                    yield StreamEvent(type=StreamEventType.TOOL_CALL, tool_call=call)

            elif kind == "message_delta":
                stop_reason = (event.get("delta") or {}).get("stop_reason") or stop_reason
                usage = event.get("usage") or {}
                output_tokens = int(usage.get("output_tokens", output_tokens) or output_tokens)

            elif kind == "message_stop":
                break

        yield StreamEvent(
            type=StreamEventType.DONE,
            completion=Completion(
                text="".join(text_parts),
                tool_calls=tuple(tool_calls),
                usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
                stop_reason=stop_reason,
            ),
        )


def _merge_adjacent(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse consecutive same-role turns into one.

    Anthropic rejects two turns in a row with the same role. Reasonhound hits
    this routinely because a tool-result turn maps to ``user`` and is usually
    followed by the user's next instruction, so the merge is required rather
    than defensive.
    """
    merged: list[dict[str, Any]] = []
    for turn in turns:
        if merged and merged[-1]["role"] == turn["role"]:
            merged[-1]["content"].extend(turn["content"])
        else:
            merged.append({"role": turn["role"], "content": list(turn["content"])})
    return merged


def _decode_event(payload: str) -> dict[str, Any] | None:
    """Decode one SSE payload, ignoring keep-alives and malformed fragments."""
    if not payload:
        return None
    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return event if isinstance(event, dict) else None


def _decode_arguments(buffer: str) -> dict[str, Any]:
    """Parse accumulated tool-argument JSON; an empty buffer means no arguments."""
    if not buffer.strip():
        return {}
    try:
        arguments = json.loads(buffer)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"anthropic sent unparseable tool arguments: {exc.msg}") from exc
    if not isinstance(arguments, dict):
        raise ProviderError("anthropic sent non-object tool arguments")
    return arguments
