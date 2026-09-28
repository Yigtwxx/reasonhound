"""The subagent runtime and library.

:mod:`reasonhound.agents.base` holds the bounded agent loop; contracts define
what agents may return; the catalog lists what the orchestrator may dispatch.
"""

from __future__ import annotations

from reasonhound.agents.base import (
    SUBMIT_TOOL,
    AgentResult,
    AgentRuntime,
    AgentSpec,
    AgentTask,
    build_system_prompt,
    run_agent,
)
from reasonhound.agents.catalog import AgentCatalog
from reasonhound.agents.contracts import AgentReport, HunterReport, HypothesisDraft
from reasonhound.events import AgentOutcome

__all__ = [
    "SUBMIT_TOOL",
    "AgentCatalog",
    "AgentOutcome",
    "AgentReport",
    "AgentResult",
    "AgentRuntime",
    "AgentSpec",
    "AgentTask",
    "HunterReport",
    "HypothesisDraft",
    "build_system_prompt",
    "run_agent",
]
