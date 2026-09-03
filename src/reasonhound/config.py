"""Scan configuration: provider/mode enums, TOML persistence, API-key lookup.

Secrets are never stored here. Only the *presence* of an API key is checked;
the key value itself is read by the provider adapter at call time.
"""

from __future__ import annotations

import os
import tomllib
from enum import StrEnum
from pathlib import Path

import tomli_w
from pydantic import BaseModel, Field, ValidationError

CONFIG_FILENAME = ".reasonhound.toml"
REPORT_DIRNAME = "Reasonhound"
INDEX_FILENAME = "INDEX.md"
FINDINGS_SUBDIR = "findings"
AUDIT_FILENAME = "audit.log"
DEFAULT_BUDGET = 20
DEFAULT_CONCURRENCY = 5
DEFAULT_COST_CAP_USD = 5.0
DEFAULT_EXCLUDE: tuple[str, ...] = (
    "node_modules",
    ".git",
    "dist",
    "build",
    "vendor",
)


class Provider(StrEnum):
    """Supported BYOK reasoning providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GEMINI = "gemini"
    OLLAMA = "ollama"

    @property
    def label(self) -> str:
        """Human-readable name shown in prompts."""
        return _PROVIDER_LABELS[self]

    @property
    def env_var(self) -> str | None:
        """Environment variable holding the API key, or ``None`` if no key is needed."""
        return _PROVIDER_ENV_VARS[self]


_PROVIDER_LABELS: dict[Provider, str] = {
    Provider.ANTHROPIC: "Anthropic (Claude)",
    Provider.OPENAI: "OpenAI",
    Provider.GEMINI: "Google Gemini",
    Provider.OLLAMA: "Ollama (local)",
}

_PROVIDER_ENV_VARS: dict[Provider, str | None] = {
    Provider.ANTHROPIC: "ANTHROPIC_API_KEY",
    Provider.OPENAI: "OPENAI_API_KEY",
    Provider.GEMINI: "GEMINI_API_KEY",
    Provider.OLLAMA: None,
}


class ScanMode(StrEnum):
    """How deep the scan goes."""

    STATIC = "static"
    DYNAMIC = "dynamic"

    @property
    def label(self) -> str:
        """Human-readable name shown in prompts."""
        return _MODE_LABELS[self]


_MODE_LABELS: dict[ScanMode, str] = {
    ScanMode.STATIC: "Code only (static)",
    ScanMode.DYNAMIC: "Bring the app up end-to-end (dynamic)",
}


class ScanConfig(BaseModel):
    """Persisted per-project scan preferences. Never contains secrets."""

    provider: Provider
    mode: ScanMode = ScanMode.STATIC
    budget: int = Field(
        default=DEFAULT_BUDGET, ge=1, description="Reasoning rounds per hypothesis."
    )
    concurrency: int = Field(default=DEFAULT_CONCURRENCY, ge=1, le=32)
    cost_cap_usd: float = Field(default=DEFAULT_COST_CAP_USD, gt=0.0)
    exclude: list[str] = Field(default_factory=lambda: list(DEFAULT_EXCLUDE))


class ConfigError(Exception):
    """Raised when an existing config file cannot be parsed."""


def config_path(root: Path) -> Path:
    """Location of the config file for a project root."""
    return root / CONFIG_FILENAME


def load_config(root: Path) -> ScanConfig | None:
    """Read ``.reasonhound.toml`` from *root*; return ``None`` when absent."""
    path = config_path(root)
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        return ScanConfig.model_validate(data.get("scan", {}))
    except (tomllib.TOMLDecodeError, ValidationError) as exc:
        raise ConfigError(f"Invalid config at {path}: {exc}") from exc


def save_config(root: Path, config: ScanConfig) -> Path:
    """Write *config* to ``.reasonhound.toml`` under *root* and return its path."""
    path = config_path(root)
    payload = {"scan": config.model_dump(mode="json")}
    path.write_text(tomli_w.dumps(payload), encoding="utf-8")
    return path


def api_key_present(provider: Provider) -> bool:
    """Return whether the provider's API key is available in the environment.

    Providers that need no key (Ollama) always return ``True``. The key value
    is intentionally not returned so it cannot leak into logs or output.
    """
    env_var = provider.env_var
    if env_var is None:
        return True
    return bool(os.environ.get(env_var, "").strip())
