"""Baldric protocol contract: provider-neutral messages, tools, events, and the
persisted session wire shape.

This package is the lowest layer. It has no dependency on the agent runtime,
provider adapters, or the coding app, and no I/O or platform dependency. Its
only third-party dependency is pydantic.
"""

from __future__ import annotations

from baldric.protocol.messages import (
    AgentMessage,
    AssistantContent,
    AssistantDiagnosticError,
    AssistantMessage,
    AssistantMessageDiagnostic,
    BashExecutionMessage,
    BranchSummaryMessage,
    CompactionSummaryMessage,
    CustomMessage,
    ImageContent,
    ResponseTiming,
    StopReason,
    TextContent,
    ThinkingContent,
    ToolCall,
    ToolResultContent,
    ToolResultMessage,
    Usage,
    UsageCost,
    UserContent,
    UserMessage,
    WireModel,
    assistant_content,
    bash_execution_text,
    content_text,
    current_timestamp_ms,
    message_text,
    message_to_user,
    sum_usage,
)
from baldric.protocol.provider import CancellationToken, ModelProvider
from baldric.protocol.provider_events import (
    AssistantDoneEvent,
    AssistantErrorEvent,
    AssistantMessageEvent,
    AssistantRetryEvent,
    AssistantStartEvent,
    DoneReason,
    ErrorReason,
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
from baldric.protocol.tools import (
    AgentTool,
    AgentToolResult,
    ToolArgumentPreparer,
    ToolCallRenderer,
    ToolCancellationToken,
    ToolExecutionMode,
    ToolExecutor,
    ToolResultRenderer,
    ToolUpdateCallback,
)
from baldric.protocol.types import JSONObject, JSONPrimitive, JSONValue

PROTOCOL_VERSION = 1
"""Version of the wire contract defined by this package.

Third parties (provider adapters, frontends, session tooling) may depend on these
shapes directly, so the contract is explicitly versioned. The persisted session
wire shape additionally carries ``schema_version`` per entry (see
``baldric.protocol.session.entries``); ``PROTOCOL_VERSION`` is the umbrella for
the whole contract (messages, tools, provider events, session wire).

Compatibility policy: additive, non-breaking changes do not bump this number; an
incompatible wire change bumps it and is announced in the changelog. The golden
snapshots in ``tests/agent/test_wire_contract.py`` and
``tests/agent/test_session_entry_contract.py`` lock the exact bytes, so any
change to the wire shape fails CI until the diff is reviewed and the snapshots
are updated deliberately.
"""

__all__ = [
    "PROTOCOL_VERSION",
    "AgentMessage",
    "AssistantContent",
    "AssistantDiagnosticError",
    "AssistantMessage",
    "AssistantMessageDiagnostic",
    "BashExecutionMessage",
    "BranchSummaryMessage",
    "CompactionSummaryMessage",
    "CustomMessage",
    "ImageContent",
    "ResponseTiming",
    "StopReason",
    "TextContent",
    "ThinkingContent",
    "ToolCall",
    "ToolResultContent",
    "ToolResultMessage",
    "Usage",
    "UsageCost",
    "UserContent",
    "UserMessage",
    "WireModel",
    "assistant_content",
    "bash_execution_text",
    "content_text",
    "current_timestamp_ms",
    "message_text",
    "message_to_user",
    "sum_usage",
    "CancellationToken",
    "ModelProvider",
    "AssistantDoneEvent",
    "AssistantErrorEvent",
    "AssistantMessageEvent",
    "AssistantRetryEvent",
    "AssistantStartEvent",
    "DoneReason",
    "ErrorReason",
    "TextDeltaEvent",
    "TextEndEvent",
    "TextStartEvent",
    "ThinkingDeltaEvent",
    "ThinkingEndEvent",
    "ThinkingStartEvent",
    "ToolCallDeltaEvent",
    "ToolCallEndEvent",
    "ToolCallStartEvent",
    "AgentTool",
    "AgentToolResult",
    "ToolArgumentPreparer",
    "ToolCallRenderer",
    "ToolCancellationToken",
    "ToolExecutionMode",
    "ToolExecutor",
    "ToolResultRenderer",
    "ToolUpdateCallback",
    "JSONObject",
    "JSONPrimitive",
    "JSONValue",
]
