"""canonicalize_provider_stream surfaces streamed tool-call argument deltas."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from baldric_agent import AssistantMessage, ToolCall, Usage
from baldric_ai._provider_events import (
    ProviderEvent,
    ProviderResponseEndEvent,
    ProviderResponseStartEvent,
    ProviderToolCallDeltaEvent,
    ProviderToolCallEvent,
    ProviderToolCallStartEvent,
)
from baldric_ai.events import ToolCallDeltaEvent, ToolCallEndEvent, ToolCallStartEvent
from baldric_ai.stream import canonicalize_provider_stream


async def _source(events: list[ProviderEvent]) -> AsyncIterator[ProviderEvent]:
    for event in events:
        yield event


def _end(tool_calls: list[ToolCall]) -> ProviderResponseEndEvent:
    return ProviderResponseEndEvent(
        message=AssistantMessage(content=list(tool_calls), usage=Usage()),
        finish_reason="tool_calls",
    )


async def _canonicalize(events: list[ProviderEvent]) -> list[object]:
    return [
        event
        async for event in canonicalize_provider_stream(_source(events), api="test", provider="p", model="m")
    ]


@pytest.mark.anyio
async def test_streamed_arguments_emit_start_deltas_and_end() -> None:
    call = ToolCall(id="call-0", name="read", arguments={"path": "a.txt"})
    events = await _canonicalize(
        [
            ProviderResponseStartEvent(model="m"),
            ProviderToolCallStartEvent(index=0),
            ProviderToolCallDeltaEvent(index=0, delta='{"path":'),
            ProviderToolCallDeltaEvent(index=0, delta='"a.txt"}'),
            ProviderToolCallEvent(tool_call=call),
            _end([call]),
        ]
    )

    assert [type(event).__name__ for event in events] == [
        "AssistantStartEvent",
        "ToolCallStartEvent",
        "ToolCallDeltaEvent",
        "ToolCallDeltaEvent",
        "ToolCallEndEvent",
        "AssistantDoneEvent",
    ]
    deltas = [event.delta for event in events if isinstance(event, ToolCallDeltaEvent)]
    assert "".join(deltas) == '{"path":"a.txt"}'
    starts = [event for event in events if isinstance(event, ToolCallStartEvent)]
    ends = [event for event in events if isinstance(event, ToolCallEndEvent)]
    assert len(starts) == len(ends) == 1
    assert starts[0].content_index == ends[0].content_index
    assert ends[0].tool_call == call


@pytest.mark.anyio
async def test_complete_tool_call_without_deltas_still_emits_start_and_end() -> None:
    call = ToolCall(id="call-0", name="read", arguments={"path": "a.txt"})
    events = await _canonicalize(
        [
            ProviderResponseStartEvent(model="m"),
            ProviderToolCallEvent(tool_call=call),
            _end([call]),
        ]
    )

    assert [type(event).__name__ for event in events] == [
        "AssistantStartEvent",
        "ToolCallStartEvent",
        "ToolCallEndEvent",
        "AssistantDoneEvent",
    ]


@pytest.mark.anyio
async def test_two_interleaved_calls_pair_end_events_in_order() -> None:
    first = ToolCall(id="call-0", name="read", arguments={"path": "a"})
    second = ToolCall(id="call-1", name="read", arguments={"path": "b"})
    events = await _canonicalize(
        [
            ProviderResponseStartEvent(model="m"),
            ProviderToolCallStartEvent(index=0),
            ProviderToolCallStartEvent(index=1),
            ProviderToolCallDeltaEvent(index=0, delta='{"path":"a"}'),
            ProviderToolCallDeltaEvent(index=1, delta='{"path":"b"}'),
            ProviderToolCallEvent(tool_call=first),
            ProviderToolCallEvent(tool_call=second),
            _end([first, second]),
        ]
    )

    ends = [event for event in events if isinstance(event, ToolCallEndEvent)]
    assert [event.tool_call for event in ends] == [first, second]
    assert [event.content_index for event in ends] == sorted(event.content_index for event in ends)
