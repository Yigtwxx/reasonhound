"""Tests for run control, the event bus, and the budget ledger."""

from __future__ import annotations

import threading
import time

import pytest

from reasonhound.budget import (
    FALLBACK_PRICE,
    FREE,
    MODEL_PRICES,
    BudgetExceeded,
    BudgetLedger,
    ModelPrice,
    price_for,
)
from reasonhound.config import Provider
from reasonhound.control import AgentKilled, RunControl, ScanKilled, ScanStopped
from reasonhound.events import AgentStatus, BudgetUpdated, EventBus, ScanEvent
from reasonhound.providers.base import Usage

# --- control ---------------------------------------------------------------------


def test_checkpoint_passes_by_default() -> None:
    RunControl().checkpoint("a-1")


def test_kill_one_agent_only() -> None:
    control = RunControl()
    control.kill("a-1")
    with pytest.raises(AgentKilled):
        control.checkpoint("a-1")
    control.checkpoint("b-1")
    assert control.is_killed("a-1") and not control.is_killed("b-1")


def test_kill_all() -> None:
    control = RunControl()
    control.kill_all()
    with pytest.raises(ScanKilled):
        control.checkpoint("any")
    assert issubclass(ScanKilled, ScanStopped) and issubclass(BudgetExceeded, ScanStopped)


def test_pause_blocks_until_resume() -> None:
    control = RunControl()
    control.pause()
    passed = threading.Event()

    def agent() -> None:
        control.checkpoint("a-1")
        passed.set()

    worker = threading.Thread(target=agent)
    worker.start()
    time.sleep(0.25)
    assert not passed.is_set() and control.paused
    control.resume()
    worker.join(timeout=2)
    assert passed.is_set()


def test_kill_releases_a_paused_agent() -> None:
    control = RunControl()
    control.pause()
    errors: list[BaseException] = []

    def agent() -> None:
        try:
            control.checkpoint("a-1")
        except ScanStopped as exc:
            errors.append(exc)

    worker = threading.Thread(target=agent)
    worker.start()
    control.kill("a-1")
    worker.join(timeout=2)
    assert errors and isinstance(errors[0], AgentKilled)


# --- events ------------------------------------------------------------------------


def test_bus_delivers_and_unsubscribes() -> None:
    bus = EventBus()
    seen: list[ScanEvent] = []
    unsubscribe = bus.subscribe(seen.append)
    bus.publish(AgentStatus(run_id="r", agent="a", message="hi"))
    unsubscribe()
    unsubscribe()  # idempotent
    bus.publish(AgentStatus(run_id="r", agent="a", message="again"))
    assert len(seen) == 1


def test_bus_survives_a_failing_subscriber() -> None:
    bus = EventBus()
    seen: list[ScanEvent] = []

    def broken(_: ScanEvent) -> None:
        raise RuntimeError("render bug")

    bus.subscribe(broken)
    bus.subscribe(seen.append)
    bus.publish(AgentStatus(run_id="r", agent="a", message="hi"))
    assert len(seen) == 1


# --- budget ------------------------------------------------------------------------


def test_price_lookup() -> None:
    assert price_for(Provider.OLLAMA, "llama3.1:8b") == FREE
    assert price_for(Provider.ANTHROPIC, "claude-opus-5") == MODEL_PRICES["claude-opus-5"]
    assert price_for(Provider.OPENAI, "some-future-model") == FALLBACK_PRICE


def test_fallback_is_never_cheaper_than_a_known_model() -> None:
    for price in MODEL_PRICES.values():
        assert FALLBACK_PRICE.input_per_mtok >= price.input_per_mtok
        assert FALLBACK_PRICE.output_per_mtok >= price.output_per_mtok


def test_ledger_charges_and_reports() -> None:
    bus = EventBus()
    updates: list[ScanEvent] = []
    bus.subscribe(updates.append)
    ledger = BudgetLedger(cap_usd=1.0, price=ModelPrice(1.0, 2.0), bus=bus)
    cost = ledger.charge("hunter", Usage(input_tokens=1_000_000, output_tokens=0))
    assert cost == pytest.approx(1.0)
    assert ledger.per_agent()["hunter"].calls == 1
    assert isinstance(updates[-1], BudgetUpdated) and updates[-1].spent_usd == pytest.approx(1.0)


def test_ledger_check_trips_at_cap() -> None:
    ledger = BudgetLedger(cap_usd=0.5, price=ModelPrice(1.0, 1.0))
    ledger.check()
    ledger.charge("a", Usage(input_tokens=500_000))
    assert ledger.exhausted
    with pytest.raises(BudgetExceeded, match="cost cap"):
        ledger.check()


def test_ledger_is_thread_safe() -> None:
    ledger = BudgetLedger(cap_usd=100.0, price=ModelPrice(1.0, 1.0))

    def spend() -> None:
        for _ in range(500):
            ledger.charge("a", Usage(input_tokens=1, output_tokens=1))

    workers = [threading.Thread(target=spend) for _ in range(8)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    assert ledger.per_agent()["a"].calls == 4000


def test_ledger_rejects_non_positive_cap() -> None:
    with pytest.raises(ValueError):
        BudgetLedger(cap_usd=0, price=FREE)
