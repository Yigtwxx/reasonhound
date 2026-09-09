"""Tests for the retry policy shared by every adapter."""

from __future__ import annotations

from email.utils import formatdate

import httpx
import pytest

from reasonhound.providers.base import ProviderError
from reasonhound.providers.retry import (
    RetryPolicy,
    parse_retry_after,
    request_with_retry,
)

NO_JITTER = staticmethod(lambda delay: delay)


def _recorder() -> tuple[list[float], object]:
    slept: list[float] = []
    return slept, slept.append


# --- backoff curve -----------------------------------------------------------


def test_backoff_grows_exponentially_and_caps() -> None:
    policy = RetryPolicy(base_delay=1.0, max_delay=4.0)
    delays = [policy.backoff(attempt) for attempt in range(1, 5)]
    assert delays == [1.0, 2.0, 4.0, 4.0], f"expected a capped doubling curve, got {delays}"


def test_backoff_prefers_retry_after_over_the_curve() -> None:
    policy = RetryPolicy(base_delay=1.0, max_delay=30.0)
    assert policy.backoff(1, retry_after=7.0) == 7.0


def test_backoff_clamps_a_hostile_retry_after() -> None:
    policy = RetryPolicy(max_delay=30.0)
    assert policy.backoff(1, retry_after=99999.0) == 30.0


# --- Retry-After parsing -----------------------------------------------------


def test_parse_retry_after_seconds() -> None:
    assert parse_retry_after("12") == 12.0


def test_parse_retry_after_http_date_is_in_the_future() -> None:
    value = parse_retry_after(formatdate(timeval=None, usegmt=True))
    assert value is not None and value >= 0.0


@pytest.mark.parametrize("value", [None, "", "   ", "soon", "not-a-date"])
def test_parse_retry_after_invalid_returns_none(value: str | None) -> None:
    assert parse_retry_after(value) is None


def test_parse_retry_after_negative_is_clamped_to_zero() -> None:
    assert parse_retry_after("-5") == 0.0


# --- the retry loop ----------------------------------------------------------


def test_success_on_first_attempt_never_sleeps() -> None:
    slept, record = _recorder()
    calls = 0

    def send() -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200)

    response = request_with_retry(send, sleep=record, jitter=NO_JITTER)

    assert response.status_code == 200
    assert calls == 1, f"expected a single attempt, got {calls}"
    assert slept == []


def test_retries_429_then_succeeds() -> None:
    slept, record = _recorder()
    responses = [httpx.Response(429), httpx.Response(200)]

    response = request_with_retry(
        lambda: responses.pop(0),
        policy=RetryPolicy(base_delay=1.0),
        sleep=record,
        jitter=NO_JITTER,
    )

    assert response.status_code == 200
    assert slept == [1.0], f"expected one backoff sleep, got {slept}"


def test_honors_retry_after_header() -> None:
    slept, record = _recorder()
    responses = [httpx.Response(429, headers={"retry-after": "3"}), httpx.Response(200)]

    request_with_retry(
        lambda: responses.pop(0),
        policy=RetryPolicy(base_delay=1.0),
        sleep=record,
        jitter=NO_JITTER,
    )

    assert slept == [3.0], f"expected the server-supplied delay, got {slept}"


@pytest.mark.parametrize("status", [400, 401, 403, 404, 413])
def test_does_not_retry_client_errors(status: int) -> None:
    slept, record = _recorder()
    calls = 0

    def send() -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status)

    response = request_with_retry(send, sleep=record, jitter=NO_JITTER)

    assert response.status_code == status
    assert calls == 1, f"a {status} must not be retried, but ran {calls} attempts"
    assert slept == []


def test_returns_the_last_response_when_attempts_run_out() -> None:
    _slept, record = _recorder()
    calls = 0

    def send() -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    response = request_with_retry(
        send, policy=RetryPolicy(max_attempts=3, base_delay=0.0), sleep=record, jitter=NO_JITTER
    )

    # Status mapping belongs to the adapter, so the exhausted response comes back
    # rather than being raised here.
    assert response.status_code == 503
    assert calls == 3, f"expected max_attempts attempts, got {calls}"


def test_retries_transport_errors_then_succeeds() -> None:
    _slept, record = _recorder()
    attempts = 0

    def send() -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("refused")
        return httpx.Response(200)

    response = request_with_retry(
        send, policy=RetryPolicy(base_delay=0.0), sleep=record, jitter=NO_JITTER
    )

    assert response.status_code == 200
    assert attempts == 2


def test_exhausted_transport_errors_raise_provider_error() -> None:
    _slept, record = _recorder()

    def send() -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    with pytest.raises(ProviderError) as excinfo:
        request_with_retry(
            send,
            policy=RetryPolicy(max_attempts=2, base_delay=0.0),
            sleep=record,
            jitter=NO_JITTER,
        )

    assert "2 attempts" in str(excinfo.value)
    assert "ConnectTimeout" in str(excinfo.value)


def test_default_jitter_never_shortens_the_delay() -> None:
    slept, record = _recorder()
    responses = [httpx.Response(503), httpx.Response(200)]

    request_with_retry(lambda: responses.pop(0), policy=RetryPolicy(base_delay=2.0), sleep=record)

    assert len(slept) == 1
    assert 2.0 <= slept[0] <= 2.5, f"jitter must only add, got {slept[0]}"
