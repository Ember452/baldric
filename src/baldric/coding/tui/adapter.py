"""Translate Pi-compatible session events into Textual display state."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

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
from baldric.ai.events import TextDeltaEvent, ThinkingDeltaEvent
from baldric.coding.events import (
    AgentSettledEvent,
    AutoRetryEndEvent,
    AutoRetryStartEvent,
    CodingSessionEvent,
    CompactionEndEvent,
    CompactionStartEvent,
    QueueUpdateEvent,
    SessionAgentEndEvent,
)
from baldric.coding.events_dispatch import EventDispatcher as EventDispatcher
from baldric.coding.session.session import is_context_overflow_error
from baldric.coding.tui.state import (
    ChatItem,
    TuiState,
    _is_tool_only_message,
    has_visible_assistant_text,
)
from baldric.protocol.messages import AssistantMessage, CustomMessage, ToolCall, UserMessage

if TYPE_CHECKING:
    from baldric.coding.session.session import CodingSession

#: Events the TUI deliberately gives no transcript behavior. Neither TUI
#: dispatcher registers them, so they fall through to the app's ``on_unhandled``
#: chrome refresh, which *is* the intended behavior for them. Each entry needs a
#: reason: the coverage guard fails on an event type that is neither registered
#: nor listed here, so forgetting to wire a new event is caught in CI.
INTENTIONAL_NOOP: dict[type[object], str] = {
    TurnStartEvent: "a turn boundary renders no transcript row",
    TurnEndEvent: "a turn boundary renders no transcript row",
    RetryAttemptEvent: "the TUI renders the paired AutoRetryStartEvent instead",
}

_TERMINAL_ERROR_RETRY_HINT = "Run ended before completion. Send a message to retry."


class TuiEventAdapter:
    """Project coding-session events into ``TuiState`` through one dispatcher."""

    def __init__(self, state: TuiState, *, session: CodingSession | None = None) -> None:
        self.state = state
        self._session = session
        self._assistant_start_item_index: int | None = None
        self._pending_overflow_error: AssistantMessage | None = None
        self._compaction_status_item: ChatItem | None = None
        self._retry_status_item: ChatItem | None = None
        self._tool_batch_ids: dict[str, int] = {}
        self._tool_continuation_calls: set[str] = set()
        self._dispatcher = EventDispatcher()
        self._register_handlers()

    def apply(self, event: CodingSessionEvent) -> None:
        """Project one session event into display state; unregistered events are ignored."""
        self._dispatcher.dispatch(event)

    def dispatched_event_types(self) -> frozenset[type[object]]:
        """Return the event types this adapter has a projection handler for."""
        return self._dispatcher.registered_types()

    def _register_handlers(self) -> None:
        register = self._dispatcher.register
        register(AgentStartEvent, self._on_agent_start)
        register(AgentEndEvent, self._on_agent_end)
        register(SessionAgentEndEvent, self._on_session_agent_end)
        register(AgentSettledEvent, self._on_agent_settled)
        register(QueueUpdateEvent, self._on_queue_update)
        register(MessageStartEvent, self._on_message_start)
        register(MessageUpdateEvent, self._on_message_update)
        register(MessageEndEvent, self._on_message_end)
        register(ToolExecutionStartEvent, self._on_tool_execution_start)
        register(ToolExecutionUpdateEvent, self._on_tool_execution_update)
        register(ToolExecutionEndEvent, self._on_tool_execution_end)
        register(CompactionStartEvent, self._on_compaction_start)
        register(CompactionEndEvent, self._on_compaction_end)
        register(AutoRetryStartEvent, self._on_auto_retry_start)
        register(AutoRetryEndEvent, self._on_auto_retry_end)

    # -- agent lifecycle -----------------------------------------------------

    def _on_agent_start(self, event: AgentStartEvent) -> None:
        self.state.running = True
        self.state.error = None

    def _on_agent_end(self, event: AgentEndEvent) -> None:
        # A bare harness event is terminal for legacy/direct adapter callers.
        self._flush()
        self._discard_pending_tool_tracking()
        self.state.running = False
        self.state.compacting = False

    def _on_session_agent_end(self, event: SessionAgentEndEvent) -> None:
        # Session orchestration may still compact, retry, or drain queued work.
        self._flush()
        self._discard_pending_tool_tracking()

    def _on_agent_settled(self, event: AgentSettledEvent) -> None:
        # Terminal for one started run, including runs that raised before
        # AgentEnd, so pending per-call tracking is stale here too.
        self._flush()
        self._discard_pending_tool_tracking()
        if self._pending_overflow_error is not None:
            self.state.add_assistant_error(self._pending_overflow_error)
            self._pending_overflow_error = None
        self.state.running = False

    def _on_queue_update(self, event: QueueUpdateEvent) -> None:
        self.state.update_queue(steering=event.steering, follow_up=event.follow_up)

    # -- streaming messages --------------------------------------------------

    def _on_message_start(self, event: MessageStartEvent) -> None:
        if isinstance(event.message, AssistantMessage):
            self.state.assistant_buffer = event.message.text
            self._assistant_start_item_index = len(self.state.items)

    def _on_message_update(self, event: MessageUpdateEvent) -> None:
        nested = event.assistant_message_event
        if isinstance(nested, TextDeltaEvent):
            self.state.assistant_buffer += nested.delta
        elif isinstance(nested, ThinkingDeltaEvent):
            # Thinking that opens a message must start its own row: appending
            # it to the previous message's thinking row would escape this
            # message's `del items[start:]` window at MessageEnd and corrupt
            # that earlier row (issue #382-style mis-grouping, upstream #782).
            if len(self.state.items) == self._assistant_start_item_index:
                self.state.add_item("thinking", nested.delta)
            else:
                self.state.add_thinking_delta(nested.delta)

    def _on_message_end(self, event: MessageEndEvent) -> None:
        message = event.message
        if isinstance(message, UserMessage):
            self.state.add_user_message(message.text)
        elif isinstance(message, CustomMessage) and message.display:
            self.state.add_user_message(
                message.text,
                custom_type=message.custom_type,
                details=message.details if isinstance(message.details, dict) else None,
            )
        elif isinstance(message, AssistantMessage):
            self._project_assistant_end(message)

    def _project_assistant_end(self, message: AssistantMessage) -> None:
        # Replace provisional delta rows with the final canonical message so
        # persisted block boundaries and ordering win.
        start = self._assistant_start_item_index
        if start is not None:
            del self.state.items[start:]
        if message.stop_reason in {"error", "aborted"}:
            self._project_failed_assistant_end(message)
        else:
            self._pending_overflow_error = None
            self.state.add_assistant_message(message, include_tool_calls=False)
            self._track_message_tool_calls(message)
        if message.stop_reason == "error" and not message.is_tool_result_recovery:
            self._annotate_terminal_error(message)
        self.state.assistant_buffer = ""
        self._assistant_start_item_index = None

    def _project_failed_assistant_end(self, message: AssistantMessage) -> None:
        if message.is_tool_result_recovery:
            self._pending_overflow_error = None
            self.state.add_assistant_error(message)
        elif is_context_overflow_error(message):
            # Keep the provider failure provisional while session-level
            # overflow compaction and retry are still in progress.
            self._pending_overflow_error = message
        else:
            # Successful overflow compaction makes the retry failure the
            # only terminal error worth presenting.
            self._pending_overflow_error = None
            self.state.add_assistant_error(message)
            self.state.running = False

    def _track_message_tool_calls(self, message: AssistantMessage) -> None:
        previous_was_tool = False
        batch_id: int | None = None
        allows_tool_continuation = _is_tool_only_message(message)
        for block in message.content:
            if isinstance(block, ToolCall):
                if not previous_was_tool:
                    batch_id = self.state.new_tool_batch_id()
                if batch_id is not None:
                    self._tool_batch_ids[block.id] = batch_id
                if allows_tool_continuation:
                    self._tool_continuation_calls.add(block.id)
                previous_was_tool = True
            else:
                previous_was_tool = False

    def _annotate_terminal_error(self, message: AssistantMessage) -> None:
        """Mirror the session's diagnostic path and retry hint into the displayed error."""
        if self._session is None:
            return
        _attach_diagnostic_log_path_to_error(self.state, self._session)
        will_auto_retry = getattr(self._session, "will_auto_retry", None)
        if not (callable(will_auto_retry) and will_auto_retry(message)):
            _attach_retry_hint_to_error(self.state, message)

    # -- tools ---------------------------------------------------------------

    def _on_tool_execution_start(self, event: ToolExecutionStartEvent) -> None:
        self._flush()
        self.state.add_tool_call(
            ToolCall(id=event.tool_call_id, name=event.tool_name, arguments=event.args),
            batch_id=self._tool_batch_ids.pop(event.tool_call_id, None),
            allows_tool_continuation=(event.tool_call_id in self._tool_continuation_calls),
        )
        self._tool_continuation_calls.discard(event.tool_call_id)

    def _on_tool_execution_update(self, event: ToolExecutionUpdateEvent) -> None:
        self.state.record_tool_update(event.tool_call_id, event.partial_result.text)

    def _on_tool_execution_end(self, event: ToolExecutionEndEvent) -> None:
        self.state.record_tool_result(
            event.tool_call_id,
            event.tool_name,
            event.result,
            event.is_error,
        )

    # -- compaction ----------------------------------------------------------

    def _on_compaction_start(self, event: CompactionStartEvent) -> None:
        if event.reason == "overflow":
            self.state.add_item("status", "… Context limit reached; compacting and retrying")
        elif event.reason == "threshold":
            self.state.compacting = True
            self.state.add_item("status", "… Compacting context")
            self._compaction_status_item = self.state.items[-1]

    def _on_compaction_end(self, event: CompactionEndEvent) -> None:
        if event.reason == "overflow":
            if (event.aborted or event.error_message) and self._pending_overflow_error is not None:
                self.state.add_assistant_error(self._pending_overflow_error)
                self._pending_overflow_error = None
            if event.aborted or event.error_message:
                self._annotate_overflow_compaction_failure()
            return
        if event.reason == "threshold":
            self.state.compacting = False
            item = self._compaction_status_item
            self._compaction_status_item = None
            if item is not None:
                if event.aborted or event.error_message:
                    item.text = f"… Automatic compaction failed: {event.error_message or 'unknown error'}"
                elif item in self.state.items:
                    self.state.items.remove(item)

    def _annotate_overflow_compaction_failure(self) -> None:
        if self._session is not None:
            _attach_diagnostic_log_path_to_error(self.state, self._session)

    # -- automatic retry -----------------------------------------------------

    def _on_auto_retry_start(self, event: AutoRetryStartEvent) -> None:
        # A provider retries before any message lands, so every attempt replaces
        # the previous live notice instead of stacking one row per attempt.
        self._discard_retry_status()
        if self.state.items and self.state.items[-1].role == "error":
            self.state.items.pop()
        self.state.error = None
        self.state.add_item("status", f"… {event.error_message}")
        self._retry_status_item = self.state.items[-1]

    def _on_auto_retry_end(self, event: AutoRetryEndEvent) -> None:
        """Settle the live retry notice once the retried request finishes.

        The notice is transient: on success the following assistant message tells
        the story, and on failure the terminal error is rendered separately. A
        retry that ended without either still surfaces its final error here.
        """
        self._discard_retry_status()
        if event.success or self.state.error is not None or event.final_error is None:
            return
        self.state.error = event.final_error
        self.state.add_item("error", f"Error: {event.final_error}")

    def _discard_retry_status(self) -> None:
        item = self._retry_status_item
        self._retry_status_item = None
        if item is not None:
            self.state.items[:] = [existing for existing in self.state.items if existing is not item]

    # -- internals -----------------------------------------------------------

    def _discard_pending_tool_tracking(self) -> None:
        """Drop per-call bookkeeping for calls that never started executing.

        A turn that fails between its message end and a call's execution start
        would otherwise leave its batch id and continuation flag behind for the
        lifetime of the session. Tool calls always follow their own message end,
        so nothing pending at a turn end can still apply.
        """
        self._tool_batch_ids.clear()
        self._tool_continuation_calls.clear()

    def _flush(self) -> None:
        # A whitespace-only buffer would project a zero-height item that still
        # carries block margins, so it is dropped rather than rendered.
        if has_visible_assistant_text(self.state.assistant_buffer):
            self.state.add_item("assistant", self.state.assistant_buffer)
        self.state.assistant_buffer = ""


def _attach_retry_hint_to_error(state: TuiState, message: AssistantMessage) -> None:
    """Clarify that a terminal provider error ended the run and can be retried.

    Context-overflow errors are auto-compacted and retried by the session, so
    they are skipped to avoid asking the user to retry while Baldric already is.
    """
    if is_context_overflow_error(message):
        return
    if state.error is not None and _TERMINAL_ERROR_RETRY_HINT not in state.error:
        state.error = f"{state.error}\n{_TERMINAL_ERROR_RETRY_HINT}"
    for item in reversed(state.items):
        if item.role == "error":
            if _TERMINAL_ERROR_RETRY_HINT not in item.text:
                item.text = f"{item.text}\n{_TERMINAL_ERROR_RETRY_HINT}"
            return


def _attach_diagnostic_log_path_to_error(state: TuiState, session: CodingSession) -> None:
    log_path = getattr(session, "last_diagnostic_log_path", None)
    if not isinstance(log_path, Path) or state.error is None:
        return
    message = f"Error: {state.error}\nLog: {log_path}"
    state.error = message
    for item in reversed(state.items):
        if item.role == "error":
            item.text = message
            return
    state.add_item("error", message)
