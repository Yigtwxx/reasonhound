"""Domain models shared across the scan pipeline.

These Pydantic v2 schemas are the single source of truth for the objects that
flow from the hunters (``Hypothesis``) through verification to the report
(``Finding``). They double as the **agent-output contract**: agents must return
data that validates against these strict schemas (``extra="forbid"``), which is
the third layer of the prompt-injection defense described in
``docs/DESIGN.md`` section 7 — an agent cannot smuggle unexpected fields or
free-form instructions past validation.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "Confidence",
    "DataFlowStep",
    "Evidence",
    "EvidenceKind",
    "Finding",
    "FindingStatus",
    "Hypothesis",
    "Location",
    "ReasoningNote",
    "Severity",
    "VoteRole",
]


def _utcnow() -> datetime:
    """Timezone-aware UTC timestamp (default for time fields)."""
    return datetime.now(UTC)


class Severity(StrEnum):
    """Impact rating, ordered low to high via :pyattr:`rank`."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        """Numeric order (higher = more severe) for sorting the report."""
        return _SEVERITY_RANK[self]


class Confidence(StrEnum):
    """How sure the arbiter is about a finding, ordered via :pyattr:`rank`."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def rank(self) -> int:
        """Numeric order (higher = more confident)."""
        return _CONFIDENCE_RANK[self]


class FindingStatus(StrEnum):
    """Lifecycle state assigned by the arbiter and updated on re-runs."""

    CONFIRMED = "confirmed"
    SUSPECTED = "suspected"
    REJECTED = "rejected"
    RESOLVED = "resolved"


class EvidenceKind(StrEnum):
    """Where a piece of evidence came from."""

    STATIC = "static"
    DYNAMIC = "dynamic"


class VoteRole(StrEnum):
    """Role of an agent in the double-voting verification stage."""

    RED = "red"
    BLUE = "blue"
    ARBITER = "arbiter"


_SEVERITY_RANK: dict[Severity, int] = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}

_CONFIDENCE_RANK: dict[Confidence, int] = {
    Confidence.LOW: 0,
    Confidence.MEDIUM: 1,
    Confidence.HIGH: 2,
}


class _Strict(BaseModel):
    """Base for all domain models: forbid unknown fields, validate on assignment."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Location(_Strict):
    """A place in the scanned code, as a repo-relative path plus optional lines."""

    file: str = Field(description="Repo-relative path, POSIX separators.")
    line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    snippet: str | None = None

    @field_validator("file")
    @classmethod
    def _normalize_separators(cls, value: str) -> str:
        # Store POSIX-style paths so reports are identical across OSes.
        return value.replace("\\", "/")


class DataFlowStep(_Strict):
    """One hop in a tainted source -> sink trace."""

    location: Location
    note: str | None = None


class Evidence(_Strict):
    """Support for a finding: a static observation or a dynamic probe capture."""

    kind: EvidenceKind
    summary: str
    request: str | None = None
    response: str | None = None


class ReasoningNote(_Strict):
    """One entry in the double-voting trail (red / blue / arbiter)."""

    role: VoteRole
    agent: str
    rationale: str
    verdict: str | None = None


class Hypothesis(_Strict):
    """A candidate vulnerability emitted by a hunter, before verification."""

    id: str
    title: str
    category: str = Field(description="Vulnerability class, e.g. 'sql-injection'.")
    rationale: str
    location: Location | None = None
    suspected_severity: Severity = Severity.MEDIUM
    found_by: str = Field(description="Name of the agent that raised it.")
    created_at: datetime = Field(default_factory=_utcnow)


class Finding(_Strict):
    """A verified (or refuted) result, rendered to its own Markdown file."""

    id: str
    title: str
    category: str
    status: FindingStatus
    severity: Severity
    confidence: Confidence
    cvss: float | None = Field(default=None, ge=0.0, le=10.0)
    cvss_vector: str | None = None
    location: Location | None = None
    data_flow: list[DataFlowStep] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    poc: str | None = None
    remediation: str | None = None
    reasoning: list[ReasoningNote] = Field(default_factory=list)
    found_by: str = Field(description="Agent that first raised the hypothesis.")
    hypothesis_id: str | None = None
    first_seen: datetime = Field(default_factory=_utcnow)
    last_seen: datetime = Field(default_factory=_utcnow)

    @property
    def slug(self) -> str:
        """Filename-safe slug derived from the title (used by the report writer)."""
        slug = re.sub(r"[^a-z0-9]+", "-", self.title.lower()).strip("-")
        return slug or "finding"
