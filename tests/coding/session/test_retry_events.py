"""Provider retry events become the coding session's auto_retry pair."""

from __future__ import annotations

import pytest

from baldric_agent import AgentEndEvent, AssistantMessage, MessageEndEvent, RetryAttemptEvent
from baldric_coding.events import AutoRetryEndEvent, AutoRetryStartEvent
from baldric_coding.session.retry_events import with_auto_retry_events


async def _consume(events: list[object]) -> list[object]:
    async def source():  # type: ignore[no-untyped-def]
        for event in events:
            yield event

    return [event async for event in with_auto_retry_events(source())]  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_retry_then_success_emits_a_start_and_a_successful_end() -> None:
    retry = RetryAttemptEvent(attempt=1, max_attempts=3, delay_ms=500, message="HTTP 429")
    end = MessageEndEvent(message=AssistantMessage(model="m", content="ok", stop_reason="stop"))

    events = await _consume([retry, end, AgentEndEvent(messages=[])])

    assert [type(event) for event in events] == [
        AutoRetryStartEvent,
        AutoRetryEndEvent,
        MessageEndEvent,
        AgentEndEvent,
    ]
    start = events[0]
    assert isinstance(start, AutoRetryStartEvent)
    assert (start.attempt, start.max_attempts, start.delay_ms, start.error_message) == (
        1,
        3,
        500,
        "HTTP 429",
    )
    finished = events[1]
    assert isinstance(finished, AutoRetryEndEvent)
    assert finished.success is True
    assert finished.attempt == 1


@pytest.mark.anyio
async def test_retry_that_fails_ends_unsuccessfully_with_the_error() -> None:
    retry = RetryAttemptEvent(attempt=2, max_attempts=2, delay_ms=10, message="HTTP 500")
    end = MessageEndEvent(
        message=AssistantMessage(model="m", content=[], stop_reason="error", error_message="boom")
    )

    events = await _consume([retry, end])

    finished = events[1]
    assert isinstance(finished, AutoRetryEndEvent)
    assert finished.success is False
    assert finished.attempt == 2
    assert finished.final_error == "boom"


@pytest.mark.anyio
async def test_repeated_retries_share_one_end_with_the_last_attempt() -> None:
    first = RetryAttemptEvent(attempt=1, max_attempts=3, delay_ms=5, message="HTTP 429")
    second = RetryAttemptEvent(attempt=2, max_attempts=3, delay_ms=10, message="HTTP 429")
    end = MessageEndEvent(message=AssistantMessage(model="m", content="ok", stop_reason="stop"))

    events = await _consume([first, second, end])

    starts = [event for event in events if isinstance(event, AutoRetryStartEvent)]
    ends = [event for event in events if isinstance(event, AutoRetryEndEvent)]
    assert [start.attempt for start in starts] == [1, 2]
    assert len(ends) == 1
    assert ends[0].success is True
    assert ends[0].attempt == 2


@pytest.mark.anyio
async def test_stream_that_ends_after_a_retry_without_a_message_closes_the_pair() -> None:
    retry = RetryAttemptEvent(attempt=1, max_attempts=3, delay_ms=5, message="HTTP 429")

    events = await _consume([retry])

    finished = events[-1]
    assert isinstance(finished, AutoRetryEndEvent)
    assert finished.success is False
    assert finished.final_error == "Provider retry did not complete"
