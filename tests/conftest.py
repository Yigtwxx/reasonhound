"""Shared pytest fixtures."""

from __future__ import annotations

import re
import threading
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from reasonhound.providers.base import (
    Completion,
    Message,
    StreamEvent,
    ToolCall,
    ToolSpec,
    Usage,
)
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


# --- agent runtime helpers ---------------------------------------------------

_AGENT_IN_PROMPT = re.compile(r"You are `([a-z0-9-]+)`")


def submit(call_id: str = "s1", **arguments: object) -> Completion:
    """A completion whose only tool call is ``submit_result``."""
    return Completion(
        tool_calls=(ToolCall(id=call_id, name="submit_result", arguments=dict(arguments)),),
        usage=Usage(input_tokens=100, output_tokens=50),
    )


def call(name: str, call_id: str = "c1", **arguments: object) -> Completion:
    """A completion with a single tool call."""
    return Completion(
        tool_calls=(ToolCall(id=call_id, name=name, arguments=dict(arguments)),),
        usage=Usage(input_tokens=100, output_tokens=50),
    )


class ScriptedProvider:
    """Thread-safe fake that routes scripted completions by agent name.

    The agent is read from the system prompt, so parallel agents each consume
    their own script regardless of scheduling order. A drained script answers
    with plain text (which the runtime treats as "no tool call").
    """

    name = "scripted"

    def __init__(self, scripts: dict[str, list[Completion]]) -> None:
        self._scripts = {agent: list(items) for agent, items in scripts.items()}
        self._lock = threading.Lock()
        self.calls: list[tuple[str, tuple[Message, ...]]] = []

    def complete(
        self,
        messages: Sequence[Message],
        *,
        system: str | None = None,
        tools: Sequence[ToolSpec] = (),
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> Completion:
        match = _AGENT_IN_PROMPT.search(system or "")
        agent = match.group(1) if match else "?"
        with self._lock:
            self.calls.append((agent, tuple(messages)))
            script = self._scripts.get(agent, [])
            if script:
                return script.pop(0)
        return Completion(text="thinking", usage=Usage(input_tokens=10, output_tokens=5))

    def stream(self, *args: object, **kwargs: object) -> Iterator[StreamEvent]:
        raise NotImplementedError


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    """A tiny project with code, an excluded dir, and a previous report folder."""
    root = tmp_path / "proj"
    (root / "app").mkdir(parents=True)
    (root / "app" / "views.py").write_text(
        "import os\n\n\ndef login(request):\n"
        "    user = request.args['user']\n"
        "    return db.execute(f\"SELECT * FROM users WHERE name = '{user}'\")\n\n\n"
        "class Admin:\n    def delete(self, uid):\n        pass\n",
        encoding="utf-8",
    )
    (root / "app" / "main.js").write_text(
        "function render(x) { document.body.innerHTML = x; }\n", encoding="utf-8"
    )
    (root / "README.md").write_text("# demo\n", encoding="utf-8")
    (root / "node_modules" / "lib").mkdir(parents=True)
    (root / "node_modules" / "lib" / "index.js").write_text("SELECT secret\n", encoding="utf-8")
    (root / "Reasonhound").mkdir()
    (root / "Reasonhound" / "INDEX.md").write_text("SELECT old finding\n", encoding="utf-8")
    return root
