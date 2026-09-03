"""Tests for the domain models in ``reasonhound.models``."""

from __future__ import annotations

from datetime import UTC

import pytest
from pydantic import ValidationError

from reasonhound.models import (
    Confidence,
    Evidence,
    EvidenceKind,
    Finding,
    FindingStatus,
    Hypothesis,
    Location,
    ReasoningNote,
    Severity,
    VoteRole,
)


def _finding(**overrides: object) -> Finding:
    base: dict[str, object] = {
        "id": "F-001",
        "title": "SQL injection in search",
        "category": "sql-injection",
        "status": FindingStatus.CONFIRMED,
        "severity": Severity.CRITICAL,
        "confidence": Confidence.HIGH,
        "found_by": "injection-hunter",
    }
    base.update(overrides)
    return Finding.model_validate(base)


def test_finding_minimal_construction() -> None:
    finding = _finding()
    assert finding.status is FindingStatus.CONFIRMED
    assert finding.data_flow == []
    assert finding.evidence == []
    assert finding.first_seen.tzinfo is UTC


def test_extra_fields_are_forbidden() -> None:
    # Strict schema is the third prompt-injection defense layer.
    with pytest.raises(ValidationError):
        _finding(injected="rm -rf /")


def test_severity_and_confidence_ordering() -> None:
    order = sorted(Severity, key=lambda s: s.rank)
    assert order == [
        Severity.INFO,
        Severity.LOW,
        Severity.MEDIUM,
        Severity.HIGH,
        Severity.CRITICAL,
    ]
    assert Confidence.HIGH.rank > Confidence.LOW.rank


def test_location_normalizes_separators() -> None:
    loc = Location(file="src\\app\\views.py", line=42)
    assert loc.file == "src/app/views.py"


def test_location_rejects_zero_line() -> None:
    with pytest.raises(ValidationError):
        Location(file="a.py", line=0)


def test_cvss_bounds() -> None:
    assert _finding(cvss=9.8).cvss == 9.8
    with pytest.raises(ValidationError):
        _finding(cvss=11.0)


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("SQL injection in /api/search", "sql-injection-in-api-search"),
        ("   ", "finding"),
        ("XSS!!!", "xss"),
    ],
)
def test_slug(title: str, expected: str) -> None:
    assert _finding(title=title).slug == expected


def test_json_roundtrip_preserves_nested_models() -> None:
    finding = _finding(
        location=Location(file="src/db.py", line=10),
        evidence=[Evidence(kind=EvidenceKind.DYNAMIC, summary="timing delta", request="GET /?q=1")],
        reasoning=[
            ReasoningNote(role=VoteRole.ARBITER, agent="arbiter", rationale="survived refute")
        ],
    )
    restored = Finding.model_validate_json(finding.model_dump_json())
    assert restored == finding
    assert restored.evidence[0].kind is EvidenceKind.DYNAMIC
    assert restored.reasoning[0].role is VoteRole.ARBITER


def test_hypothesis_defaults() -> None:
    hyp = Hypothesis(
        id="H-1",
        title="Possible IDOR",
        category="idor",
        rationale="object id from user input, no ownership check",
        found_by="auth-logic-breaker",
    )
    assert hyp.suspected_severity is Severity.MEDIUM
    assert hyp.location is None
    assert hyp.created_at.tzinfo is UTC
