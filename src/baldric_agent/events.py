"""Pi-compatible events emitted by Baldric's portable agent layer."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from baldric_protocol.messages import AgentMessage, ToolResultMessage, WireModel
from baldric_protocol.provider_events import AssistantMessageEvent
from baldric_protocol.tools import AgentToolResult
from baldric_protocol.types import JSONValue


class AgentStartEvent(WireModel):
    type: Literal["agent_start"] = "agent_start"


class AgentEndEvent(WireModel):
    type: Literal["agent_end"] = "agent_end"
    messages: list[AgentMessage] = Field(default_factory=list)


class TurnStartEvent(WireModel):
    type: Literal["turn_start"] = "turn_start"


class TurnEndEvent(WireModel):
    type: Literal["turn_end"] = "turn_end"
    message: AgentMessage
    tool_results: list[ToolResultMessage] = Field(default_factory=list)


class MessageStartEvent(WireModel):
    type: Literal["message_start"] = "message_start"
    message: AgentMessage


class RetryAttemptEvent(WireModel):
    """A provider adapter is retrying a transient failure before output starts.

    Distinct from the internal `baldric_ai._provider_events.ProviderRetryEvent`,
    which stays inside the adapter; this is the frontend-visible event.
    """

    type: Literal["provider_retry"] = "provider_retry"
    attempt: int
    max_attempts: int
    delay_ms: int
    message: str = ""


class MessageUpdateEvent(WireModel):
    type: Literal["message_update"] = "message_update"
    message: AgentMessage
    assistant_message_event: AssistantMessageEvent = Field(serialization_alias="assistantMessageEvent")


class MessageEndEvent(WireModel):
    type: Literal["message_end"] = "message_end"
    message: AgentMessage


class ToolExecutionStartEvent(WireModel):
    type: Literal["tool_execution_start"] = "tool_execution_start"
    tool_call_id: str
    tool_name: str
    args: dict[str, JSONValue] = Field(default_factory=dict)


class ToolExecutionUpdateEvent(WireModel):
    type: Literal["tool_execution_update"] = "tool_execution_update"
    tool_call_id: str
    tool_name: str
    args: dict[str, JSONValue] = Field(default_factory=dict)
    partial_result: AgentToolResult


class ToolExecutionEndEvent(WireModel):
    type: Literal["tool_execution_end"] = "tool_execution_end"
    tool_call_id: str
    tool_name: str
    result: AgentToolResult
    is_error: bool
    # Milliseconds the tool's execute step took; absent when it never ran
    # (blocked, cancelled, unknown, or invalid arguments).
    duration_ms: int | None = None


type AgentEvent = Annotated[
    AgentStartEvent
    | AgentEndEvent
    | TurnStartEvent
    | TurnEndEvent
    | MessageStartEvent
    | RetryAttemptEvent
    | MessageUpdateEvent
    | MessageEndEvent
    | ToolExecutionStartEvent
    | ToolExecutionUpdateEvent
    | ToolExecutionEndEvent,
    Field(discriminator="type"),
]
