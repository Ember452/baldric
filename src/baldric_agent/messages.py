"""Compatibility shim: the message models now live in ``baldric_protocol.messages``.

Kept during the protocol extraction so existing ``from baldric_agent.messages``
imports keep working. Remove once every importer points at the protocol package.
"""

from __future__ import annotations

from baldric_protocol.messages import (
    AgentMessage,
    AssistantMessage,
    AssistantMessageDiagnostic,
    BashExecutionMessage,
    BranchSummaryMessage,
    CompactionSummaryMessage,
    CustomMessage,
    ImageContent,
    ResponseTiming,
    TextContent,
    ThinkingContent,
    ToolCall,
    ToolResultMessage,
    Usage,
    UsageCost,
    UserMessage,
    WireModel,
    assistant_content,
    bash_execution_text,
    content_text,
    message_text,
    message_to_user,
    sum_usage,
)

__all__ = [
    "AgentMessage",
    "AssistantMessage",
    "AssistantMessageDiagnostic",
    "BashExecutionMessage",
    "BranchSummaryMessage",
    "CompactionSummaryMessage",
    "CustomMessage",
    "ImageContent",
    "ResponseTiming",
    "TextContent",
    "ThinkingContent",
    "ToolCall",
    "ToolResultMessage",
    "Usage",
    "UsageCost",
    "UserMessage",
    "WireModel",
    "assistant_content",
    "bash_execution_text",
    "content_text",
    "message_text",
    "message_to_user",
    "sum_usage",
]
