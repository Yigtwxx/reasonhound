"""Budget ledger (``budget-quartermaster``): token / dollar accounting with a hard cap.

Every completion is charged to the agent that made it. Before each provider call
an agent asks the ledger whether the scan may continue; once the cap is reached
:meth:`BudgetLedger.check` raises :class:`BudgetExceeded` and the scan winds
down, keeping what it already found.

The cap is checked *before* a call and charged *after* it, so parallel agents can
overshoot it by at most one completion each. That is the price of not holding a
lock across a network call.

Prices are per million tokens. A model missing from the table is priced as a
premium model, so an unknown id can make the cap trip early but never silently
switches it off.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from reasonhound.config import Provider
from reasonhound.control import ScanStopped
from reasonhound.events import BudgetUpdated, EventBus
from reasonhound.providers.base import Usage

__all__ = [
    "FALLBACK_PRICE",
    "FREE",
    "MODEL_PRICES",
    "AgentSpend",
    "BudgetExceeded",
    "BudgetLedger",
    "ModelPrice",
    "price_for",
]


class BudgetExceeded(ScanStopped):
    """The scan-wide cost cap was reached."""


@dataclass(frozen=True)
class ModelPrice:
    """USD per one million input / output tokens."""

    input_per_mtok: float
    output_per_mtok: float

    def cost(self, usage: Usage) -> float:
        return (
            usage.input_tokens * self.input_per_mtok + usage.output_tokens * self.output_per_mtok
        ) / 1_000_000


FREE = ModelPrice(0.0, 0.0)

# Standard-tier list prices. Exact ids only: a prefix match would price a pricier
# sibling ("-pro") as its cheaper base model. Where a vendor has tiers, the higher
# one is used (OpenAI's long-context rate; Gemini's post-2026 rate) so the ledger
# never under-counts. Verified 2026-09-28 -- these drift.
MODEL_PRICES: dict[str, ModelPrice] = {
    "claude-opus-5": ModelPrice(5.0, 25.0),
    "gpt-6-astra": ModelPrice(20.0, 75.0),
    "gemini-3.8-flash": ModelPrice(1.5, 7.5),
}

# Unknown models are priced at least as high as the priciest known one, so the
# cap errs toward stopping early.
FALLBACK_PRICE = ModelPrice(20.0, 75.0)


def price_for(provider: Provider, model: str) -> ModelPrice:
    """Price sheet for *model*; local Ollama models cost nothing."""
    if provider is Provider.OLLAMA:
        return FREE
    return MODEL_PRICES.get(model, FALLBACK_PRICE)


@dataclass
class AgentSpend:
    """Running totals for one agent name."""

    input_tokens: int = 0
    output_tokens: int = 0
    usd: float = 0.0
    calls: int = 0


class BudgetLedger:
    """Thread-safe spend tracker that enforces the scan's dollar cap."""

    def __init__(self, *, cap_usd: float, price: ModelPrice, bus: EventBus | None = None) -> None:
        if cap_usd <= 0:
            raise ValueError("cap_usd must be positive")
        self.cap_usd = cap_usd
        self.price = price
        self._bus = bus
        self._lock = threading.Lock()
        self._per_agent: dict[str, AgentSpend] = {}
        self._spent = 0.0
        self._input = 0
        self._output = 0

    @property
    def spent_usd(self) -> float:
        with self._lock:
            return self._spent

    @property
    def exhausted(self) -> bool:
        with self._lock:
            return self._spent >= self.cap_usd

    def per_agent(self) -> dict[str, AgentSpend]:
        """A snapshot copy of the per-agent totals."""
        with self._lock:
            return {name: AgentSpend(**vars(spend)) for name, spend in self._per_agent.items()}

    def check(self) -> None:
        """Raise :class:`BudgetExceeded` once the cap has been reached."""
        with self._lock:
            spent = self._spent
        if spent >= self.cap_usd:
            raise BudgetExceeded(f"cost cap reached: ${spent:.2f} of ${self.cap_usd:.2f}")

    def charge(self, agent: str, usage: Usage) -> float:
        """Record one completion's usage against *agent*; return its cost in USD."""
        cost = self.price.cost(usage)
        with self._lock:
            spend = self._per_agent.setdefault(agent, AgentSpend())
            spend.input_tokens += usage.input_tokens
            spend.output_tokens += usage.output_tokens
            spend.usd += cost
            spend.calls += 1
            self._spent += cost
            self._input += usage.input_tokens
            self._output += usage.output_tokens
            event = BudgetUpdated(
                spent_usd=self._spent,
                cap_usd=self.cap_usd,
                input_tokens=self._input,
                output_tokens=self._output,
            )
        if self._bus is not None:
            self._bus.publish(event)
        return cost
