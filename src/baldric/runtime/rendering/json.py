"""Pi-compatible JSON event stream renderer."""

import typer

from baldric.agent.events import (
    AgentEndEvent,
    AgentStartEvent,
    MessageEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    RetryAttemptEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    ToolExecutionUpdateEvent,
    TurnEndEvent,
    TurnStartEvent,
)
from baldric.protocol.messages import AssistantMessage
from baldric.runtime.events import (
    AgentSettledEvent,
    AutoRetryEndEvent,
    AutoRetryStartEvent,
    CodingSessionEvent,
    CompactionEndEvent,
    CompactionStartEvent,
    ModelSelectEvent,
    QueueUpdateEvent,
    SessionAgentEndEvent,
    SessionInfoChangedEvent,
    ThinkingLevelChangedEvent,
)
from baldric.runtime.rendering.base import is_failed_stop_reason

#: Event coverage declarations consumed by tests/guards/test_print_event_dispatch.py.
#: JSON mode writes every event it receives verbatim, so an INTENTIONAL_NOOP entry
#: means "no per-type branch/state", not "dropped": for this renderer the
#: AssistantMessage payload is reached by unwrapping MessageEndEvent, and message
#: classes are not session events, so they are not listed.
RENDERED_EVENT_TYPES: frozenset[type[object]] = frozenset(
    {
        AutoRetryEndEvent,
        MessageEndEvent,
    }
)
INTENTIONAL_NOOP: dict[type[object], str] = {
    AgentEndEvent: "translated to SessionAgentEndEvent before reaching print renderers",
    AgentSettledEvent: "no failed-state tracking; streamed as JSONL",
    AgentStartEvent: "no failed-state tracking; streamed as JSONL",
    AutoRetryStartEvent: "no failed-state tracking; streamed as JSONL",
    CompactionEndEvent: "no failed-state tracking; streamed as JSONL",
    CompactionStartEvent: "no failed-state tracking; streamed as JSONL",
    MessageStartEvent: "no failed-state tracking; streamed as JSONL",
    MessageUpdateEvent: "no failed-state tracking; streamed as JSONL",
    ModelSelectEvent: "TUI-only; print mode reports model changes as command text",
    QueueUpdateEvent: "TUI-only; print mode never queues mid-turn",
    RetryAttemptEvent: "translated to AutoRetryStartEvent before print renderers",
    SessionAgentEndEvent: "no failed-state tracking; streamed as JSONL",
    SessionInfoChangedEvent: "TUI-only; print mode reports renames as command text",
    ThinkingLevelChangedEvent: "TUI-only; print mode reports thinking changes as command text",
    ToolExecutionEndEvent: "no failed-state tracking; streamed as JSONL",
    ToolExecutionStartEvent: "no failed-state tracking; streamed as JSONL",
    ToolExecutionUpdateEvent: "no failed-state tracking; streamed as JSONL",
    TurnEndEvent: "no failed-state tracking; streamed as JSONL",
    TurnStartEvent: "no failed-state tracking; streamed as JSONL",
}


class JsonEventRenderer:
    def __init__(self) -> None:
        self._failed = False

    def render(self, event: CodingSessionEvent) -> None:
        if isinstance(event, AutoRetryEndEvent) and event.success:
            self._failed = False
        if (
            isinstance(event, MessageEndEvent)
            and isinstance(event.message, AssistantMessage)
            and is_failed_stop_reason(event.message.stop_reason)
            and not event.message.is_tool_result_recovery
        ):
            self._failed = True
        typer.echo(event.model_dump_json(by_alias=True, exclude_none=True))

    def finish(self) -> bool:
        return not self._failed
