"""Agent output contracts: what an agent may hand back through ``submit_result``.

These are the strict schemas of prompt-injection defense layer 3. The model
fills a *draft*; the runtime adds everything the model must not choose itself
(ids, attribution, timestamps) when it converts the draft into a domain object.
"""

from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from reasonhound.models import Hypothesis, Location, Severity

__all__ = ["AgentReport", "HunterReport", "HypothesisDraft"]


class AgentReport(BaseModel):
    """Base for every agent output: unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")


class HypothesisDraft(AgentReport):
    """A candidate vulnerability as the model reports it."""

    title: str = Field(min_length=1, max_length=200)
    category: str = Field(
        min_length=1, max_length=64, description="Vulnerability class, e.g. 'sql-injection'."
    )
    rationale: str = Field(
        min_length=1, description="Why this is plausibly exploitable, citing the code you read."
    )
    location: Location | None = None
    suspected_severity: Severity = Severity.MEDIUM

    @field_validator("location")
    @classmethod
    def _repo_relative(cls, value: Location | None) -> Location | None:
        # The path ends up in report filenames and links: keep it inside the repo.
        if value is None:
            return value
        path = PurePosixPath(value.file)
        if path.is_absolute() or PureWindowsPath(value.file).drive or ".." in path.parts:
            raise ValueError("location.file must be a repo-relative path")
        return value

    def to_hypothesis(self, *, found_by: str) -> Hypothesis:
        return Hypothesis(
            id=f"H-{uuid4().hex[:10]}",
            title=self.title,
            category=self.category.strip().lower(),
            rationale=self.rationale,
            location=self.location,
            suspected_severity=self.suspected_severity,
            found_by=found_by,
        )


class HunterReport(AgentReport):
    """What a hunter submits: its hypotheses plus the leads it dropped, and why."""

    hypotheses: list[HypothesisDraft] = Field(default_factory=list, max_length=50)
    notes: str = Field(
        default="", description="Leads you investigated and dropped, and why (the pivot trail)."
    )
