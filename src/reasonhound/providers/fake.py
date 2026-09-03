"""A deterministic in-memory provider for tests (no network).

``FakeProvider`` returns scripted completions and records every call, so tests
can assert both behavior and that redaction/fencing ran on the outbound payload
in later phases.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from reasonhound.providers.base import (
    Completion,
    Message,
    StreamEvent,
    StreamEventType,
    ToolSpec,
)

__all__ = ["FakeProvider", "RecordedCall"]


@dataclass(frozen=True)
class RecordedCall:
    """A captured provider invocation, for assertions in tests."""

    messages: tuple[Message, ...]
    system: str | None
    tools: tuple[ToolSpec, ...]


class FakeProvider:
    """Implements :class:`~reasonhound.providers.base.LLMProvider` for tests."""

    def __init__(
        self,
        responses: Sequence[Completion] | None = None,
        *,
        name: str = "fake",
        default_text: str = "ok",
    ) -> None:
        self.name = name
        self._responses = list(responses or [])
        self._default_text = default_text
        self.calls: list[RecordedCall] = []

    def complete(
        self,
        messages: Sequence[Message],
        *,
        system: str | None = None,
        tools: Sequence[ToolSpec] = (),
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> Completion:
        self.calls.append(RecordedCall(tuple(messages), system, tuple(tools)))
        if self._responses:
            return self._responses.pop(0)
        return Completion(text=self._default_text)

    def stream(
        self,
        messages: Sequence[Message],
        *,
        system: str | None = None,
        tools: Sequence[ToolSpec] = (),
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> Iterator[StreamEvent]:
        completion = self.complete(
            messages,
            system=system,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        for char in completion.text:
            yield StreamEvent(type=StreamEventType.TEXT, text=char)
        for call in completion.tool_calls:
            yield StreamEvent(type=StreamEventType.TOOL_CALL, tool_call=call)
        yield StreamEvent(type=StreamEventType.DONE, completion=completion)
