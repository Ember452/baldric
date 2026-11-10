"""Write tool implementation."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path

from baldric.coding.tools.base import ToolDefinition, _file_lock, _path_arg, _str_arg
from baldric.coding.tools.edit import generate_unified_patch
from baldric.protocol.messages import TextContent
from baldric.protocol.tools import AgentTool, AgentToolResult, ToolCancellationToken
from baldric.protocol.types import JSONValue


def create_write_tool_definition(*, cwd: str | Path | None = None) -> ToolDefinition:
    """Create a definition for the `write` tool.

    The tool writes the supplied string `content` to `path`, resolving relative
    paths against `cwd`. Parent directories are created automatically and any
    existing file is overwritten. Writes use UTF-8 text encoding and are guarded
    by a per-path async lock so multiple writes/edits to the same resolved file
    are serialized within this process.

    The executor raises `ToolInputError` when `path` or `content` has the wrong
    type. Successful results include the resolved path, number of characters
    written, and a unified `patch` against the previous content in `data`
    (all-additions for a new file; omitted when the previous file was not
    decodable UTF-8 text).
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
            # Overwriting a decodable text file records a diff against its old
            # content; creating a file diffs against empty (all-additions).
            # An undecodable (e.g. binary) old file gets no patch — faking a
            # full-file addition would misrepresent what was replaced.
            old_content: str | None = ""
            if path.exists():
                try:
                    old_content = await asyncio.to_thread(path.read_text, encoding="utf-8-sig")
                except (OSError, UnicodeDecodeError):
                    old_content = None
            await asyncio.to_thread(path.write_text, content, encoding="utf-8")

        details: dict[str, JSONValue] = {"path": str(path), "characters": len(content)}
        if old_content is not None:
            details["patch"] = generate_unified_patch(str(path), old_content, content)
        return AgentToolResult(
            content=[TextContent(text=f"Successfully wrote to {path}.")],
            details=details,
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
                "content": {
                    "type": "string",
                    "description": "Content to write to the file",
                },
            },
            "required": ["path", "content"],
        },
        executor=execute,
    )


def create_write_tool(*, cwd: str | Path | None = None) -> AgentTool:
    """Create an `AgentTool` for creating or overwriting UTF-8 text files."""
    return create_write_tool_definition(cwd=cwd).to_agent_tool()
