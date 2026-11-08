"""RunState reducer mapping, unit-level (pi processEvents, agent.ts:575-622)."""

from __future__ import annotations

from baldric_agent.events import (
    AgentEndEvent,
    MessageEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    TurnEndEvent,
)
from baldric_agent.run_state import RunState
from baldric_protocol.messages import AssistantMessage, UserMessage
from baldric_protocol.provider_events import TextDeltaEvent
from baldric_protocol.tools import AgentToolResult


def test_streaming_message_follows_the_message_lifecycle() -> None:
    state = RunState()
    partial = AssistantMessage(content="hi", model="fake")

    state.apply(MessageStartEvent(message=partial))
    assert state.streaming_message is partial

    state.apply(
        MessageUpdateEvent(
            message=partial,
            assistant_message_event=TextDeltaEvent(content_index=0, delta="hi", partial=partial),
        )
    )
    assert state.streaming_message is partial

    state.apply(MessageEndEvent(message=partial))
    assert state.streaming_message is None


def test_pending_tool_calls_track_start_and_end() -> None:
    state = RunState()

    state.apply(ToolExecutionStartEvent(tool_call_id="call-1", tool_name="read"))
    assert state.pending_tool_calls == frozenset({"call-1"})

    state.apply(ToolExecutionStartEvent(tool_call_id="call-2", tool_name="edit"))
    state.apply(
        ToolExecutionEndEvent(
            tool_call_id="call-1",
            tool_name="read",
            result=AgentToolResult(content=[]),
            is_error=False,
        )
    )
    assert state.pending_tool_calls == frozenset({"call-2"})

    state.finish()
    assert state.pending_tool_calls == frozenset()


def test_error_message_records_assistant_failures_only() -> None:
    state = RunState()
    failed = AssistantMessage(content=[], model="fake", stop_reason="error", error_message="upstream down")

    state.apply(TurnEndEvent(message=UserMessage(content="hello")))
    assert state.error_message is None

    state.apply(TurnEndEvent(message=failed))
    assert state.error_message == "upstream down"

    state.begin()
    assert state.error_message is None
    assert state.streaming_message is None


def test_agent_end_clears_the_streaming_message() -> None:
    state = RunState()
    partial = AssistantMessage(content="hi", model="fake")

    state.apply(MessageStartEvent(message=partial))
    state.apply(AgentEndEvent(messages=[]))
    assert state.streaming_message is None
