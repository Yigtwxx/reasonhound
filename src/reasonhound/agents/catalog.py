"""The agent catalog: the subagents the orchestrator is allowed to dispatch.

The orchestrator plans only in terms of catalog names; a plan naming anything
else is dropped. The library of specialists (recon, hunters, verifiers) is
registered here as each phase lands.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from reasonhound.agents.base import AgentSpec

__all__ = ["AgentCatalog"]


class AgentCatalog:
    """Name -> :class:`AgentSpec`, in registration order."""

    def __init__(self, specs: Iterable[AgentSpec] = ()) -> None:
        self._specs: dict[str, AgentSpec] = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec: AgentSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"agent {spec.name!r} is already registered")
        self._specs[spec.name] = spec

    def get(self, name: str) -> AgentSpec | None:
        return self._specs.get(name)

    def __contains__(self, name: object) -> bool:
        return name in self._specs

    def __iter__(self) -> Iterator[AgentSpec]:
        return iter(self._specs.values())

    def __len__(self) -> int:
        return len(self._specs)

    def describe(self) -> str:
        """One ``- name: role`` line per agent, for the planner's prompt."""
        return "\n".join(f"- {spec.name}: {spec.role}" for spec in self)
