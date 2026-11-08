"""Real-process stdio integration: supervisor boots a FastMCP fixture server."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from baldric_mcp.client import McpContentBlock
from baldric_mcp.config import McpServerConfig
from baldric_mcp.supervisor import McpSupervisor

pytestmark = pytest.mark.anyio

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "helpers" / "mcp_stdio_fixture.py"


def anyio_backend() -> str:
    return "asyncio"


async def test_supervisor_runs_a_real_stdio_server() -> None:
    config = McpServerConfig(
        name="fixture",
        server_type="stdio",
        command=sys.executable,
        args=(str(FIXTURE_PATH),),
        timeout=30.0,
    )
    supervisor = McpSupervisor([config], environment=dict(os.environ))

    await supervisor.start()

    statuses = supervisor.statuses()
    assert [status.state for status in statuses] == ["connected"]
    assert [tool.name for tool in supervisor.tool_names("fixture")] == ["echo"]

    result = await supervisor.call_tool("fixture", "echo", {"text": "hi"})

    assert result.is_error is not True
    assert isinstance(result.blocks[0], McpContentBlock) and result.blocks[0].text == "hi"

    await supervisor.shutdown()

    assert [status.state for status in supervisor.statuses()] == ["closed"]
