"""Provider-neutral streaming events emitted by model adapters."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from baldric.protocol.messages import AssistantMessage
from baldric.protocol.tools import ToolCall
from baldric.protocol.types import JSONValue


class ProviderResponseStartEvent(BaseModel):
    """The provider has started a model response."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["response_start"] = "response_start"
    model: str
    response_provider: str | None = None


class ProviderRetryEvent(BaseModel):
    """The provider adapter is retrying a transient request failure."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["retry"] = "retry"
    attempt: int
    max_attempts: int
    delay_seconds: float
    message: str
    data: dict[str, JSONValue] | None = None


class ProviderTextDeltaEvent(BaseModel):
    """A streamed text fragment from the provider."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["text_delta"] = "text_delta"
    delta: str


class ProviderThinkingDeltaEvent(BaseModel):
    """A streamed thinking/reasoning fragment from the provider."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["thinking_delta"] = "thinking_delta"
    delta: str


class ProviderToolCallStartEvent(BaseModel):
    """A streamed tool call has begun; argument fragments follow."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["tool_call_start"] = "tool_call_start"
    index: int


class ProviderToolCallDeltaEvent(BaseModel):
    """A fragment of a streamed tool call's JSON arguments."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["tool_call_delta"] = "tool_call_delta"
    index: int
    delta: str


class ProviderToolCallEvent(BaseModel):
    """A complete tool call requested by the model.

    ``index`` ties this complete call back to the ``ProviderToolCallStartEvent``
    / ``ProviderToolCallDeltaEvent`` stream that carried its arguments, so the
    canonicalizer can replace the exact placeholder block instead of guessing by
    arrival order. It is ``None`` for providers that deliver the whole call at
    once (Responses, Google) and never emitted a start event.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["tool_call"] = "tool_call"
    tool_call: ToolCall
    index: int | None = None


class ProviderResponseEndEvent(BaseModel):
    """The provider has completed a model response."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["response_end"] = "response_end"
    message: AssistantMessage
    finish_reason: str | None = None


class ProviderErrorEvent(BaseModel):
    """A provider-level error that can be surfaced by the agent layer."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["error"] = "error"
    message: str
    data: dict[str, JSONValue] | None = None
    response_provider: str | None = None


type ProviderEvent = (
    ProviderResponseStartEvent
    | ProviderRetryEvent
    | ProviderTextDeltaEvent
    | ProviderThinkingDeltaEvent
    | ProviderToolCallStartEvent
    | ProviderToolCallDeltaEvent
    | ProviderToolCallEvent
    | ProviderResponseEndEvent
    | ProviderErrorEvent
)
