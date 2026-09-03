"""Secret / PII redaction applied to everything before it leaves the machine.

This is the always-on base layer of the egress-safety model: named-pattern rules
catch well-known credential shapes, and an entropy pass catches long random
tokens the rules miss. It errs toward over-redaction — never leaking a secret to
a provider matters more than preserving an opaque blob in the prompt.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable

__all__ = ["DEFAULT_REDACTOR", "Redactor", "redact", "redact_json"]

_PLACEHOLDER = "[REDACTED:{label}]"


class _Rule:
    """A single redaction pattern. If *group* is 0 the whole match is replaced,
    otherwise only that capture group (so surrounding context is preserved).
    A negative *group* replaces whichever alternative group participated."""

    def __init__(self, label: str, pattern: str, *, group: int = 0, flags: int = 0) -> None:
        self.label = label
        self.regex = re.compile(pattern, flags)
        self.group = group

    def apply(self, text: str) -> str:
        placeholder = _PLACEHOLDER.format(label=self.label)

        def repl(match: re.Match[str]) -> str:
            if self.group == 0:
                return placeholder
            group = self.group
            if group < 0:  # first participating alternative group
                group = next(
                    i for i in range(1, self.regex.groups + 1) if match.group(i) is not None
                )
            full = match.group(0)
            g_start = match.start(group) - match.start(0)
            g_end = match.end(group) - match.start(0)
            return full[:g_start] + placeholder + full[g_end:]

        return self.regex.sub(repl, text)


_RULES: tuple[_Rule, ...] = (
    _Rule(
        "private-key",
        r"-----BEGIN[A-Z ]*PRIVATE KEY-----.*?-----END[A-Z ]*PRIVATE KEY-----",
        flags=re.DOTALL,
    ),
    _Rule("jwt", r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    _Rule("aws-access-key", r"AKIA[0-9A-Z]{16}"),
    _Rule("google-api-key", r"AIza[0-9A-Za-z_\-]{35}"),
    _Rule("slack-token", r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    _Rule("github-token", r"gh[pousr]_[A-Za-z0-9]{36,}"),
    _Rule("api-key", r"sk-(?:ant-|proj-)?[A-Za-z0-9_\-]{20,}"),
    _Rule("bearer", r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}"),
    _Rule(
        "basic-auth",
        r"""(?i)authorization["']?\s*[:=]\s*["']?basic\s+([A-Za-z0-9+/=]{8,})""",
        group=1,
    ),
    # Credentials embedded in connection URLs: scheme://user:PASSWORD@host
    _Rule(
        "url-credential",
        r"""(?i)\b[a-z][a-z0-9+.\-]*://[^\s:/@"']*:([^\s@"']+)@""",
        group=1,
    ),
    # Assignments / JSON pairs whose key *contains* a credential keyword
    # (SECRET_KEY, JWT_SECRET_KEY, secretKey, DB_PASSWORD, ...). The value must
    # be a quoted literal or a bare .env-style token; identifier chains, calls
    # and subscripts (os.environ.get(...), request.form[...]) are left intact
    # because they are exactly the taint sources the static engine must see.
    _Rule(
        "secret",
        r"(?i)(?:api[_-]?key|secret|token|password|passwd|pwd|access[_-]?key)\w*"
        r"""["']?\s*[:=]\s*(?:"""
        r'"([^"\r\n]{4,})"'  # double-quoted literal
        r"|'([^'\r\n]{4,})'"  # single-quoted literal
        r"|(?!(?:string|number|boolean|object|unknown|undefined|required|nullable)\b)"
        r"""([^\s"'`()\[\]{},;]{6,})(?![\w.(\[])"""  # bare .env-style token
        r")",
        group=-1,
    ),
    # The lookbehind anchors the local part so a long run without '@' (hex blobs,
    # minified bundles) is scanned once instead of re-tried from every offset.
    _Rule(
        "email",
        r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",
    ),
)

_ENTROPY_TOKEN = re.compile(r"[A-Za-z0-9+/=_\-]{32,}")
_UPPER = re.compile(r"[A-Z]")
_LOWER = re.compile(r"[a-z]")
_DIGIT = re.compile(r"[0-9]")


def _looks_like_path(token: str) -> bool:
    """Slash-bearing tokens are routes / URLs / package paths unless they carry
    the base64 signature (upper + lower + digit); a random base64 secret lacks
    one of those classes with negligible probability, a path almost always does."""
    if "/" not in token:
        return False
    return not (_UPPER.search(token) and _LOWER.search(token) and _DIGIT.search(token))


def _shannon_entropy(value: str) -> float:
    """Shannon entropy in bits per character."""
    counts = Counter(value)
    length = len(value)
    return -sum((n / length) * math.log2(n / length) for n in counts.values())


class Redactor:
    """Applies the rule set plus a high-entropy pass to text or JSON structures."""

    def __init__(self, *, entropy_threshold: float = 4.0) -> None:
        self.entropy_threshold = entropy_threshold

    def redact(self, text: str) -> str:
        for rule in _RULES:
            text = rule.apply(text)
        return self._entropy_pass(text)

    def _entropy_pass(self, text: str) -> str:
        def repl(match: re.Match[str]) -> str:
            token = match.group(0)
            if _looks_like_path(token):
                return token
            if _shannon_entropy(token) >= self.entropy_threshold:
                return _PLACEHOLDER.format(label="high-entropy")
            return token

        return _ENTROPY_TOKEN.sub(repl, text)

    def redact_json(self, obj: object) -> object:
        """Recursively redact string values inside dicts / lists / tuples."""
        if isinstance(obj, str):
            return self.redact(obj)
        if isinstance(obj, dict):
            return {key: self.redact_json(value) for key, value in obj.items()}
        if isinstance(obj, (list, tuple)):
            return type(obj)(self.redact_json(item) for item in obj)
        return obj


DEFAULT_REDACTOR = Redactor()


def redact(text: str) -> str:
    """Redact secrets/PII from *text* using the default redactor."""
    return DEFAULT_REDACTOR.redact(text)


def redact_json(obj: object) -> object:
    """Redact secrets/PII from every string in a JSON-like structure."""
    return DEFAULT_REDACTOR.redact_json(obj)


def _iter_rule_labels() -> Iterable[str]:  # pragma: no cover - introspection helper
    return (rule.label for rule in _RULES)
