"""Retry policy tests: server guidance, classification, and limits."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import pytest

from baldric.ai.retry import (
    classify_http_failure,
    failure_code,
    retry_after_delay_seconds,
    retry_delay_seconds,
)


def _classify(
    *,
    status_code: int,
    headers: dict[str, str] | None = None,
    body: str = "",
    attempt: int = 0,
    max_retries: int = 3,
    max_delay_seconds: float = 10.0,
):
    return classify_http_failure(
        status_code=status_code,
        headers=headers,
        body=body,
        attempt=attempt,
        max_retries=max_retries,
        max_delay_seconds=max_delay_seconds,
    )


def test_retry_after_seconds_is_honoured_exactly() -> None:
    decision = _classify(status_code=429, headers={"retry-after": "2.5"})

    assert decision.retryable is True
    assert decision.delay_seconds == 2.5
    assert decision.code == "rate_limit"


def test_retry_after_ms_takes_precedence_over_seconds() -> None:
    decision = _classify(
        status_code=429,
        headers={"retry-after-ms": "1500", "retry-after": "9"},
    )

    assert decision.delay_seconds == 1.5


def test_retry_after_http_date_is_honoured() -> None:
    retry_at = datetime.now(UTC) + timedelta(seconds=3)

    delay = retry_after_delay_seconds({"retry-after": format_datetime(retry_at, usegmt=True)})

    assert delay is not None
    assert 2.0 <= delay <= 4.0


def test_server_delay_above_the_limit_fails_fast() -> None:
    decision = _classify(
        status_code=429,
        headers={"retry-after": "60"},
        max_delay_seconds=1.0,
    )

    assert decision.retryable is False
    assert decision.delay_seconds == 0.0
    assert decision.code == "retry_after_too_long"
    assert "60s" in decision.note
    assert "1s" in decision.note


def test_exponential_fallback_stays_within_the_jitter_band() -> None:
    decision = _classify(status_code=503)

    assert decision.retryable is True
    assert decision.code == "server_error"
    assert 0.25 * 0.75 <= decision.delay_seconds <= 0.25


def test_failure_codes_are_stable_and_specific() -> None:
    assert failure_code(401) == "auth"
    assert failure_code(403) == "auth"
    assert failure_code(408) == "timeout"
    assert failure_code(409) == "conflict"
    assert failure_code(425) == "too_early"
    assert failure_code(429) == "rate_limit"
    assert failure_code(400) == "invalid_request"
    assert failure_code(500) == "server_error"
    assert failure_code(400, "maximum context length exceeded") == "context_overflow"
    assert failure_code(413, "too many tokens in request") == "context_overflow"


def test_a_context_overflow_is_never_retried() -> None:
    decision = _classify(status_code=400, body="This model's maximum context length is 8192 tokens")

    assert decision.retryable is False
    assert decision.code == "context_overflow"


def test_auth_failures_are_never_retried() -> None:
    assert _classify(status_code=401).retryable is False
    assert _classify(status_code=403).retryable is False


def test_the_retry_header_overrides_the_status_default() -> None:
    assert _classify(status_code=500, headers={"x-should-retry": "false"}).retryable is False
    assert _classify(status_code=400, headers={"x-should-retry": "true"}).retryable is True


def test_the_attempt_limit_stops_retrying() -> None:
    decision = _classify(status_code=503, attempt=3, max_retries=3)

    assert decision.retryable is False
    assert decision.code == "server_error"


def test_an_unparsable_retry_after_falls_back_to_the_exponential_delay() -> None:
    decision = _classify(status_code=429, headers={"retry-after": "soon"})

    assert decision.retryable is True
    assert decision.delay_seconds > 0
    assert retry_after_delay_seconds({"retry-after": "-5"}) is None


def test_a_config_with_no_delay_budget_still_rejects_a_server_delay() -> None:
    decision = _classify(status_code=429, headers={"retry-after": "1"}, max_delay_seconds=0)

    assert decision.retryable is False
    assert decision.code == "retry_after_too_long"


def test_jitter_only_shrinks_the_fallback_delay() -> None:
    delays = {retry_delay_seconds(0, max_delay_seconds=10, jitter=True) for _ in range(20)}

    assert all(0.1875 <= delay <= 0.25 for delay in delays)
    assert len(delays) > 1, "jitter must vary between calls"


@pytest.mark.parametrize("status_code", [408, 409, 425, 429, 500, 502, 503, 504])
def test_transient_statuses_stay_retryable(status_code: int) -> None:
    assert _classify(status_code=status_code).retryable is True
