"""Pi-style final text renderer for print mode."""

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
#: Final-text mode prints only the completed assistant answer and its failure
#: reason, so every remaining session event is deliberately ignored. The
#: AssistantMessage payload is reached by unwrapping MessageEndEvent; message
#: classes are not session events and therefore are not listed here.
RENDERED_EVENT_TYPES: frozenset[type[object]] = frozenset(
    {
        AutoRetryEndEvent,
        MessageEndEvent,
    }
)
INTENTIONAL_NOOP: dict[type[object], str] = {
    AgentEndEvent: "translated to SessionAgentEndEvent before reaching print renderers",
    AgentSettledEvent: "no visible output in final-text mode",
    AgentStartEvent: "no visible output in final-text mode",
    AutoRetryStartEvent: "retry progress is not printed in final-text mode",
    CompactionEndEvent: "compaction progress is not printed in final-text mode",
    CompactionStartEvent: "compaction progress is not printed in final-text mode",
    MessageStartEvent: "no output until the message ends",
    MessageUpdateEvent: "streaming deltas are not printed in final-text mode",
    ModelSelectEvent: "TUI-only; print mode reports model changes as command text",
    QueueUpdateEvent: "TUI-only; print mode never queues mid-turn",
    RetryAttemptEvent: "translated to AutoRetryStartEvent before print renderers",
    SessionAgentEndEvent: "no per-type output; answers print on MessageEndEvent",
    SessionInfoChangedEvent: "TUI-only; print mode reports renames as command text",
    ThinkingLevelChangedEvent: "TUI-only; print mode reports thinking changes as command text",
    ToolExecutionEndEvent: "tool output is not printed in final-text mode",
    ToolExecutionStartEvent: "tool output is not printed in final-text mode",
    ToolExecutionUpdateEvent: "tool output is not printed in final-text mode",
    TurnEndEvent: "turn messages are printed through MessageEndEvent",
    TurnStartEvent: "no visible output in final-text mode",
}


class FinalTextRenderer:
    def __init__(self) -> None:
        self._last_assistant_text = ""
        self._failed = False
        self._error_messages: list[str] = []

    def render(self, event: CodingSessionEvent) -> None:
        if isinstance(event, AutoRetryEndEvent) and event.success:
            self._failed = False
            self._error_messages.clear()
            return
        if not isinstance(event, MessageEndEvent) or not isinstance(event.message, AssistantMessage):
            return
        if event.message.is_tool_result_recovery:
            return
        self._last_assistant_text = event.message.text
        if is_failed_stop_reason(event.message.stop_reason):
            self._failed = True
            if event.message.stop_reason == "length" and not event.message.error_message:
                self._error_messages.append(
                    "Response was truncated: the model reached its output token limit."
                )
            elif event.message.error_message:
                self._error_messages.append(event.message.error_message)

    def finish(self) -> bool:
        if self._failed:
            for message in self._error_messages:
                typer.echo(f"Error: {message}", err=True)
            return False
        if self._last_assistant_text:
            typer.echo(self._last_assistant_text)
        return True
