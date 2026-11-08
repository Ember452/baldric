"""Live tool registration: the bound list stays in step with the registry."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from baldric_coding import BaldricResourcePaths
from baldric_coding.extensions import ExtensionAPI, ExtensionRuntime
from baldric_coding.extensions.builtin_registry import BuiltInExtension
from baldric_protocol.tools import AgentTool, AgentToolResult
from tests.coding.extensions.test_extensions import RecordingSession

pytestmark = pytest.mark.anyio


def anyio_backend() -> str:
    return "asyncio"


def _paths(tmp_path: Path) -> BaldricResourcePaths:
    return BaldricResourcePaths(
        root=tmp_path / "home-baldric",
        cwd=tmp_path / "project",
        agents_root=tmp_path / "home-agents",
    )


def _capture(apis: list[ExtensionAPI], name: str) -> BuiltInExtension:
    def setup(baldric: ExtensionAPI) -> None:
        apis.append(baldric)

    return BuiltInExtension(name=name, setup=setup)


def _tool(name: str) -> AgentTool:
    async def execute(
        tool_call_id: str, arguments: Any, signal: Any = None, on_update: Any = None
    ) -> AgentToolResult:
        return AgentToolResult(content="ok")

    return AgentTool(
        name=name,
        label=name,
        description="test tool",
        parameters={"type": "object", "properties": {}},
        execute_fn=execute,
    )


def _runtime(tmp_path: Path, apis: list[ExtensionAPI]) -> ExtensionRuntime:
    runtime = ExtensionRuntime(built_in_extensions=[_capture(apis, "cap-a"), _capture(apis, "cap-b")])
    runtime.load(_paths(tmp_path))
    return runtime


async def test_register_appends_a_hook_wrapped_tool_to_the_bound_list(tmp_path: Path) -> None:
    apis: list[ExtensionAPI] = []
    runtime = _runtime(tmp_path, apis)
    live: list[AgentTool] = []
    runtime.bind_live_tools(live, None)
    runtime.bind(RecordingSession(tmp_path))
    raw = _tool("mcp-one")

    apis[0].register_tool(raw)

    assert len(live) == 1
    assert live[0].name == "mcp-one"
    # Live registrations carry the same hook wrapper compose_tools produces;
    # appending the raw tool would bypass tool_call/tool_result hooks.
    assert live[0] is not raw


async def test_live_registration_runs_the_tool_call_hooks(tmp_path: Path) -> None:
    from baldric_coding.extensions.api import ToolCallHookResult

    apis: list[ExtensionAPI] = []
    runtime = _runtime(tmp_path, apis)
    live: list[AgentTool] = []
    runtime.bind_live_tools(live, None)
    runtime.bind(RecordingSession(tmp_path))
    apis[0].on("tool_call", lambda event, context: ToolCallHookResult(block=True, reason="nope"))
    apis[0].register_tool(_tool("mcp-one"))

    result = await live[0].execute("call-1", {}, None, None)

    assert result.content[0].text == "Tool call blocked: nope"


async def test_unregister_removes_the_tool_from_the_bound_list(tmp_path: Path) -> None:
    apis: list[ExtensionAPI] = []
    runtime = _runtime(tmp_path, apis)
    live: list[AgentTool] = []
    runtime.bind_live_tools(live, None)
    runtime.bind(RecordingSession(tmp_path))
    apis[0].register_tool(_tool("mcp-one"))

    apis[0].unregister_tool("mcp-one")

    assert live == []


async def test_unregister_from_another_extension_is_a_silent_no_op(tmp_path: Path) -> None:
    apis: list[ExtensionAPI] = []
    runtime = _runtime(tmp_path, apis)
    live: list[AgentTool] = []
    runtime.bind_live_tools(live, None)
    runtime.bind(RecordingSession(tmp_path))
    apis[0].register_tool(_tool("mcp-one"))

    apis[1].unregister_tool("mcp-one")

    assert [tool.name for tool in live] == ["mcp-one"]


async def test_register_outside_allowed_names_is_ignored_with_a_diagnostic(tmp_path: Path) -> None:
    apis: list[ExtensionAPI] = []
    runtime = _runtime(tmp_path, apis)
    live: list[AgentTool] = []
    runtime.bind_live_tools(live, frozenset({"keep"}))
    runtime.bind(RecordingSession(tmp_path))

    apis[0].register_tool(_tool("keep"))
    apis[0].register_tool(_tool("outside"))

    assert [tool.name for tool in live] == ["keep"]
    assert any("outside" in diagnostic.message for diagnostic in runtime.diagnostics)


async def test_duplicate_registration_does_not_double_add(tmp_path: Path) -> None:
    apis: list[ExtensionAPI] = []
    runtime = _runtime(tmp_path, apis)
    live: list[AgentTool] = []
    runtime.bind_live_tools(live, None)
    runtime.bind(RecordingSession(tmp_path))

    apis[0].register_tool(_tool("dup"))
    apis[0].register_tool(_tool("dup"))

    assert [tool.name for tool in live] == ["dup"]
    assert any("duplicate" in diagnostic.message for diagnostic in runtime.diagnostics)


async def test_request_system_prompt_refresh_reaches_the_bound_session(tmp_path: Path) -> None:
    apis: list[ExtensionAPI] = []
    runtime = _runtime(tmp_path, apis)
    runtime.bind_live_tools([], None)
    session = RecordingSession(tmp_path)
    runtime.bind(session)

    apis[0].refresh_system_prompt()

    assert session.refresh_calls == 1
