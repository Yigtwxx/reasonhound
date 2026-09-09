"""Retry policy shared by every BYOK adapter.

Provider APIs fail transiently: rate limits, overload, and dropped connections
are normal operating conditions, not bugs. This module keeps the backoff rules
in one place so all four adapters behave identically, and so the behavior can be
tested without sleeping or touching the network.

Deliberately dependency-free (no ``tenacity``): the base install stays light.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

import httpx

from reasonhound.providers.base import ProviderError

__all__ = [
    "DEFAULT_BASE_DELAY",
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_MAX_DELAY",
    "RETRYABLE_STATUS",
    "RetryPolicy",
    "parse_retry_after",
    "request_with_retry",
]

DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_BASE_DELAY = 0.5
DEFAULT_MAX_DELAY = 30.0

# Transient by contract: the same request may succeed later. Client errors that
# describe a broken request (400 / 401 / 403 / 404 / 413) are deliberately absent
# -- retrying them only burns the user's budget.
RETRYABLE_STATUS: frozenset[int] = frozenset({408, 409, 425, 429, 500, 502, 503, 504, 529})


@dataclass(frozen=True)
class RetryPolicy:
    """How many times to retry a provider call, and how long to wait between."""

    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    base_delay: float = DEFAULT_BASE_DELAY
    max_delay: float = DEFAULT_MAX_DELAY

    def backoff(self, attempt: int, *, retry_after: float | None = None) -> float:
        """Delay before *attempt* (1-based) is retried, capped at ``max_delay``.

        A server-supplied ``Retry-After`` always wins over the exponential curve:
        the provider knows better than we do when its limit resets.
        """
        if retry_after is not None:
            return min(max(retry_after, 0.0), self.max_delay)
        return min(self.base_delay * (2 ** max(attempt - 1, 0)), self.max_delay)


def parse_retry_after(value: str | None) -> float | None:
    """Parse a ``Retry-After`` header (delta-seconds or HTTP-date) into seconds.

    Returns ``None`` for a missing or unparseable value so the caller falls back
    to exponential backoff rather than failing.
    """
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        return max(float(raw), 0.0)
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    delta = when.timestamp() - time.time()
    return max(delta, 0.0)


def _default_jitter(delay: float) -> float:
    """Spread retries so concurrent agents do not all wake at the same instant."""
    return delay + random.uniform(0.0, delay * 0.25)


def request_with_retry(
    send: Callable[[], httpx.Response],
    *,
    policy: RetryPolicy | None = None,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[float], float] = _default_jitter,
) -> httpx.Response:
    """Call *send* until it yields a non-retryable response or attempts run out.

    The final response is returned **whatever its status** -- mapping an error
    status to a message is the adapter's job, because only the adapter knows how
    its provider shapes an error body. Only transport failures that survive every
    attempt are raised here, as :class:`ProviderError`.

    Retryable responses are closed before the next attempt so a streaming
    connection is never left dangling.
    """
    policy = policy or RetryPolicy()
    last_error: Exception | None = None

    for attempt in range(1, policy.max_attempts + 1):
        try:
            response = send()
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = exc
            if attempt == policy.max_attempts:
                break
            sleep(jitter(policy.backoff(attempt)))
            continue

        if response.status_code not in RETRYABLE_STATUS or attempt == policy.max_attempts:
            return response

        retry_after = parse_retry_after(response.headers.get("retry-after"))
        response.close()
        sleep(jitter(policy.backoff(attempt, retry_after=retry_after)))

    # Only reachable when every attempt raised a transport error.
    raise ProviderError(
        f"provider request failed after {policy.max_attempts} attempts: {type(last_error).__name__}"
    ) from last_error
