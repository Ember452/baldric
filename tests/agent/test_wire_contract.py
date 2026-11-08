"""Wire-format snapshots for messages, provider-stream events, and loop events.

Three consumers depend on these shapes: the persisted JSONL transcript, the
JSON event stream (``--print``/JSON mode), and the RPC wire. A change here is a
protocol change, so it has to show up as a reviewed golden diff instead of as a
silent behavior change.

The snapshot is the production serialization output (aliases on, ``None``
omitted), one object per line, so a diff points at the branch that changed.
Update a snapshot only with ``UPDATE_EXPECTED=1`` after reading the diff.
"""

from __future__ import annotations

from typing import get_args

from pydantic import TypeAdapter

from baldric_agent import (
    AgentEndEvent,
    AgentEvent,
    AgentMessage,
    AgentStartEvent,
    AgentToolResult,
    AssistantMessage,
    BashExecutionMessage,
    BranchSummaryMessage,
    CompactionSummaryMessage,
    CustomMessage,
    ImageContent,
    MessageEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    RetryAttemptEvent,
    TextContent,
    ThinkingContent,
    ToolCall,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    ToolExecutionUpdateEvent,
    ToolResultMessage,
    TurnEndEvent,
    TurnStartEvent,
    Usage,
    UsageCost,
    UserMessage,
)
from baldric_protocol.messages import AssistantMessageDiagnostic, ResponseTiming, WireModel
from baldric_protocol.provider_events import (
    AssistantDoneEvent,
    AssistantErrorEvent,
    AssistantMessageEvent,
    AssistantRetryEvent,
    AssistantStartEvent,
    TextDeltaEvent,
    TextEndEvent,
    TextStartEvent,
    ThinkingDeltaEvent,
    ThinkingEndEvent,
    ThinkingStartEvent,
    ToolCallDeltaEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
)
from tests.helpers.golden import assert_matches_expected

_TIMESTAMP = 1_700_000_000_000


def _wire(payload: WireModel) -> str:
    """Serialize one model exactly as the JSON and RPC outputs do."""
    return payload.model_dump_json(by_alias=True, exclude_none=True) + "\n"


def _snapshot(objects: tuple[WireModel, ...]) -> str:
    """One serialized object per line, so a diff stays branch-local."""
    return "".join(_wire(payload) for payload in objects)


def _assistant_message() -> AssistantMessage:
    return AssistantMessage(
        content=[
            TextContent(text="reading the file", text_signature="text-sig"),
            ThinkingContent(thinking="plan", thinking_signature="thinking-sig"),
            ToolCall(id="call-1", name="read", arguments={"path": "README.md"}, thought_signature="thought"),
        ],
        api="openai-compatible",
        provider="golden-provider",
        model="golden-model",
        response_model="golden-model-2026-01-01",
        response_provider="golden-upstream",
        response_id="resp-1",
        diagnostics=[
            AssistantMessageDiagnostic(type="truncated_tool_arguments", timestamp=_TIMESTAMP),
        ],
        usage=Usage(
            input=10,
            output=5,
            cache_read=2,
            cache_write=1,
            reasoning=3,
            total_tokens=21,
            cost=UsageCost(input=0.1, output=0.2, cache_read=0.01, cache_write=0.02, total=0.33),
        ),
        timing=ResponseTiming(time_to_first_output_ms=120, total_duration_ms=900),
        stop_reason="toolUse",
        timestamp=_TIMESTAMP,
    )


def _tool_result_message() -> ToolResultMessage:
    return ToolResultMessage(
        tool_call_id="call-1",
        tool_name="read",
        content=[
            TextContent(text="file contents"),
            ImageContent(data="aW1hZ2U=", mime_type="image/png"),
        ],
        details={"bytes": 13, "truncated": False},
        added_tool_names=["extra-tool"],
        is_error=False,
        timestamp=_TIMESTAMP,
    )


def _agent_messages() -> tuple[AgentMessage, ...]:
    return (
        UserMessage(content="hello", timestamp=_TIMESTAMP),
        UserMessage(
            content=[TextContent(text="look at this"), ImageContent(data="aW1hZ2U=", mime_type="image/png")],
            timestamp=_TIMESTAMP,
        ),
        _assistant_message(),
        _tool_result_message(),
        BashExecutionMessage(
            command="ls",
            output="a.txt\nb.txt",
            exit_code=0,
            cancelled=False,
            truncated=False,
            full_output_path="/tmp/baldric/out.txt",
            timestamp=_TIMESTAMP,
            exclude_from_context=False,
        ),
        CustomMessage(
            custom_type="subagent-notification",
            content=[TextContent(text="<task-notification/>")],
            display=True,
            details={"run_id": "run-1"},
            timestamp=_TIMESTAMP,
        ),
        BranchSummaryMessage(summary="explored approach A", from_id="entry-1", timestamp=_TIMESTAMP),
        CompactionSummaryMessage(summary="earlier work", tokens_before=1234, timestamp=_TIMESTAMP),
    )


def _provider_events() -> tuple[AssistantMessageEvent, ...]:
    partial = AssistantMessage(
        content="hello",
        api="openai-compatible",
        provider="golden-provider",
        model="golden-model",
        timestamp=_TIMESTAMP,
    )
    tool_call = ToolCall(id="call-1", name="read", arguments={"path": "README.md"})
    with_tool_call = AssistantMessage(
        content=[tool_call],
        api="openai-compatible",
        provider="golden-provider",
        model="golden-model",
        timestamp=_TIMESTAMP,
    )
    done = AssistantMessage(
        content="done",
        api="openai-compatible",
        provider="golden-provider",
        model="golden-model",
        stop_reason="stop",
        timestamp=_TIMESTAMP,
    )
    failed = AssistantMessage(
        content=[],
        api="openai-compatible",
        provider="golden-provider",
        model="golden-model",
        stop_reason="error",
        error_message="upstream exploded",
        timestamp=_TIMESTAMP,
    )

    return (
        AssistantStartEvent(partial=partial),
        AssistantRetryEvent(attempt=1, max_attempts=3, delay_ms=500, message="HTTP 429"),
        TextStartEvent(content_index=0, partial=partial),
        TextDeltaEvent(content_index=0, delta="hello", partial=partial),
        TextEndEvent(content_index=0, content="hello", partial=partial),
        ThinkingStartEvent(content_index=0, partial=partial),
        ThinkingDeltaEvent(content_index=0, delta="plan", partial=partial),
        ThinkingEndEvent(content_index=0, content="plan", partial=partial),
        ToolCallStartEvent(content_index=0, partial=with_tool_call),
        ToolCallDeltaEvent(content_index=0, delta='{"path":', partial=with_tool_call),
        ToolCallEndEvent(content_index=0, tool_call=tool_call, partial=with_tool_call),
        AssistantDoneEvent(reason="stop", message=done),
        AssistantErrorEvent(reason="error", error=failed),
    )


def _agent_events() -> tuple[AgentEvent, ...]:
    assistant = _assistant_message()
    result = _tool_result_message()
    tool_result = AgentToolResult(content=[TextContent(text="partial output")], details={"lines": 1})

    return (
        AgentStartEvent(),
        AgentEndEvent(messages=[UserMessage(content="hello", timestamp=_TIMESTAMP), assistant]),
        TurnStartEvent(),
        TurnEndEvent(message=assistant, tool_results=[result]),
        MessageStartEvent(message=UserMessage(content="hello", timestamp=_TIMESTAMP)),
        RetryAttemptEvent(attempt=1, max_attempts=3, delay_ms=500, message="HTTP 429"),
        MessageUpdateEvent(
            message=assistant,
            assistant_message_event=TextDeltaEvent(
                content_index=0,
                delta="reading the file",
                partial=assistant,
            ),
        ),
        MessageEndEvent(message=assistant),
        ToolExecutionStartEvent(tool_call_id="call-1", tool_name="read", args={"path": "README.md"}),
        ToolExecutionUpdateEvent(
            tool_call_id="call-1",
            tool_name="read",
            args={"path": "README.md"},
            partial_result=tool_result,
        ),
        ToolExecutionEndEvent(
            tool_call_id="call-1",
            tool_name="read",
            result=tool_result,
            is_error=False,
            duration_ms=250,
        ),
    )


_AGENT_MESSAGE = TypeAdapter(AgentMessage)
_PROVIDER_EVENT = TypeAdapter(AssistantMessageEvent)
_AGENT_EVENT = TypeAdapter(AgentEvent)


def _union_members(alias: object) -> frozenset[type]:
    """Every branch declared by a ``type X = Annotated[Union[...], Field(...)]`` alias."""
    value = getattr(alias, "__value__", alias)
    annotated = get_args(value)
    return frozenset(get_args(annotated[0]))


def test_agent_message_snapshot_covers_every_branch() -> None:
    """A new message type must extend this snapshot, not slip past it."""
    assert {type(message) for message in _agent_messages()} == set(_union_members(AgentMessage))


def test_provider_event_snapshot_covers_every_branch() -> None:
    assert {type(event) for event in _provider_events()} == set(_union_members(AssistantMessageEvent))


def test_agent_event_snapshot_covers_every_branch() -> None:
    assert {type(event) for event in _agent_events()} == set(_union_members(AgentEvent))


def test_agent_message_union_wire_format_is_stable() -> None:
    assert_matches_expected("agent_message_union.jsonl", _snapshot(_agent_messages()))


def test_provider_event_wire_format_is_stable() -> None:
    assert_matches_expected("provider_events.jsonl", _snapshot(_provider_events()))


def test_agent_event_wire_format_is_stable() -> None:
    assert_matches_expected("agent_events.jsonl", _snapshot(_agent_events()))


def test_agent_messages_round_trip_through_wire_json() -> None:
    for message in _agent_messages():
        assert _AGENT_MESSAGE.validate_json(_wire(message)) == message


def test_provider_events_round_trip_through_wire_json() -> None:
    for event in _provider_events():
        assert _PROVIDER_EVENT.validate_json(_wire(event)) == event


def test_agent_events_round_trip_through_wire_json() -> None:
    for event in _agent_events():
        assert _AGENT_EVENT.validate_json(_wire(event)) == event
