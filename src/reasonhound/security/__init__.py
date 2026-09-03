"""Cross-cutting security primitives: redaction, data-fencing, audit, egress.

These enforce the hard constraints in ``docs/DESIGN.md`` section 7 and are used
by every provider call (redaction), every agent (fencing), and the dynamic phase
(egress + audit).
"""

from __future__ import annotations

from reasonhound.security.audit import AuditLog, audit_path
from reasonhound.security.egress import (
    AllowlistEgress,
    EgressError,
    EgressPolicy,
    LocalhostEgress,
    target_from_url,
)
from reasonhound.security.fencing import FENCE_BEGIN, FENCE_END, fence
from reasonhound.security.redactor import Redactor, redact, redact_json

__all__ = [
    "FENCE_BEGIN",
    "FENCE_END",
    "AllowlistEgress",
    "AuditLog",
    "EgressError",
    "EgressPolicy",
    "LocalhostEgress",
    "Redactor",
    "audit_path",
    "fence",
    "redact",
    "redact_json",
    "target_from_url",
]
