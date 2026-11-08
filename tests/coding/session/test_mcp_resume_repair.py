"""Resume repair for dangling MCP tool calls (harness prelude mechanism)."""

from __future__ import annotations

import pytest

from baldric_agent import AgentHarness, AgentHarnessConfig, AssistantMessage, ToolCall, ToolResultMessage
from baldric_ai import FakeProvider
from tests.helpers.pi_event_helpers import assistant_done, assistant_start

pytestmark = pytest.mark.anyio


def anyio_backend() -> str:
    return "asyncio"


async def test_dangling_mcp_tool_call_gets_a_synthetic_result() -> None:
    """A resumed `mcp__…` call without a result reaches the provider repaired.

    Mechanism (Task 0 Step 5): `AgentHarness._run` calls
    `_append_interrupted_tool_results` before the loop, so every run —
    including the first prompt of a resumed session — hands the provider a
    synthesized error result for an unanswered call id instead of a rejected
    request. The loop would answer an unknown *live* name differently ("Tool
    … not found"); this pins only the pre-repair behavior.
    """
    assistant = AssistantMessage(content="ok")
    provider = FakeProvider([[assistant_start(), assistant_done(assistant)]])
    dangling = AssistantMessage(content=[ToolCall(id="call-1", name="mcp__gone__srv__tool", arguments={})])
    harness = AgentHarness(
        AgentHarnessConfig(provider=provider, model="fake", system="s"),
        messages=[dangling],
    )

    _ = [event async for event in harness.prompt("continue")]

    messages = provider.calls[0][2]
    repairs = [message for message in messages if isinstance(message, ToolResultMessage)]
    assert [(message.tool_call_id, message.tool_name) for message in repairs] == [
        ("call-1", "mcp__gone__srv__tool")
    ]
    assert repairs[0].content[0].text == "Tool call interrupted by user"
    assert repairs[0].is_error is True
