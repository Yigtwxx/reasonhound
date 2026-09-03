"""Egress policy: constrain where the dynamic phase may send network probes.

The dynamic phase runs in an egress-locked environment; ``escape-watchdog`` uses
these policies to allow only the intended target and abort on anything else.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from urllib.parse import urlsplit

__all__ = [
    "AllowlistEgress",
    "EgressError",
    "EgressPolicy",
    "LocalhostEgress",
    "target_from_url",
]

_DEFAULT_PORTS = {"http": 80, "https": 443}
_LOCALHOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class EgressError(Exception):
    """Raised when a probe targets a host/port outside the allowed scope."""


def target_from_url(url: str) -> tuple[str, int]:
    """Parse *url* into a ``(host, port)`` pair, filling default ports.

    Raises :class:`EgressError` (fail closed) for anything that cannot be scoped:
    a malformed URL, a missing host, an invalid port, or a non-HTTP scheme.
    """
    try:
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        if scheme not in _DEFAULT_PORTS:
            raise EgressError(f"unsupported scheme for egress: {url!r}")
        host = parts.hostname
        if not host:
            raise EgressError(f"URL has no host: {url!r}")
        port = parts.port  # ``None`` when absent; an explicit ``:0`` stays 0
    except ValueError as exc:
        raise EgressError(f"unparseable URL blocked: {url!r} ({exc})") from exc
    if port is None:
        port = _DEFAULT_PORTS[scheme]
    return host, port


class EgressPolicy(ABC):
    """Decides whether a probe to ``(host, port)`` is in scope."""

    @abstractmethod
    def allows(self, host: str, port: int) -> bool: ...

    def check(self, url: str) -> None:
        """Raise :class:`EgressError` if *url* is out of scope."""
        host, port = target_from_url(url)
        if not self.allows(host, port):
            raise EgressError(f"out-of-scope egress blocked: {host}:{port}")


class AllowlistEgress(EgressPolicy):
    """Allows only an explicit set of ``(host, port)`` targets."""

    def __init__(self, targets: Iterable[tuple[str, int]]) -> None:
        self._targets = frozenset(targets)

    def allows(self, host: str, port: int) -> bool:
        return (host, port) in self._targets


class LocalhostEgress(EgressPolicy):
    """Allows only loopback hosts on a single port (Docker-absent fallback)."""

    def __init__(self, port: int) -> None:
        self.port = port

    def allows(self, host: str, port: int) -> bool:
        return host in _LOCALHOSTS and port == self.port
