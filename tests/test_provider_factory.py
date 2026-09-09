"""Tests for the provider factory and its environment key handling."""

from __future__ import annotations

import pytest

from reasonhound.config import Provider
from reasonhound.providers import (
    DEFAULT_MODELS,
    AnthropicProvider,
    GeminiProvider,
    LLMProvider,
    OllamaProvider,
    OpenAIProvider,
    ProviderError,
    create_provider,
    default_model,
)

_EXPECTED = {
    Provider.ANTHROPIC: AnthropicProvider,
    Provider.OPENAI: OpenAIProvider,
    Provider.GEMINI: GeminiProvider,
    Provider.OLLAMA: OllamaProvider,
}


@pytest.fixture
def all_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for provider in Provider:
        if provider.env_var:
            monkeypatch.setenv(provider.env_var, f"key-for-{provider.value}")


@pytest.mark.parametrize("provider", list(Provider))
def test_creates_the_expected_adapter(provider: Provider, all_keys: None) -> None:
    with create_provider(provider) as built:
        assert isinstance(built, _EXPECTED[provider])
        assert isinstance(built, LLMProvider)


@pytest.mark.parametrize("provider", list(Provider))
def test_every_provider_has_a_default_model(provider: Provider) -> None:
    """A new Provider member must not slip in without a default."""
    assert default_model(provider) == DEFAULT_MODELS[provider]
    assert DEFAULT_MODELS[provider], f"{provider.value} has an empty default model"


def test_explicit_model_overrides_the_default(all_keys: None) -> None:
    with create_provider(Provider.ANTHROPIC, model="claude-haiku-4-5") as built:
        assert built.model == "claude-haiku-4-5"


def test_missing_key_names_the_variable_not_the_value(no_api_keys: None) -> None:
    with pytest.raises(ProviderError) as excinfo:
        create_provider(Provider.OPENAI)

    assert "OPENAI_API_KEY" in str(excinfo.value)


def test_blank_key_counts_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "   ")

    with pytest.raises(ProviderError, match="GEMINI_API_KEY"):
        create_provider(Provider.GEMINI)


def test_ollama_needs_no_key(no_api_keys: None) -> None:
    with create_provider(Provider.OLLAMA) as built:
        assert isinstance(built, OllamaProvider)


def test_key_is_read_at_call_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rotating the environment between runs must be picked up, not cached."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ProviderError):
        create_provider(Provider.ANTHROPIC)

    monkeypatch.setenv("ANTHROPIC_API_KEY", "now-present")
    with create_provider(Provider.ANTHROPIC) as built:
        assert built._headers()["x-api-key"] == "now-present"


def test_key_does_not_leak_into_the_error_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    with pytest.raises(ProviderError) as excinfo:
        create_provider(Provider.OPENAI)

    assert "sk-" not in str(excinfo.value)
