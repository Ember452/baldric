"""Human-readable Pi-compatible streaming transcript renderer."""

from pathlib import Path

import typer
from rich.console import Console
from rich.text import Text

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
from baldric.ai.events import TextDeltaEvent
from baldric.protocol.messages import AssistantMessage, CustomMessage, ToolCall
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
from baldric.runtime.platform.api import CustomMessageMarkup
from baldric.runtime.rendering.base import is_failed_stop_reason
from baldric.runtime.rendering.tool_calls import format_tool_call_block

#: Event coverage declarations consumed by tests/guards/test_print_event_dispatch.py.
#: The transcript renders streamed assistant text and tool lifecycle only; the
#: CustomMessage/AssistantMessage payloads are reached by unwrapping
#: MessageEndEvent, and message classes are not session events, so they are not
#: listed here.
RENDERED_EVENT_TYPES: frozenset[type[object]] = frozenset(
    {
        AgentEndEvent,
        AutoRetryEndEvent,
        AutoRetryStartEvent,
        MessageEndEvent,
        MessageUpdateEvent,
        SessionAgentEndEvent,
        ToolExecutionEndEvent,
        ToolExecutionStartEvent,
        ToolExecutionUpdateEvent,
    }
)
INTENTIONAL_NOOP: dict[type[object], str] = {
    AgentSettledEvent: "no visible output in transcript mode",
    AgentStartEvent: "no visible output in transcript mode",
    CompactionEndEvent: "compaction progress is not shown in transcript mode",
    CompactionStartEvent: "compaction progress is not shown in transcript mode",
    MessageStartEvent: "no output until deltas or the message end",
    ModelSelectEvent: "TUI-only; print mode reports model changes as command text",
    QueueUpdateEvent: "TUI-only; print mode never queues mid-turn",
    RetryAttemptEvent: "translated to AutoRetryStartEvent before print renderers",
    SessionInfoChangedEvent: "TUI-only; print mode reports renames as command text",
    ThinkingLevelChangedEvent: "TUI-only; print mode reports thinking changes as command text",
    TurnEndEvent: "turn messages print through MessageEndEvent",
    TurnStartEvent: "no visible output in transcript mode",
}


class TranscriptRenderer:
    def __init__(
        self,
        *,
        custom_message_renderer: CustomMessageMarkup | None = None,
        cwd: Path | None = None,
        **_: object,
    ) -> None:
        self._assistant_started = False
        self._assistant_ended = False
        self._failed = False
        self._cwd = cwd
        self._console = Console(stderr=True, highlight=False)
        self._custom_message_renderer = custom_message_renderer

    def render(self, event: CodingSessionEvent) -> None:
        if isinstance(event, MessageUpdateEvent):
            nested = event.assistant_message_event
            if isinstance(nested, TextDeltaEvent):
                self._assistant_started = True
                typer.echo(nested.delta, nl=False)
            return
        if isinstance(event, ToolExecutionStartEvent):
            self._newline()
            call = ToolCall(id=event.tool_call_id, name=event.tool_name, arguments=event.args)
            self._console.print(
                Text(format_tool_call_block(call, compact=False, cwd=self._cwd), style="cyan")
            )
            return
        if isinstance(event, ToolExecutionUpdateEvent):
            self._newline()
            if event.partial_result.text:
                self._console.print(Text(f"… {event.partial_result.text}", style="bright_black"))
            return
        if isinstance(event, AutoRetryStartEvent):
            self._newline()
            self._console.print(Text(f"… {event.error_message}", style="bright_black"))
            return
        if isinstance(event, AutoRetryEndEvent) and event.success:
            self._failed = False
            return
        if isinstance(event, ToolExecutionEndEvent):
            status = "✗" if event.is_error else "✓"
            style = "red" if event.is_error else "green"
            self._console.print(Text(f"{status} {event.tool_name}", style=style))
            if event.result.text:
                for line in event.result.text.splitlines():
                    self._console.print(Text(f"  {line}"))
            return
        if isinstance(event, MessageEndEvent) and isinstance(event.message, CustomMessage):
            if self._custom_message_renderer is None or not event.message.display:
                return
            rendered = self._custom_message_renderer(
                event.message.custom_type,
                event.message.text,
                event.message.details if isinstance(event.message.details, dict) else None,
                False,
            )
            if rendered:
                self._newline()
                self._console.print(rendered)
            return
        if isinstance(event, MessageEndEvent) and isinstance(event.message, AssistantMessage):
            if event.message.is_tool_result_recovery:
                self._newline()
                self._console.print(
                    Text(
                        "Image tool response rejected; retrying without images: "
                        f"{event.message.error_message}",
                        style="bright_black",
                    )
                )
            elif is_failed_stop_reason(event.message.stop_reason):
                self._failed = True
                self._newline()
                if event.message.stop_reason == "length":
                    message = "Response was truncated: the model reached its output token limit."
                else:
                    message = f"Error: {event.message.error_message or event.message.stop_reason}"
                self._console.print(Text(message, style="red"))
            self._newline(final=True)
            return
        if isinstance(event, SessionAgentEndEvent | AgentEndEvent):
            # A session-frontend run only ever yields SessionAgentEndEvent: the
            # session rewrites the agent-level AgentEndEvent before any renderer
            # sees it. Keeping the agent form covered keeps this renderer honest
            # for a harness-level caller, and without the session form an
            # aborted run left its open assistant block without a final newline.
            self._newline(final=True)

    def finish(self) -> bool:
        return not self._failed

    def _newline(self, *, final: bool = False) -> None:
        if self._assistant_started and not self._assistant_ended:
            typer.echo()
            self._assistant_ended = True
        elif final and not self._assistant_started:
            self._assistant_ended = True
