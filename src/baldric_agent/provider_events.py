"""Compatibility shim: assistant stream events now live in
``baldric_protocol.provider_events``.

Kept during the protocol extraction so existing ``from baldric_agent.provider_events``
imports keep working. Remove once every importer points at the protocol package.
"""

from __future__ import annotations

from baldric_protocol.provider_events import (
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

__all__ = [
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
]
