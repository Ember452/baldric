"""Compatibility shim: the tool contract now lives in ``baldric_protocol.tools``.

Kept during the protocol extraction so existing ``from baldric_agent.tools``
imports keep working. Remove once every importer points at the protocol package.
"""

from __future__ import annotations

from baldric_protocol.tools import (
    AgentTool,
    AgentToolResult,
    ToolArgumentPreparer,
    ToolCall,
    ToolCallRenderer,
    ToolCancellationToken,
    ToolExecutionMode,
    ToolExecutor,
    ToolResultRenderer,
    ToolUpdateCallback,
)

__all__ = [
    "AgentTool",
    "AgentToolResult",
    "ToolArgumentPreparer",
    "ToolCall",
    "ToolCallRenderer",
    "ToolCancellationToken",
    "ToolExecutionMode",
    "ToolResultRenderer",
    "ToolExecutor",
    "ToolUpdateCallback",
]
