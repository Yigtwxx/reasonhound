"""``lead-strategist``: plan the scan, dispatch subagents in parallel, collect results.

The orchestrator is itself an agent: it may look around the project
(``fs_glob`` / ``fs_read``) and must submit a :class:`ScanPlan` naming agents
from the catalog. Unknown names are dropped; if nothing usable is left, it
falls back to running every catalog agent once, so a weak planning model can
cost quality but never stall the scan.

Planned runs execute on a thread pool (the provider adapters are synchronous and
their ``httpx`` client is thread-safe). Stops are cooperative: the kill-switch,
the cost cap and Ctrl-C all make agents halt at their next checkpoint, and the
scan still returns whatever was collected -- a partial result, never nothing.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from pydantic import Field

from reasonhound.agents.base import (
    AgentResult,
    AgentRuntime,
    AgentSpec,
    AgentTask,
    run_agent,
)
from reasonhound.agents.catalog import AgentCatalog
from reasonhound.agents.contracts import AgentReport
from reasonhound.config import DEFAULT_CONCURRENCY
from reasonhound.events import AgentOutcome, ScanFinished, ScanOutcome, ScanPlanned
from reasonhound.models import Hypothesis

__all__ = [
    "DEFAULT_GOAL",
    "DEFAULT_MAX_TASKS",
    "LEAD_STRATEGIST",
    "LeadStrategist",
    "PlannedTask",
    "ScanPlan",
    "ScanResult",
    "dedupe_hypotheses",
]

DEFAULT_GOAL = (
    "Find exploitable security vulnerabilities in this project, prioritizing "
    "externally reachable code paths."
)
DEFAULT_MAX_TASKS = 12

# How often the main thread wakes while waiting on agents (keeps Ctrl-C responsive).
_POLL_SECONDS = 0.5


class PlannedTask(AgentReport):
    agent: str = Field(description="Agent name, exactly as listed in the catalog.")
    objective: str = Field(min_length=1, max_length=2000)
    focus: list[str] = Field(
        default_factory=list, max_length=20, description="Repo-relative paths to start from."
    )


class ScanPlan(AgentReport):
    rationale: str = Field(description="Why these agents, in one or two sentences.")
    tasks: list[PlannedTask] = Field(min_length=1)


LEAD_STRATEGIST = AgentSpec(
    name="lead-strategist",
    role="Plans the scan: decides which specialist agents to run, on what, and how many.",
    instructions=(
        "Survey the project's layout (fs_glob, and fs_read on manifests or entry "
        "points when useful), then submit a plan. Each task names one agent from the "
        "catalog you are given, a concrete objective, and the paths it should start "
        "from. Prefer fewer, well-aimed tasks over running everything: every task "
        "costs the user money."
    ),
    tools=frozenset({"fs_glob", "fs_read"}),
    output=ScanPlan,
    max_rounds=6,
)


@dataclass
class ScanResult:
    """Everything one scan produced."""

    plan: ScanPlan | None
    fallback: bool
    results: list[AgentResult] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    outcome: ScanOutcome = ScanOutcome.COMPLETED
    stop_reason: str | None = None


def dedupe_hypotheses(hypotheses: list[Hypothesis]) -> list[Hypothesis]:
    """Collapse duplicates raised by different agents, keeping the most severe.

    Two hypotheses are the same when they share a category and a location (file
    + line), or a category and a title when neither has a location. First-seen
    order is kept so the result is stable.
    """
    kept: dict[tuple[str, ...], Hypothesis] = {}
    for hypothesis in hypotheses:
        key = _dedupe_key(hypothesis)
        current = kept.get(key)
        if current is None or hypothesis.suspected_severity.rank > current.suspected_severity.rank:
            kept[key] = hypothesis
    return list(kept.values())


def _dedupe_key(hypothesis: Hypothesis) -> tuple[str, ...]:
    category = hypothesis.category.strip().lower()
    location = hypothesis.location
    if location is not None:
        return (category, PurePosixPath(location.file).as_posix(), str(location.line or 0))
    return (category, "", hypothesis.title.strip().lower())


class LeadStrategist:
    """Plans and runs one scan over a catalog of subagents."""

    def __init__(
        self,
        runtime: AgentRuntime,
        catalog: AgentCatalog,
        *,
        concurrency: int = DEFAULT_CONCURRENCY,
        max_tasks: int = DEFAULT_MAX_TASKS,
    ) -> None:
        if len(catalog) == 0:
            raise ValueError("the agent catalog is empty")
        if concurrency < 1 or max_tasks < 1:
            raise ValueError("concurrency and max_tasks must be at least 1")
        self.runtime = runtime
        self.catalog = catalog
        self.concurrency = concurrency
        self.max_tasks = max_tasks

    # --- planning -----------------------------------------------------------------

    def plan(self, goal: str = DEFAULT_GOAL) -> tuple[ScanPlan | None, bool, AgentResult]:
        """Ask the planner for a plan; returns ``(plan, fallback, planner_result)``.

        ``plan`` is ``None`` only when the planner was stopped (kill / cost cap):
        then there is nothing to dispatch.
        """
        objective = (
            f"{goal}\n\nPlan at most {self.max_tasks} task(s). Available agents:\n"
            f"{self.catalog.describe()}"
        )
        result = run_agent(LEAD_STRATEGIST, AgentTask(objective=objective), self.runtime)
        if result.outcome in (AgentOutcome.KILLED, AgentOutcome.BUDGET):
            return None, False, result
        if isinstance(result.output, ScanPlan):
            usable = [task for task in result.output.tasks if task.agent in self.catalog]
            if usable:
                plan = ScanPlan(rationale=result.output.rationale, tasks=usable[: self.max_tasks])
                return plan, False, result
        return self._fallback_plan(goal), True, result

    def _fallback_plan(self, goal: str) -> ScanPlan:
        tasks = [PlannedTask(agent=spec.name, objective=goal) for spec in self.catalog]
        return ScanPlan(
            rationale="Planner produced no usable plan; running every catalog agent once.",
            tasks=tasks[: self.max_tasks],
        )

    # --- execution ------------------------------------------------------------------

    def execute(self, plan: ScanPlan) -> list[AgentResult]:
        """Run every planned task, at most ``concurrency`` at a time."""
        jobs: list[tuple[AgentSpec, AgentTask]] = []
        for task in plan.tasks:
            spec = self.catalog.get(task.agent)
            if spec is not None:
                jobs.append((spec, AgentTask(objective=task.objective, focus=tuple(task.focus))))
        if not jobs:
            return []

        workers = min(self.concurrency, len(jobs))
        pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="agent")
        futures: list[Future[AgentResult]] = []
        try:
            for spec, task in jobs:
                futures.append(pool.submit(run_agent, spec, task, self.runtime))
            return [self._collect(future) for future in futures]
        except KeyboardInterrupt:
            # Ctrl-C outside _collect (e.g. while submitting): stop everything that
            # started, keep what it produced. Unsubmitted jobs simply never run.
            self.runtime.control.kill_all()
            return [self._collect(future) for future in futures]
        finally:
            pool.shutdown(wait=True)

    def _collect(self, future: Future[AgentResult]) -> AgentResult:
        """Wait for one run; Ctrl-C while waiting triggers the kill-switch.

        The wait polls: on Windows an untimed wait cannot be interrupted, so
        Ctrl-C would otherwise go unnoticed until an agent finished.
        """
        while True:
            try:
                return future.result(timeout=_POLL_SECONDS)
            except TimeoutError:
                continue
            except KeyboardInterrupt:
                self.runtime.control.kill_all()

    # --- the whole scan -------------------------------------------------------------

    def run(self, goal: str = DEFAULT_GOAL) -> ScanResult:
        """Plan, dispatch, dedupe; always returns what was collected."""
        plan, fallback, planner = self.plan(goal)
        if plan is None:
            scan = ScanResult(
                plan=None,
                fallback=False,
                results=[planner],
                outcome=ScanOutcome.PARTIAL,
                stop_reason=planner.error,
            )
            self._finish(scan)
            return scan

        self.runtime.bus.publish(
            ScanPlanned(
                agents=tuple(task.agent for task in plan.tasks),
                rationale=plan.rationale,
                fallback=fallback,
            )
        )
        results = self.execute(plan)
        hypotheses = dedupe_hypotheses([h for result in results for h in result.hypotheses])
        outcome, reason = _summarize(results)
        scan = ScanResult(
            plan=plan,
            fallback=fallback,
            results=[planner, *results],
            hypotheses=hypotheses,
            outcome=outcome,
            stop_reason=reason,
        )
        self._finish(scan)
        return scan

    def _finish(self, scan: ScanResult) -> None:
        self.runtime.bus.publish(
            ScanFinished(
                outcome=scan.outcome,
                hypotheses=len(scan.hypotheses),
                stop_reason=scan.stop_reason,
            )
        )


def _summarize(results: list[AgentResult]) -> tuple[ScanOutcome, str | None]:
    """Scan outcome plus a one-line reason whenever it is not a clean finish."""
    counts: dict[AgentOutcome, int] = {}
    for result in results:
        counts[result.outcome] = counts.get(result.outcome, 0) + 1
    reasons: list[str] = []
    if counts.get(AgentOutcome.BUDGET):
        reasons.append("cost cap reached")
    if counts.get(AgentOutcome.KILLED):
        reasons.append(f"{counts[AgentOutcome.KILLED]} agent(s) stopped by the user")
    if counts.get(AgentOutcome.FAILED):
        reasons.append(f"{counts[AgentOutcome.FAILED]} agent(s) failed")
    if counts.get(AgentOutcome.EXHAUSTED):
        reasons.append(f"{counts[AgentOutcome.EXHAUSTED]} agent(s) hit the round limit")
    if not reasons:
        return ScanOutcome.COMPLETED, None
    return ScanOutcome.PARTIAL, "; ".join(reasons)
