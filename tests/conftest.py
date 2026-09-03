"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """An empty directory standing in for a user's project."""
    target = tmp_path / "app"
    target.mkdir()
    return target


@pytest.fixture
def no_api_keys(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Strip every provider key from the environment so tests are hermetic."""
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    yield
