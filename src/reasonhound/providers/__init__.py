"""BYOK provider adapters and the shared ``LLMProvider`` interface.

The interface and transport types live in :mod:`reasonhound.providers.base`; the
four HTTP adapters (Anthropic / OpenAI / Gemini / Ollama) share the machinery in
:mod:`reasonhound.providers.http`, which is also where the always-on egress
redaction is enforced. :class:`~reasonhound.providers.fake.FakeProvider` is the
test double. Use :func:`create_provider` rather than constructing an adapter
directly, so the API key is read from the environment in one place.
"""

from __future__ import annotations

from reasonhound.providers.anthropic import AnthropicProvider
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
from reasonhound.providers.factory import DEFAULT_MODELS, create_provider, default_model
from reasonhound.providers.fake import FakeProvider, RecordedCall
from reasonhound.providers.gemini import GeminiProvider
from reasonhound.providers.http import DEFAULT_TIMEOUT, HttpProvider
from reasonhound.providers.ollama import OllamaProvider
from reasonhound.providers.openai import OpenAIProvider
from reasonhound.providers.retry import RetryPolicy

__all__ = [
    "DEFAULT_MODELS",
    "DEFAULT_TIMEOUT",
    "AnthropicProvider",
    "Completion",
    "FakeProvider",
    "GeminiProvider",
    "HttpProvider",
    "LLMProvider",
    "Message",
    "OllamaProvider",
    "OpenAIProvider",
    "ProviderError",
    "RecordedCall",
    "RetryPolicy",
    "Role",
    "StreamEvent",
    "StreamEventType",
    "ToolCall",
    "ToolResult",
    "ToolSpec",
    "Usage",
    "create_provider",
    "default_model",
]
