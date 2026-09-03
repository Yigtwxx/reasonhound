"""Tests for reasonhound.config."""

from __future__ import annotations

from pathlib import Path

import pytest

from reasonhound.config import (
    DEFAULT_CONCURRENCY,
    DEFAULT_COST_CAP_USD,
    DEFAULT_EXCLUDE,
    ConfigError,
    Provider,
    ScanConfig,
    ScanMode,
    api_key_present,
    config_path,
    load_config,
    save_config,
)


def test_roundtrip(project: Path) -> None:
    cfg = ScanConfig(provider=Provider.OPENAI, mode=ScanMode.DYNAMIC, budget=7)
    written = save_config(project, cfg)

    assert written == config_path(project)
    assert load_config(project) == cfg


def test_load_missing_returns_none(project: Path) -> None:
    assert load_config(project) is None


def test_saved_file_contains_no_secret(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-never-be-persisted")
    save_config(project, ScanConfig(provider=Provider.ANTHROPIC))

    assert "sk-should-never-be-persisted" not in config_path(project).read_text()


@pytest.mark.parametrize(
    "body",
    [
        "not = [valid toml",
        '[scan]\nprovider = "nope"',
        '[scan]\nprovider = "openai"\nbudget = 0',
        '[scan]\nprovider = "openai"\nconcurrency = 0',
        '[scan]\nprovider = "openai"\ncost_cap_usd = 0',
    ],
)
def test_load_invalid_raises(project: Path, body: str) -> None:
    config_path(project).write_text(body)
    with pytest.raises(ConfigError):
        load_config(project)


def test_api_key_present(monkeypatch: pytest.MonkeyPatch, no_api_keys: None) -> None:
    assert api_key_present(Provider.OLLAMA) is True
    assert api_key_present(Provider.GEMINI) is False

    monkeypatch.setenv("GEMINI_API_KEY", "   ")
    assert api_key_present(Provider.GEMINI) is False

    monkeypatch.setenv("GEMINI_API_KEY", "abc")
    assert api_key_present(Provider.GEMINI) is True


def test_provider_env_vars() -> None:
    assert Provider.ANTHROPIC.env_var == "ANTHROPIC_API_KEY"
    assert Provider.OLLAMA.env_var is None
    assert all(p.label for p in Provider)
    assert all(m.label for m in ScanMode)


def test_extended_defaults() -> None:
    cfg = ScanConfig(provider=Provider.OLLAMA)
    assert cfg.concurrency == DEFAULT_CONCURRENCY
    assert cfg.cost_cap_usd == DEFAULT_COST_CAP_USD
    assert cfg.exclude == list(DEFAULT_EXCLUDE)
    assert "node_modules" in cfg.exclude and ".git" in cfg.exclude


def test_extended_roundtrip(project: Path) -> None:
    cfg = ScanConfig(
        provider=Provider.ANTHROPIC,
        concurrency=8,
        cost_cap_usd=2.5,
        exclude=["node_modules", "coverage"],
    )
    save_config(project, cfg)
    assert load_config(project) == cfg


def test_backcompat_minimal_config_fills_defaults(project: Path) -> None:
    # Older config files without the new fields must still load with defaults.
    config_path(project).write_text('[scan]\nprovider = "ollama"\n')
    cfg = load_config(project)
    assert cfg is not None
    assert cfg.provider is Provider.OLLAMA
    assert cfg.concurrency == DEFAULT_CONCURRENCY
    assert cfg.cost_cap_usd == DEFAULT_COST_CAP_USD
    assert cfg.exclude == list(DEFAULT_EXCLUDE)
