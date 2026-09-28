"""Run control: the user's kill-switch and pause button, checked by every agent.

The live monitor (and a clean shutdown on Ctrl-C) talks to agents only through
:class:`RunControl`. Agents call :meth:`RunControl.checkpoint` between reasoning
rounds and before each tool call, so a stop request takes effect at the next safe
point. An in-flight provider request is not interrupted; it finishes, and the
agent stops right after it.

Every reason a run can stop early derives from :class:`ScanStopped`, so the
runtime can tell "stopped on purpose" (write a partial report) apart from a
genuine failure.
"""

from __future__ import annotations

import threading

__all__ = ["AgentKilled", "RunControl", "ScanKilled", "ScanStopped"]

# How often a paused agent re-checks for a kill request while it waits.
_PAUSE_POLL_SECONDS = 0.1


class ScanStopped(Exception):  # noqa: N818 - a stop signal, not an error
    """Base for every intentional early stop (kill-switch, budget cap)."""


class ScanKilled(ScanStopped):
    """The user stopped the whole scan."""


class AgentKilled(ScanStopped):
    """The user stopped one agent; the rest of the scan continues."""


class RunControl:
    """Thread-safe stop / pause state shared by the orchestrator and its agents."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._killed_all = False
        self._killed: set[str] = set()
        self._running = threading.Event()
        self._running.set()

    # --- commands (called by the UI) -----------------------------------------

    def kill_all(self) -> None:
        """Stop every agent at its next checkpoint. Also releases a pause."""
        with self._lock:
            self._killed_all = True
        self._running.set()

    def kill(self, run_id: str) -> None:
        """Stop one agent run at its next checkpoint."""
        with self._lock:
            self._killed.add(run_id)

    def pause(self) -> None:
        """Hold every agent at its next checkpoint until :meth:`resume`."""
        self._running.clear()

    def resume(self) -> None:
        """Release a pause."""
        self._running.set()

    # --- queries ---------------------------------------------------------------

    @property
    def killed_all(self) -> bool:
        with self._lock:
            return self._killed_all

    @property
    def paused(self) -> bool:
        return not self._running.is_set()

    def is_killed(self, run_id: str) -> bool:
        with self._lock:
            return self._killed_all or run_id in self._killed

    # --- the agent-side hook -----------------------------------------------------

    def checkpoint(self, run_id: str) -> None:
        """Block while paused; raise if this run (or the whole scan) was killed."""
        while not self._running.wait(_PAUSE_POLL_SECONDS):
            self._raise_if_killed(run_id)
        self._raise_if_killed(run_id)

    def _raise_if_killed(self, run_id: str) -> None:
        with self._lock:
            if self._killed_all:
                raise ScanKilled("scan stopped by the user")
            if run_id in self._killed:
                raise AgentKilled(f"agent run {run_id} stopped by the user")
