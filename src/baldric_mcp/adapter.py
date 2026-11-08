"""MCP tool adaptation: ecosystem tool naming, schemas, result conversion.

The naming rule is a line-by-line port of pi's
``pi-main/packages/mcp/src/naming.ts`` so Baldric ranks and groups MCP tools
the same way as other MCP clients. The 20 KiB middle cut is ported from
``pi-main/packages/mcp/src/output-limit.ts``.
"""

from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from baldric_mcp.client import McpContentBlock, McpToolInfo, McpToolResultData
from baldric_protocol.messages import ImageContent, TextContent
from baldric_protocol.tools import AgentTool, AgentToolResult
from baldric_protocol.types import JSONValue

TOOL_NAME_MAX = 64
TEXT_LIMIT = 20 * 1024

OutputSaver = Callable[[str, str], str]
McpToolCaller = Callable[..., Awaitable[McpToolResultData]]

_SANITIZE = re.compile(r"[^A-Za-z0-9_]")


def create_mcp_tool_name(
    server: str, tool: str, is_taken: Callable[[str], bool] = lambda _name: False
) -> str:
    """`mcp__<server>__<tool>`, sanitized, hash-suffixed when too long or taken."""
    name = _SANITIZE.sub("_", f"mcp__{server}__{tool}")
    if len(name) <= TOOL_NAME_MAX and not is_taken(name):
        return name
    digest = hashlib.sha256(f"{server}\0{tool}".encode()).hexdigest()[:8]
    return f"{name[: TOOL_NAME_MAX - len(digest) - 1]}_{digest}"


def normalize_input_schema(schema: Mapping[str, JSONValue] | None) -> dict[str, JSONValue]:
    """Coerce a server-provided input schema to a minimal object schema."""
    if not isinstance(schema, dict) or not schema:
        return {"type": "object", "properties": {}}
    return dict(schema)


def convert_result(
    server: str, tool: str, data: McpToolResultData, *, output_saver: OutputSaver | None = None
) -> AgentToolResult:
    """Map a tool result onto model-facing content, truncating long text."""
    combined = "\n".join(block.text for block in data.blocks if block.text is not None)
    images = [block for block in data.blocks if block.text is None and block.image_data is not None]

    if len(combined.encode()) > TEXT_LIMIT:
        content: list[TextContent | ImageContent] = [
            TextContent(text=_truncate_middle(combined, output_saver))
        ]
        content.extend(_image_placeholders(images))
        return AgentToolResult(content=content, is_error=True if data.is_error else None)

    blocks: list[TextContent | ImageContent] = []
    if combined:
        blocks.append(TextContent(text=combined))
    elif data.is_error and not images:
        blocks.append(TextContent(text=f"MCP tool {server}/{tool} returned an error"))
    blocks.extend(_image_placeholders(images))
    return AgentToolResult(content=blocks, is_error=True if data.is_error else None)


def _image_placeholders(images: list[McpContentBlock]) -> list[TextContent]:
    """MVP: images become text placeholders; provider tool-result image
    serialization in the loop is unverified (spec's deliberate boundary)."""
    placeholders: list[TextContent] = []
    for block in images:
        size = len(base64.b64decode(block.image_data or ""))
        placeholders.append(TextContent(text=f"[image: {block.image_mime or 'unknown'}, {size} bytes]"))
    return placeholders


def _truncate_middle(text: str, output_saver: OutputSaver | None) -> str:
    """Keep start and end halves at the byte limit; pi's truncateMiddle."""
    encoded = text.encode()
    head_end = TEXT_LIMIT // 2
    while head_end > 0 and (encoded[head_end] & 0xC0) == 0x80:
        head_end -= 1
    tail_start = len(encoded) - (TEXT_LIMIT - TEXT_LIMIT // 2)
    while tail_start < len(encoded) and (encoded[tail_start] & 0xC0) == 0x80:
        tail_start += 1
    head = encoded[:head_end].decode()
    tail = encoded[tail_start:].decode()
    removed = len(encoded[head_end:tail_start].decode())

    where = ""
    if output_saver is not None:
        try:
            path = output_saver(text, ".txt")
            where = f"\n\n[Full output: {path} (read it with offset/limit)]"
        except Exception as exc:
            where = f"\n\n[Could not save the full output: {exc}]"

    tokens = (len(encoded) + 3) // 4
    lines = len(text.split("\n")) - (1 if text.endswith("\n") else 0)
    return (
        f"Warning: truncated output (original token count: {tokens})\n"
        f"Total output lines: {lines}\n\n"
        f"{head}…{removed} chars truncated…{tail}{where}"
    )


def mcp_tool_to_agent_tool(
    server: str,
    info: McpToolInfo,
    call: McpToolCaller,
    *,
    output_saver: OutputSaver | None = None,
) -> AgentTool:
    """Wrap one advertised MCP tool as an ordinary agent tool."""

    async def executor(
        tool_call_id: str,
        arguments: Mapping[str, JSONValue],
        signal: Any = None,
        on_update: Callable[[AgentToolResult], None] | None = None,
    ) -> AgentToolResult:
        # signal is accepted but unused: the per-call timeout lives in the
        # connection's deadline watchdog, not in the loop's token.
        def on_progress(text: str) -> None:
            if on_update is not None:
                on_update(AgentToolResult(content=[TextContent(text=text)]))

        data = await call(dict(arguments), on_progress=on_progress)
        return convert_result(server, info.name, data, output_saver=output_saver)

    description = info.description.strip() or info.title or f"MCP tool {info.name} from server {server}"
    return AgentTool(
        name=create_mcp_tool_name(server, info.name),
        label=f"{server}/{info.name}",
        description=description,
        parameters=normalize_input_schema(info.input_schema),
        execute_fn=executor,
    )


__all__ = [
    "McpToolCaller",
    "OutputSaver",
    "TEXT_LIMIT",
    "TOOL_NAME_MAX",
    "convert_result",
    "create_mcp_tool_name",
    "mcp_tool_to_agent_tool",
    "normalize_input_schema",
]
