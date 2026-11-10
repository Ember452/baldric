"""Shared retry policy for provider adapters."""

from __future__ import annotations

import math
import ssl
from asyncio import sleep
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC
from email.utils import parsedate_to_datetime
from random import random
from time import time
from typing import Protocol

import httpx

from baldric.ai._provider_events import ProviderRetryEvent
from baldric.ai.provider import CancellationToken
from baldric.protocol.types import JSONValue

RETRY_POLL_SECONDS = 0.05
RETRY_BASE_DELAY_SECONDS = 0.25

# Statuses the OpenAI and Anthropic SDKs retry. 425 is kept from Baldric's own
# earlier policy: it is rare, but dropping it would silently stop retrying a
# case that used to work.
RETRYABLE_STATUS_CODES = frozenset({408, 409, 425, 429})

# A request that overflows the context window arrives as a 400 or 413; these
# markers are the part of the message that is stable across providers.
_CONTEXT_OVERFLOW_MARKERS = (
    "context length",
    "context_length_exceeded",
    "context window",
    "maximum context",
    "prompt is too long",
    "too many tokens",
    "input is too long",
    "request too large",
)

# Transport failures that are safe to retry before any content is emitted.
# httpcore's anyio backend only maps ssl.SSLError during the TLS handshake (to
# ConnectError), so post-handshake record errors such as
# SSLV3_ALERT_BAD_RECORD_MAC escape as raw ssl.SSLError.
RETRYABLE_TRANSPORT_ERRORS: tuple[type[Exception], ...] = (httpx.HTTPError, ssl.SSLError)


@dataclass(frozen=True, slots=True)
class RetryDecision:
    """What one failed HTTP attempt means: retry, fail, and under which code."""

    retryable: bool
    delay_seconds: float
    code: str
    note: str = ""


class RetryConfig(Protocol):
    """The provider retry settings every adapter config already carries."""

    @property
    def max_retries(self) -> int: ...

    @property
    def max_retry_delay_seconds(self) -> float: ...


def classify_response_failure(
    response: httpx.Response,
    body: str,
    *,
    attempt: int,
    config: RetryConfig,
) -> RetryDecision:
    """Classify one failed streaming response with the provider's retry config."""
    return classify_http_failure(
        status_code=response.status_code,
        headers=response.headers,
        body=body,
        attempt=attempt,
        max_retries=config.max_retries,
        max_delay_seconds=config.max_retry_delay_seconds,
    )


def retry_delay_seconds(
    attempt: int,
    *,
    max_delay_seconds: float,
    jitter: bool = False,
) -> float:
    """Return an exponential retry delay capped by provider config.

    ``jitter`` trims up to 25% so simultaneous clients do not retry in lockstep.
    It applies only to the fallback delay, never to a server-requested one.
    """
    if max_delay_seconds <= 0:
        return 0.0
    base_delay = min(RETRY_BASE_DELAY_SECONDS, max_delay_seconds)
    delay = min(max_delay_seconds, base_delay * (2**attempt))
    if jitter:
        delay *= 1.0 - random() * 0.25
    return float(delay)


def retry_after_delay_seconds(headers: Mapping[str, str] | None) -> float | None:
    """Return the delay a server asked for through ``Retry-After`` headers."""
    if not headers:
        return None
    lowered = {str(key).lower(): str(value) for key, value in headers.items()}
    milliseconds = _non_negative_float(lowered.get("retry-after-ms"))
    if milliseconds is not None:
        return milliseconds / 1000.0
    raw = lowered.get("retry-after")
    if raw is None:
        return None
    seconds = _non_negative_float(raw)
    if seconds is not None:
        return seconds
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return max(0.0, parsed.timestamp() - time())


def failure_code(status_code: int, body: str = "") -> str:
    """Classify one HTTP failure with a stable, provider-neutral code."""
    if status_code in {401, 403}:
        return "auth"
    if status_code == 408:
        return "timeout"
    if status_code == 409:
        return "conflict"
    if status_code == 425:
        return "too_early"
    if status_code == 429:
        return "rate_limit"
    if _looks_like_context_overflow(body):
        return "context_overflow"
    if status_code >= 500:
        return "server_error"
    return "invalid_request"


def classify_http_failure(
    *,
    status_code: int,
    headers: Mapping[str, str] | None = None,
    body: str = "",
    attempt: int,
    max_retries: int,
    max_delay_seconds: float,
) -> RetryDecision:
    """Decide whether one failed HTTP attempt is retried, and after how long.

    Server guidance wins over the local exponential delay: ``Retry-After`` is
    honoured exactly, and a delay beyond the configured limit fails the request
    immediately with a note instead of either hammering the endpoint or blocking
    far past the caller's budget.
    """
    code = failure_code(status_code, body)
    retry_after = retry_after_delay_seconds(headers)
    header_policy = _should_retry_header(headers)
    retryable = status_code in RETRYABLE_STATUS_CODES or status_code >= 500
    if header_policy is True:
        retryable = True
    elif header_policy is False:
        retryable = False
    if code == "context_overflow":
        retryable = False
    if not retryable or attempt >= max_retries:
        return RetryDecision(retryable=False, delay_seconds=0.0, code=code)
    if retry_after is not None:
        if retry_after > max_delay_seconds:
            return RetryDecision(
                retryable=False,
                delay_seconds=0.0,
                code="retry_after_too_long",
                note=(
                    f" Server asked to wait {retry_after:.0f}s before retrying; "
                    f"the configured limit is {max_delay_seconds:g}s."
                ),
            )
        return RetryDecision(retryable=True, delay_seconds=retry_after, code=code)
    return RetryDecision(
        retryable=True,
        delay_seconds=retry_delay_seconds(
            attempt,
            max_delay_seconds=max_delay_seconds,
            jitter=True,
        ),
        code=code,
    )


def _should_retry_header(headers: Mapping[str, str] | None) -> bool | None:
    """Return the server's explicit retry policy, when it sends one."""
    if not headers:
        return None
    for key, value in headers.items():
        if str(key).lower() != "x-should-retry":
            continue
        lowered = str(value).strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    return None


def _non_negative_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return value


def _looks_like_context_overflow(body: str) -> bool:
    normalized = body.lower()
    return any(marker in normalized for marker in _CONTEXT_OVERFLOW_MARKERS)


def provider_retry_event(
    *,
    attempt: int,
    max_retries: int,
    delay_seconds: float,
    reason: str,
    data: dict[str, JSONValue] | None = None,
) -> ProviderRetryEvent:
    """Build a provider-neutral retry progress event."""
    next_attempt = attempt + 2
    max_attempts = max_retries + 1
    delay_suffix = f" in {delay_seconds:g}s" if delay_seconds else ""
    return ProviderRetryEvent(
        attempt=next_attempt,
        max_attempts=max_attempts,
        delay_seconds=delay_seconds,
        message=(f"Retrying provider request {next_attempt}/{max_attempts} after {reason}{delay_suffix}."),
        data=data,
    )


async def wait_for_retry(
    delay_seconds: float,
    *,
    signal: CancellationToken | None,
) -> bool:
    """Sleep before a retry while allowing cancellation to interrupt backoff."""
    if delay_seconds <= 0:
        return signal is None or not signal.is_cancelled()

    remaining = delay_seconds
    while remaining > 0:
        if signal is not None and signal.is_cancelled():
            return False
        step = min(RETRY_POLL_SECONDS, remaining)
        await sleep(step)
        remaining -= step
    return signal is None or not signal.is_cancelled()
