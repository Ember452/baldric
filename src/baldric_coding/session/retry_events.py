"""Translate agent-level provider retries into the coding session's auto-retry events."""

from __future__ import annotations

from collections.abc import AsyncIterator

from baldric_agent.events import AgentEvent, MessageEndEvent, RetryAttemptEvent
from baldric_agent.messages import AssistantMessage
from baldric_coding.events import AutoRetryEndEvent, AutoRetryStartEvent, CodingSessionEvent


async def with_auto_retry_events(
    events: AsyncIterator[AgentEvent],
) -> AsyncIterator[CodingSessionEvent]:
    """Pair provider retries with the auto_retry events frontends already render.

    A transient failure can retry more than once, so every retry notice starts a
    new attempt and a single end event closes the sequence when the retried call
    produces an assistant message or the stream ends without one.
    """
    pending: RetryAttemptEvent | None = None
    ended = False
    async for event in events:
        if isinstance(event, RetryAttemptEvent):
            pending = event
            ended = False
            yield AutoRetryStartEvent(
                attempt=event.attempt,
                max_attempts=event.max_attempts,
                delay_ms=event.delay_ms,
                error_message=event.message or "Provider request failed",
            )
            continue
        if (
            pending is not None
            and not ended
            and isinstance(event, MessageEndEvent)
            and isinstance(event.message, AssistantMessage)
        ):
            success = event.message.stop_reason not in {"error", "aborted"}
            yield AutoRetryEndEvent(
                success=success,
                attempt=pending.attempt,
                final_error=None if success else event.message.error_message,
            )
            ended = True
        yield event
    if pending is not None and not ended:
        yield AutoRetryEndEvent(
            success=False,
            attempt=pending.attempt,
            final_error="Provider retry did not complete",
        )
