"""Dynamic tool surface (plan Task C): set_active_tools and execute_tool.

Covers the two genuinely missing handles from Pi's tool surface. Name-based
override of built-in tools already existed in ``compose_tools`` and is not
duplicated here.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from baldric.agent import AgentTool, AgentToolResult
from baldric.protocol.messages import TextContent
from baldric.protocol.types import JSONValue
from baldric.runtime.platform.api import ExtensionAPI
from baldric.runtime.platform.builtin_registry import BuiltInExtension
from baldric.runtime.platform.runtime import ExtensionRuntime
from tests.runtime.extensions.test_extensions import _paths

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _tool(name: str) -> AgentTool:
    async def execute(
        tool_call_id: str,
        arguments: object,
        signal: object = None,
        on_update: object = None,
    ) -> AgentToolResult:
        del tool_call_id, arguments, signal, on_update
        return AgentToolResult(content=[TextContent(text=f"ran {name}")])

    return AgentTool(
        name=name,
        label=name,
        description=f"test tool {name}",
        parameters={},
        execute_fn=cast("object", execute),
    )


def _runtime(tmp_path: Path, setup) -> ExtensionRuntime:
    runtime = ExtensionRuntime(built_in_extensions=(BuiltInExtension(name="ext", setup=setup),))
    runtime.load(_paths(tmp_path), include_resource_dirs=False)
    return runtime


def _register_two(api: ExtensionAPI) -> None:
    api.register_tool(_tool("alpha"))
    api.register_tool(_tool("beta"))


async def test_set_active_tools_filters_and_is_reversible(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, _register_two)
    runtime.bind_live_tools(runtime.compose_tools([]), None)

    assert [tool.name for tool in runtime.compose_tools([])] == ["alpha", "beta"]

    runtime.set_active_tools(["alpha"])
    live = runtime._live_tools
    assert live is not None
    assert [tool.name for tool in live] == ["alpha"]

    runtime.set_active_tools(None)
    assert live is not None
    assert [tool.name for tool in live] == ["alpha", "beta"]


async def test_set_active_tools_diagnoses_unknown_names(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, _register_two)
    runtime.bind_live_tools(runtime.compose_tools([]), None)

    runtime.set_active_tools(["alpha", "missing"])

    unknown = [d for d in runtime.diagnostics if "missing" in d.message]
    assert len(unknown) == 1
    live = runtime._live_tools
    assert live is not None
    assert [tool.name for tool in live] == ["alpha"]


async def test_register_tool_respects_the_active_filter(tmp_path: Path) -> None:
    def setup(api: ExtensionAPI) -> None:
        api.register_tool(_tool("alpha"))

    runtime = _runtime(tmp_path, setup)
    runtime.bind_live_tools(runtime.compose_tools([]), None)
    runtime.set_active_tools([])  # nothing active

    # A later registration must not silently reappear while the filter excludes it.
    runtime.register_tool("ext", "ext", _tool("beta"))
    live = runtime._live_tools
    assert live is not None
    assert live == []

    runtime.set_active_tools(["beta"])
    assert live is not None
    assert [tool.name for tool in live] == ["beta"]


async def test_execute_tool_runs_through_the_tool_pipeline(tmp_path: Path) -> None:
    def setup(api: ExtensionAPI) -> None:
        api.register_tool(_tool("alpha"))

        from baldric.runtime.platform.api import ToolCallHookResult

        def block(event, ctx):
            return ToolCallHookResult(block=True, reason="not now")

        api.on("tool_call", block)

    runtime = _runtime(tmp_path, setup)
    runtime.bind_live_tools(runtime.compose_tools([]), None)

    result = await runtime.execute_tool("alpha", {})

    # The registered tool_call hook blocked it, proving the call used the same
    # pipeline as a model-issued tool call.
    assert "blocked" in result.text.lower()
    assert "not now" in result.text


async def test_execute_tool_rejects_unknown_and_disabled_tools(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, _register_two)
    runtime.bind_live_tools(runtime.compose_tools([]), None)
    runtime.set_active_tools(["alpha"])

    with pytest.raises(Exception, match="not active or not registered"):
        await runtime.execute_tool("beta", {})
    with pytest.raises(Exception, match="not active or not registered"):
        await runtime.execute_tool("nope", {})


async def test_execute_tool_returns_tool_result(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, _register_two)
    runtime.bind_live_tools(runtime.compose_tools([]), None)

    result = await runtime.execute_tool("beta", cast("dict[str, JSONValue]", {}))

    assert result.text == "ran beta"
