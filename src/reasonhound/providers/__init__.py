"""BYOK provider adapters and the shared ``LLMProvider`` interface.

The interface and transport types live in :mod:`reasonhound.providers.base`;
concrete HTTP adapters (Anthropic / OpenAI / Gemini / Ollama) arrive in Phase 2.
:class:`~reasonhound.providers.fake.FakeProvider` is the test double.
"""

from __future__ import annotations

from reasonhound.providers.base import (
    Completion,
    LLMProvider,
    Message,
    ProviderError,
    Role,
    StreamEvent,
    StreamEventType,
    ToolCall,
    ToolResult,
    ToolSpec,
    Usage,
)
from reasonhound.providers.fake import FakeProvider, RecordedCall

__all__ = [
    "Completion",
    "FakeProvider",
    "LLMProvider",
    "Message",
    "ProviderError",
    "RecordedCall",
    "Role",
    "StreamEvent",
    "StreamEventType",
    "ToolCall",
    "ToolResult",
    "ToolSpec",
    "Usage",
]
