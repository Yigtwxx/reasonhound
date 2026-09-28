"""Tests for the lead-strategist: planning, fallback, parallel dispatch, dedup, stops."""

from __future__ import annotations

from pathlib import Path

import pytest

from reasonhound.agents import AgentCatalog, AgentOutcome, AgentRuntime, AgentSpec
from reasonhound.budget import BudgetLedger, ModelPrice
from reasonhound.control import RunControl
from reasonhound.events import EventBus, ScanEvent, ScanFinished, ScanOutcome, ScanPlanned
from reasonhound.models import Hypothesis, Location, Severity
from reasonhound.orchestrator import LEAD_STRATEGIST, LeadStrategist, dedupe_hypotheses
from reasonhound.tools import ToolContext, default_registry

from .conftest import ScriptedProvider, call, submit

SQLI = AgentSpec(
    name="injection-hunter", role="SQL injection.", instructions="i", tools=frozenset({"fs_grep"})
)
XSS = AgentSpec(name="xss-analyst", role="XSS.", instructions="i", tools=frozenset({"fs_grep"}))
PLANNER = LEAD_STRATEGIST.name


def _hyp(category: str, file: str, line: int, severity: str = "medium") -> dict[str, object]:
    return {
        "title": f"{category} at {file}:{line}",
        "category": category,
        "rationale": "because",
        "location": {"file": file, "line": line},
        "suspected_severity": severity,
    }


def _plan(*agents: str) -> dict[str, object]:
    return {
        "rationale": "targeted",
        "tasks": [{"agent": a, "objective": f"run {a}", "focus": ["app/"]} for a in agents],
    }


def _strategist(
    provider: ScriptedProvider,
    root: Path,
    *,
    cap: float = 10.0,
    concurrency: int = 2,
    control: RunControl | None = None,
) -> tuple[LeadStrategist, list[ScanEvent]]:
    bus = EventBus()
    events: list[ScanEvent] = []
    bus.subscribe(events.append)
    runtime = AgentRuntime(
        provider=provider,
        registry=default_registry(),
        context=ToolContext(root=root),
        ledger=BudgetLedger(cap_usd=cap, price=ModelPrice(1.0, 1.0), bus=bus),
        control=control or RunControl(),
        bus=bus,
        max_rounds=3,
    )
    return LeadStrategist(runtime, AgentCatalog([SQLI, XSS]), concurrency=concurrency), events


def test_full_scan_plans_dispatches_and_dedupes(sample_project: Path) -> None:
    provider = ScriptedProvider(
        {
            PLANNER: [call("fs_glob"), submit(**_plan(SQLI.name, XSS.name))],
            SQLI.name: [
                call("fs_grep", pattern="execute"),
                submit(hypotheses=[_hyp("sql-injection", "app/views.py", 6, "high")]),
            ],
            # Same bug reported again at lower severity, plus a distinct one.
            XSS.name: [
                submit(
                    hypotheses=[
                        _hyp("sql-injection", "app/views.py", 6, "low"),
                        _hyp("xss", "app/main.js", 1),
                    ]
                )
            ],
        }
    )
    strategist, events = _strategist(provider, sample_project)
    scan = strategist.run()

    assert scan.outcome is ScanOutcome.COMPLETED and scan.stop_reason is None
    assert not scan.fallback and scan.plan is not None
    assert [r.agent for r in scan.results] == [PLANNER, SQLI.name, XSS.name]
    assert {(h.category, h.suspected_severity) for h in scan.hypotheses} == {
        ("sql-injection", Severity.HIGH),
        ("xss", Severity.MEDIUM),
    }
    planned = next(e for e in events if isinstance(e, ScanPlanned))
    assert planned.agents == (SQLI.name, XSS.name)
    assert isinstance(events[-1], ScanFinished) and events[-1].hypotheses == 2


def test_unknown_agents_are_dropped(sample_project: Path) -> None:
    provider = ScriptedProvider(
        {
            PLANNER: [submit(**_plan("exfiltrator", XSS.name))],
            XSS.name: [submit(hypotheses=[])],
        }
    )
    strategist, _ = _strategist(provider, sample_project)
    scan = strategist.run()
    assert scan.plan is not None and [t.agent for t in scan.plan.tasks] == [XSS.name]
    assert not scan.fallback


def test_fallback_when_planner_fails(sample_project: Path) -> None:
    provider = ScriptedProvider(
        {
            # Planner only ever names agents that do not exist.
            PLANNER: [submit(**_plan("ghost"))],
            SQLI.name: [submit(hypotheses=[])],
            XSS.name: [submit(hypotheses=[])],
        }
    )
    strategist, events = _strategist(provider, sample_project)
    scan = strategist.run()
    assert scan.fallback
    assert sorted(r.agent for r in scan.results[1:]) == [SQLI.name, XSS.name]
    assert next(e for e in events if isinstance(e, ScanPlanned)).fallback


def test_max_tasks_caps_the_plan(sample_project: Path) -> None:
    provider = ScriptedProvider(
        {PLANNER: [submit(**_plan(SQLI.name, XSS.name))], SQLI.name: [submit(hypotheses=[])]}
    )
    strategist, _ = _strategist(provider, sample_project)
    strategist.max_tasks = 1
    scan = strategist.run()
    assert scan.plan is not None and len(scan.plan.tasks) == 1


def test_budget_stop_returns_partial(sample_project: Path) -> None:
    provider = ScriptedProvider({PLANNER: [submit(**_plan(SQLI.name, XSS.name))]})
    # The planner's single call spends the whole cap.
    strategist, events = _strategist(provider, sample_project, cap=0.0001)
    scan = strategist.run()
    assert scan.outcome is ScanOutcome.PARTIAL
    assert scan.stop_reason == "cost cap reached"
    assert {r.outcome for r in scan.results[1:]} == {AgentOutcome.BUDGET}
    assert isinstance(events[-1], ScanFinished)


def test_killed_planner_ends_scan(sample_project: Path) -> None:
    control = RunControl()
    control.kill_all()
    strategist, events = _strategist(ScriptedProvider({}), sample_project, control=control)
    scan = strategist.run()
    assert scan.plan is None and scan.outcome is ScanOutcome.PARTIAL
    assert scan.results[0].outcome is AgentOutcome.KILLED
    assert isinstance(events[-1], ScanFinished)


def test_failed_and_exhausted_agents_are_reported(sample_project: Path) -> None:
    provider = ScriptedProvider(
        {PLANNER: [submit(**_plan(SQLI.name))]}  # the hunter never submits
    )
    strategist, _ = _strategist(provider, sample_project)
    scan = strategist.run()
    assert scan.outcome is ScanOutcome.PARTIAL
    assert scan.stop_reason == "1 agent(s) hit the round limit"


def test_constructor_validation(sample_project: Path) -> None:
    strategist, _ = _strategist(ScriptedProvider({}), sample_project)
    with pytest.raises(ValueError, match="empty"):
        LeadStrategist(strategist.runtime, AgentCatalog())
    with pytest.raises(ValueError, match="at least 1"):
        LeadStrategist(strategist.runtime, AgentCatalog([SQLI]), concurrency=0)


def test_dedupe_without_location_uses_title() -> None:
    def hyp(title: str, severity: Severity, location: Location | None = None) -> Hypothesis:
        return Hypothesis(
            id=title + severity,
            title=title,
            category="xss",
            rationale="r",
            location=location,
            suspected_severity=severity,
            found_by="a",
        )

    out = dedupe_hypotheses(
        [
            hyp("Stored XSS", Severity.LOW),
            hyp("stored xss ", Severity.CRITICAL),
            hyp("Other", Severity.LOW),
            hyp("At line", Severity.LOW, Location(file="a.js", line=1)),
            hyp("At line", Severity.LOW, Location(file="a.js", line=2)),
        ]
    )
    assert [h.suspected_severity for h in out] == [
        Severity.CRITICAL,
        Severity.LOW,
        *[Severity.LOW] * 2,
    ]


class _InterruptingProvider:
    """Simulates Ctrl-C arriving while the planner waits on the model."""

    name = "interrupting"

    def complete(self, *args: object, **kwargs: object) -> object:
        raise KeyboardInterrupt

    def stream(self, *args: object, **kwargs: object) -> object:
        raise NotImplementedError


def test_ctrl_c_during_planning_returns_partial(sample_project: Path) -> None:
    strategist, events = _strategist(ScriptedProvider({}), sample_project)
    strategist.runtime.provider = _InterruptingProvider()  # type: ignore[assignment]
    scan = strategist.run()
    assert scan.outcome is ScanOutcome.PARTIAL and scan.plan is None
    assert strategist.runtime.control.killed_all
    assert isinstance(events[-1], ScanFinished)


def test_dedupe_normalizes_dot_slash() -> None:
    def hyp(file: str) -> Hypothesis:
        return Hypothesis(
            id=file,
            title="t",
            category="xss",
            rationale="r",
            location=Location(file=file, line=3),
            found_by="a",
        )

    assert len(dedupe_hypotheses([hyp("app.py"), hyp("./app.py")])) == 1
