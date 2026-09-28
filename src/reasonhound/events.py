"""The scan's event stream: what every agent is doing, as typed events.

Agents and the orchestrator publish; the live TUI, the ``--plain`` line printer,
and tests subscribe. Events are immutable and carry no secrets -- tool events
name the tool and whether it succeeded, never its arguments or output, because
those can hold file content from the scanned project.

The outcome enums live here because they are the shared vocabulary of "how a run
ended", used by both the runtime that decides it and the UI that shows it.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from reasonhound.models import Hypothesis

__all__ = [
    "AgentFinished",
    "AgentOutcome",
    "AgentStarted",
    "AgentStatus",
    "BudgetUpdated",
    "EventBus",
    "HypothesisRaised",
    "ScanEvent",
    "ScanFinished",
    "ScanOutcome",
    "ScanPlanned",
    "Subscriber",
    "ToolDenied",
    "ToolInvoked",
]

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AgentOutcome(StrEnum):
    """How one agent run ended."""

    COMPLETED = "completed"  # submitted a valid result
    EXHAUSTED = "exhausted"  # hit its round limit without submitting
    BUDGET = "budget"  # the scan-wide cost cap was reached
    KILLED = "killed"  # stopped by the user
    FAILED = "failed"  # provider or runtime error


class ScanOutcome(StrEnum):
    """How the whole scan ended."""

    COMPLETED = "completed"  # every planned agent finished on its own terms
    PARTIAL = "partial"  # stopped early (budget / kill) or some agents failed


@dataclass(frozen=True)
class AgentStarted:
    run_id: str
    agent: str
    objective: str
    ts: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True)
class AgentStatus:
    """A short human-readable progress line ("round 3/20")."""

    run_id: str
    agent: str
    message: str
    ts: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True)
class ToolInvoked:
    run_id: str
    agent: str
    tool: str
    ok: bool
    ts: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True)
class ToolDenied:
    """An agent asked for a tool outside its allowlist -- a prompt-injection signal."""

    run_id: str
    agent: str
    tool: str
    ts: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True)
class HypothesisRaised:
    run_id: str
    agent: str
    hypothesis: Hypothesis
    ts: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True)
class AgentFinished:
    run_id: str
    agent: str
    outcome: AgentOutcome
    rounds: int
    error: str | None = None
    ts: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True)
class BudgetUpdated:
    spent_usd: float
    cap_usd: float
    input_tokens: int
    output_tokens: int
    ts: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True)
class ScanPlanned:
    """The orchestrator's dispatch plan: one entry per planned agent run."""

    agents: tuple[str, ...]
    rationale: str
    fallback: bool = False
    ts: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True)
class ScanFinished:
    outcome: ScanOutcome
    hypotheses: int
    stop_reason: str | None = None
    ts: datetime = field(default_factory=_utcnow)


ScanEvent = (
    AgentStarted
    | AgentStatus
    | ToolInvoked
    | ToolDenied
    | HypothesisRaised
    | AgentFinished
    | BudgetUpdated
    | ScanPlanned
    | ScanFinished
)

Subscriber = Callable[[ScanEvent], None]


class EventBus:
    """Synchronous, thread-safe publish/subscribe for :data:`ScanEvent`.

    Subscribers run on the publishing thread, so they must be quick (the TUI
    hands events to its own loop). A subscriber that raises is logged and
    skipped: a rendering bug must never abort a scan.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[Subscriber] = []

    def subscribe(self, subscriber: Subscriber) -> Callable[[], None]:
        """Register *subscriber*; return a function that unregisters it."""
        with self._lock:
            self._subscribers.append(subscriber)

        def unsubscribe() -> None:
            with self._lock:
                if subscriber in self._subscribers:
                    self._subscribers.remove(subscriber)

        return unsubscribe

    def publish(self, event: ScanEvent) -> None:
        """Deliver *event* to every current subscriber."""
        with self._lock:
            subscribers = tuple(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber(event)
            except Exception:
                logger.exception("event subscriber failed on %s", type(event).__name__)
