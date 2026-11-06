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
            ProviderToolCallEvent(tool_call=call, index=0),
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
            ProviderToolCallEvent(tool_call=first, index=0),
            ProviderToolCallEvent(tool_call=second, index=1),
            _end([first, second]),
        ]
    )

    ends = [event for event in events if isinstance(event, ToolCallEndEvent)]
    assert [event.tool_call for event in ends] == [first, second]
    assert [event.content_index for event in ends] == sorted(event.content_index for event in ends)


@pytest.mark.anyio
async def test_out_of_order_completions_pair_by_index_not_arrival() -> None:
    """A completion arriving before a sibling's must still fill its own block.

    Regression for the FIFO pairing bug: when ``output_item.done`` arrives out of
    order, the end event must carry the tool whose start block it replaces, not
    whichever placeholder happens to be oldest.
    """
    first = ToolCall(id="call-0", name="read", arguments={"path": "a"})
    second = ToolCall(id="call-1", name="run", arguments={"cmd": "b"})
    events = await _canonicalize(
        [
            ProviderResponseStartEvent(model="m"),
            ProviderToolCallStartEvent(index=0),
            ProviderToolCallStartEvent(index=1),
            ProviderToolCallDeltaEvent(index=0, delta='{"path":"a"}'),
            ProviderToolCallDeltaEvent(index=1, delta='{"cmd":"b"}'),
            # Completion order reversed relative to start order.
            ProviderToolCallEvent(tool_call=second, index=1),
            ProviderToolCallEvent(tool_call=first, index=0),
            _end([first, second]),
        ]
    )

    starts = [event for event in events if isinstance(event, ToolCallStartEvent)]
    ends = [event for event in events if isinstance(event, ToolCallEndEvent)]
    start_index_by_content = {event.content_index: i for i, event in enumerate(starts)}
    # Block opened for tool 0 is the first start, tool 1 the second.
    assert starts[0].content_index < starts[1].content_index
    end_by_content = {event.content_index: event.tool_call.id for event in ends}
    assert end_by_content[starts[0].content_index] == "call-0"
    assert end_by_content[starts[1].content_index] == "call-1"
    assert start_index_by_content[starts[0].content_index] == 0


@pytest.mark.anyio
async def test_complete_call_without_index_does_not_steal_open_placeholder() -> None:
    """A delta-less completion must not displace another streamed tool's block.

    Regression: a provider (Codex) may deliver a whole function call at
    ``output_item.done`` with no argument deltas; it carries ``index=None`` and
    must be appended, never paired with an unrelated open placeholder.
    """
    streamed = ToolCall(id="call-A", name="read", arguments={"path": "a"})
    delta_less = ToolCall(id="call-B", name="run", arguments={"cmd": "b"})
    events = await _canonicalize(
        [
            ProviderResponseStartEvent(model="m"),
            ProviderToolCallStartEvent(index=0),
            ProviderToolCallDeltaEvent(index=0, delta='{"path":"a"}'),
            ProviderToolCallEvent(tool_call=delta_less, index=None),
            ProviderToolCallEvent(tool_call=streamed, index=0),
            _end([streamed, delta_less]),
        ]
    )

    starts = [event for event in events if isinstance(event, ToolCallStartEvent)]
    ends = [event for event in events if isinstance(event, ToolCallEndEvent)]
    assert len(starts) == len(ends) == 2
    end_by_content = {event.content_index: event.tool_call.id for event in ends}
    # The streamed tool closes its announced block; the delta-less one gets its own.
    assert end_by_content[starts[0].content_index] == "call-A"
    assert set(end_by_content.values()) == {"call-A", "call-B"}
    assert len({event.content_index for event in ends}) == 2
