"""Append-only audit log of everything the scan does that touches the target.

Every probe and gated action is recorded as one redacted JSON line in
``Reasonhound/audit.log`` for accountability. Records are passed through the
redactor so no credential is ever persisted, even locally.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from reasonhound.config import AUDIT_FILENAME, REPORT_DIRNAME
from reasonhound.security.redactor import redact_json

__all__ = ["AuditLog", "audit_path"]


def audit_path(root: Path) -> Path:
    """Location of the audit log for a project root."""
    return root / REPORT_DIRNAME / AUDIT_FILENAME


class AuditLog:
    """Appends redacted, timestamped JSON-line records to the audit log."""

    def __init__(self, root: Path) -> None:
        self.path = audit_path(root)

    def record(self, action: str, **fields: object) -> dict[str, object]:
        """Append one audit record and return the redacted entry that was written."""
        raw: dict[str, object] = {
            "ts": datetime.now(UTC).isoformat(),
            "action": action,
            **fields,
        }
        # Normalize to plain JSON types first (so ``default=str`` fallbacks are
        # redacted too), then redact the *structure* rather than the serialized
        # text: string values containing nested JSON keep their unescaped quotes,
        # which the key/value rules rely on.
        entry: dict[str, object] = json.loads(json.dumps(raw, ensure_ascii=False, default=str))
        entry = redact_json(entry)  # type: ignore[assignment]
        line = json.dumps(entry, ensure_ascii=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return entry
