"""Construction of a concrete BYOK adapter from a :class:`~reasonhound.config.Provider`.

The API key is read from the environment **at call time** and handed straight to
the adapter, which keeps it only in its request headers. It is never cached at
import, never written to disk, and never included in an error message -- a
missing-key error names the variable, not its value.
"""

from __future__ import annotations

import os
from typing import Any

from reasonhound.config import Provider
from reasonhound.providers.anthropic import AnthropicProvider
from reasonhound.providers.base import ProviderError
from reasonhound.providers.gemini import GeminiProvider
from reasonhound.providers.http import HttpProvider
from reasonhound.providers.ollama import OllamaProvider
from reasonhound.providers.openai import OpenAIProvider

__all__ = ["DEFAULT_MODELS", "create_provider", "default_model"]

# One default per provider so `reasonhound scan` works with no model flag.
# Each is the current top-tier *stable* model for a long-horizon agentic workload;
# preview models are deliberately avoided as defaults. Verified 2026-09-09 --
# these drift, so `--model` is the escape hatch when one goes stale.
DEFAULT_MODELS: dict[Provider, str] = {
    Provider.ANTHROPIC: "claude-opus-5",
    Provider.OPENAI: "gpt-6-astra",
    Provider.GEMINI: "gemini-3.8-flash",
    # Ollama needs an explicit tag: a bare name 404s unless :latest was pulled.
    # qwen3.5:9b (6.7 GB loaded at 32K context) found every planted bug in live
    # tool-calling scans with correct file:line and graded severity. gpt-oss:20b
    # found them too but left the location empty; llama3.1:8b never submitted.
    Provider.OLLAMA: "qwen3.5:9b",
}

_ADAPTERS: dict[Provider, type[HttpProvider]] = {
    Provider.ANTHROPIC: AnthropicProvider,
    Provider.OPENAI: OpenAIProvider,
    Provider.GEMINI: GeminiProvider,
    Provider.OLLAMA: OllamaProvider,
}


def default_model(provider: Provider) -> str:
    """Model id used when the user picked a provider but not a model."""
    return DEFAULT_MODELS[provider]


def _read_api_key(provider: Provider) -> str | None:
    """Read the provider's key from the environment; ``None`` when none is needed."""
    env_var = provider.env_var
    if env_var is None:  # Ollama runs locally
        return None
    key = os.environ.get(env_var, "").strip()
    if not key:
        raise ProviderError(
            f"{provider.label} needs an API key. Set the {env_var} environment variable."
        )
    return key


def create_provider(provider: Provider, *, model: str | None = None, **kwargs: Any) -> HttpProvider:
    """Build the adapter for *provider*, defaulting the model when unspecified.

    Extra keyword arguments are forwarded to the adapter (``timeout``, ``policy``,
    ``client`` for tests).
    """
    adapter = _ADAPTERS[provider]
    resolved = model or default_model(provider)
    api_key = _read_api_key(provider)
    if api_key is None:
        return adapter(model=resolved, **kwargs)
    return adapter(api_key=api_key, model=resolved, **kwargs)
