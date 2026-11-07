"""A tool that asks for parallel execution must be rejected, not silently serialised.

Pi's loop runs a `parallel` batch concurrently. This harness runs tools one at a
time, so accepting the declaration would change the caller's semantics without
telling anyone.
"""

from __future__ import annotations

import pytest

from baldric_agent import AgentHarness, AgentHarnessConfig, AgentTool
from baldric_ai import FakeProvider


def _tool(name: str, mode: str) -> AgentTool:
    async def execute(
        tool_call_id: str,
        arguments: object,
        *,
        signal: object = None,
        on_update: object = None,
    ) -> None:
        del tool_call_id, arguments, signal, on_update
        raise AssertionError("not executed")

    return AgentTool(
        name=name,
        label=name,
        description="test tool",
        parameters={"type": "object", "properties": {}},
        execute_fn=execute,
        execution_mode=mode,  # type: ignore[arg-type]
    )


def _config(tools: list[AgentTool]) -> AgentHarnessConfig:
    return AgentHarnessConfig(provider=FakeProvider([]), model="fake", system="s", tools=tools)


def test_a_parallel_tool_is_rejected_at_registration() -> None:
    with pytest.raises(ValueError, match="parallel execution is not implemented"):
        AgentHarness(_config([_tool("a", "parallel")]))


def test_the_error_names_every_offending_tool() -> None:
    with pytest.raises(ValueError, match="b, c"):
        AgentHarness(_config([_tool("b", "parallel"), _tool("c", "parallel")]))


def test_sequential_tools_are_accepted() -> None:
    harness = AgentHarness(_config([_tool("a", "sequential")]))

    assert [tool.name for tool in harness.config.tools] == ["a"]
