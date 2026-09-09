"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from reasonhound.providers.retry import RetryPolicy

#: Retries without wall-clock cost: a zero base delay makes the jitter zero too.
FAST_RETRY = RetryPolicy(max_attempts=3, base_delay=0.0, max_delay=0.0)


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
    """Strip every provider key from the environment so tests are hermetic.

    ``OLLAMA_HOST`` goes too: a developer running a custom daemon would otherwise
    see different request URLs than CI.
    """
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "OLLAMA_HOST"):
        monkeypatch.delenv(var, raising=False)
    yield


def sse(*frames: str) -> bytes:
    """Build a Server-Sent Events body from raw ``data:`` payloads."""
    return "".join(f"data: {frame}\n\n" for frame in frames).encode("utf-8")


def ndjson(*frames: str) -> bytes:
    """Build a newline-delimited JSON body (Ollama's stream format)."""
    return "".join(f"{frame}\n" for frame in frames).encode("utf-8")


@pytest.fixture
def capture() -> Callable[..., tuple[httpx.Client, list[httpx.Request]]]:
    """Build a client whose transport records every request it is handed.

    Pass either canned responses (returned in order) or a handler for full
    control. The recorded list lets a test assert on the outbound body.
    """

    def _make(
        *responses: httpx.Response,
        handler: Callable[[httpx.Request], httpx.Response] | None = None,
    ) -> tuple[httpx.Client, list[httpx.Request]]:
        requests: list[httpx.Request] = []
        queue = list(responses)

        def _handle(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if handler is not None:
                return handler(request)
            return queue.pop(0) if len(queue) > 1 else queue[0]

        return httpx.Client(transport=httpx.MockTransport(_handle)), requests

    return _make
