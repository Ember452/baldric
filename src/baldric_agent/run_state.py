"""Run-state projection reduced from agent events (pi AgentState / processEvents)."""

from __future__ import annotations

from baldric_agent.events import (
    AgentEndEvent,
    AgentEvent,
    MessageEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    TurnEndEvent,
)
from baldric_protocol.messages import AgentMessage, AssistantMessage


class RunState:
    """Observability state of the current run, reduced from agent events.

    Mirrors pi's AgentState and processEvents (agent.ts:575-622): one reducer
    per harness, cleared per run, fed the same events the listeners see, so a
    frontend can poll instead of replaying the event stream.
    """

    def __init__(self) -> None:
        self._streaming_message: AgentMessage | None = None
        self._pending_tool_calls: set[str] = set()
        self._error_message: str | None = None

    @property
    def streaming_message(self) -> AgentMessage | None:
        """The message currently being streamed, if any."""
        return self._streaming_message

    @property
    def pending_tool_calls(self) -> frozenset[str]:
        """Tool calls that started and have not ended yet."""
        return frozenset(self._pending_tool_calls)

    @property
    def error_message(self) -> str | None:
        """The error text of the last failed assistant turn, if any."""
        return self._error_message

    def begin(self) -> None:
        """Clear per-run state the way pi does when a run starts (agent.ts:530-531)."""
        self._streaming_message = None
        self._error_message = None

    def finish(self) -> None:
        """Drop pending tool calls the way pi's finishRun does (agent.ts:563)."""
        self._pending_tool_calls.clear()

    def apply(self, event: AgentEvent) -> None:
        """Reduce one event into the observable state."""
        if isinstance(event, (MessageStartEvent, MessageUpdateEvent)):
            self._streaming_message = event.message
        elif isinstance(event, MessageEndEvent):
            self._streaming_message = None
        elif isinstance(event, ToolExecutionStartEvent):
            self._pending_tool_calls.add(event.tool_call_id)
        elif isinstance(event, ToolExecutionEndEvent):
            self._pending_tool_calls.discard(event.tool_call_id)
        elif isinstance(event, TurnEndEvent):
            if isinstance(event.message, AssistantMessage) and event.message.error_message:
                self._error_message = event.message.error_message
        elif isinstance(event, AgentEndEvent):
            self._streaming_message = None
