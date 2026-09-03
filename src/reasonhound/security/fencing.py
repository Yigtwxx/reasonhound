"""Data-fencing: wrap untrusted file content so the model treats it as data.

Scanned code is untrusted input to the reasoning LLM. ``fence`` wraps content in
explicit delimiters and neutralizes any fence markers the content itself
contains, so an attacker cannot close the fence early and inject instructions.
"""

from __future__ import annotations

import re

__all__ = ["FENCE_BEGIN", "FENCE_END", "fence"]

FENCE_BEGIN = "[BEGIN UNTRUSTED DATA]"
FENCE_END = "[END UNTRUSTED DATA]"

_MARKER = re.compile(r"(?i)\[\s*(begin|end)\s+untrusted\s+data[^\]]*\]")


def _neutralize(content: str) -> str:
    # Turn any embedded fence marker into harmless parentheses so it cannot be
    # mistaken for the real delimiter that closes/opens the block.
    return _MARKER.sub(lambda m: "(" + m.group(0)[1:-1] + ")", content)


_SOURCE_UNSAFE = re.compile(r"[\[\]\r\n]")


def _safe_source(source: str) -> str:
    # The source label is attacker-controlled too (it is a file name from the
    # scanned repo): strip brackets and line breaks so it can neither close the
    # BEGIN marker early nor smuggle a forged marker onto its own line.
    return _SOURCE_UNSAFE.sub(" ", source)


def fence(content: str, *, source: str | None = None) -> str:
    """Return *content* wrapped as clearly-delimited untrusted data.

    The reasoning prompt instructs the model that anything between the markers is
    data to analyze, never instructions to follow.
    """
    begin = (
        FENCE_BEGIN if source is None else f"[BEGIN UNTRUSTED DATA source={_safe_source(source)}]"
    )
    return f"{begin}\n{_neutralize(content)}\n{FENCE_END}"
