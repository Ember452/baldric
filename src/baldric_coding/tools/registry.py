"""Factory for the default coding-tool set."""

from __future__ import annotations

import asyncio  # noqa: F401 - tests monkeypatch this module's asyncio.to_thread
from pathlib import Path

from baldric_coding.tools.base import ImageSupportState, ReadOperations, ToolDefinition, ToolInputError
from baldric_coding.tools.bash import create_bash_tool, create_bash_tool_definition
from baldric_coding.tools.edit import create_edit_tool, create_edit_tool_definition
from baldric_coding.tools.read import create_read_tool, create_read_tool_definition
from baldric_coding.tools.write import create_write_tool, create_write_tool_definition
from baldric_protocol.tools import AgentTool

__all__ = [
    "ImageSupportState",
    "ReadOperations",
    "ToolDefinition",
    "ToolInputError",
    "create_bash_tool",
    "create_bash_tool_definition",
    "create_coding_tools",
    "create_edit_tool",
    "create_edit_tool_definition",
    "create_read_tool",
    "create_read_tool_definition",
    "create_write_tool",
    "create_write_tool_definition",
]


def create_coding_tools(
    *,
    cwd: str | Path | None = None,
    shell_command_prefix: str | None = None,
    shell: str = "auto",
    image_support: ImageSupportState | None = None,
) -> list[AgentTool]:
    """Create the default coding-tool set for a local project.

    The returned tools are ordered as `read`, `write`, `edit`, and `bash`.
    Relative paths used with those tools are resolved against `cwd`; when `cwd`
    is omitted, the process current working directory at factory-call time is
    used. The tools share per-path write/edit locks within this process so
    concurrent mutations of the same file do not interleave. When configured,
    `shell_command_prefix` is prepended to every bash tool command, and `shell`
    selects the shell (`auto` by default).
    """
    root = Path.cwd() if cwd is None else Path(cwd)
    return [
        create_read_tool(cwd=root, image_support=image_support),
        create_write_tool(cwd=root),
        create_edit_tool(cwd=root),
        create_bash_tool(cwd=root, shell_command_prefix=shell_command_prefix, shell=shell),
    ]
