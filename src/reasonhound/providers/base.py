"""Provider-agnostic transport types and the ``LLMProvider`` interface.

Every BYOK adapter (Anthropic / OpenAI / Gemini / Ollama) implements
``LLMProvider``. The types here are deliberately small and provider-neutral: the
agent runtime speaks only this vocabulary, and each adapter translates it to and
from its provider's HTTP API. No network code lives here.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "Completion",
    "LLMProvider",
    "Message",
    "ProviderError",
    "Role",
    "StreamEvent",
    "StreamEventType",
    "ToolCall",
    "ToolResult",
    "ToolSpec",
    "Usage",
]


class ProviderError(Exception):
    """Raised when a provider call fails (transport, auth, or protocol error)."""


class Role(StrEnum):
    """Conversation roles understood by every adapter."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True)
class ToolSpec:
    """A tool definition offered to the model (JSON-schema arguments)."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    """The model's request to invoke a tool."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    """The outcome of a tool call, fed back to the model."""

    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass
class Message:
    """One turn in the conversation.

    ``tool_calls`` appear on assistant turns; ``tool_results`` on the following
    user turn that answers them.
    """

    role: Role
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_results: tuple[ToolResult, ...] = ()


@dataclass(frozen=True)
class Usage:
    """Token accounting for one completion, used by the budget ledger."""

    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class Completion:
    """A model response: text and/or tool calls, plus usage."""

    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    usage: Usage = field(default_factory=Usage)
    stop_reason: str | None = None


class StreamEventType(StrEnum):
    """Kinds of events emitted while streaming a completion."""

    TEXT = "text"
    TOOL_CALL = "tool_call"
    DONE = "done"


@dataclass(frozen=True)
class StreamEvent:
    """One streamed event: a text delta, a tool call, or the final completion."""

    type: StreamEventType
    text: str = ""
    tool_call: ToolCall | None = None
    completion: Completion | None = None


@runtime_checkable
class LLMProvider(Protocol):
    """The BYOK reasoning interface every adapter implements."""

    name: str

    def complete(
        self,
        messages: Sequence[Message],
        *,
        system: str | None = None,
        tools: Sequence[ToolSpec] = (),
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> Completion:
        """Return a single completion for *messages*."""
        ...

    def stream(
        self,
        messages: Sequence[Message],
        *,
        system: str | None = None,
        tools: Sequence[ToolSpec] = (),
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> Iterator[StreamEvent]:
        """Yield streamed events, ending with a ``DONE`` event that carries the
        final :class:`Completion` (drives the live TUI)."""
        ...
