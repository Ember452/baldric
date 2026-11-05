"""Write tool implementation."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path

from baldric_agent.messages import TextContent
from baldric_agent.tools import AgentTool, AgentToolResult, ToolCancellationToken
from baldric_agent.types import JSONValue
from baldric_coding.tools.base import ToolDefinition, _file_lock, _path_arg, _str_arg


def create_write_tool_definition(*, cwd: str | Path | None = None) -> ToolDefinition:
    """Create a definition for the `write` tool.

    The tool writes the supplied string `content` to `path`, resolving relative
    paths against `cwd`. Parent directories are created automatically and any
    existing file is overwritten. Writes use UTF-8 text encoding and are guarded
    by a per-path async lock so multiple writes/edits to the same resolved file
    are serialized within this process.

    The executor raises `ToolInputError` when `path` or `content` has the wrong
    type. Successful results include the resolved path and number of characters
    written in `data`.
    """
    root = Path.cwd() if cwd is None else Path(cwd)

    async def execute(
        arguments: Mapping[str, JSONValue],
        signal: ToolCancellationToken | None = None,
    ) -> AgentToolResult:
        del signal
        path = _path_arg(arguments, "path", cwd=root)
        content = _str_arg(arguments, "content")

        async with _file_lock(path):
            path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(path.write_text, content, encoding="utf-8")

        return AgentToolResult(
            content=[TextContent(text=f"Successfully wrote to {path}.")],
            details={"path": str(path), "characters": len(content)},
        )

    return ToolDefinition(
        name="write",
        description=(
            "Write content to a file. Creates the file if it doesn't exist, overwrites if it does. "
            "Automatically creates parent directories."
        ),
        prompt_snippet="Create or overwrite files",
        prompt_guidelines=("Use write only for new files or complete rewrites.",),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to write"},
                "content": {"type": "string", "description": "Content to write to the file"},
            },
            "required": ["path", "content"],
        },
        executor=execute,
    )


def create_write_tool(*, cwd: str | Path | None = None) -> AgentTool:
    """Create an `AgentTool` for creating or overwriting UTF-8 text files."""
    return create_write_tool_definition(cwd=cwd).to_agent_tool()
