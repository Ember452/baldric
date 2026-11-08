"""Tests for the bundled MCP extension: boot, trust gate, dynamic registration."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anyio
import pytest

from baldric_ai import FakeProvider
from baldric_coding import BaldricPaths, BaldricResourcePaths, CodingSession, CodingSessionConfig
from baldric_coding.extensions import ExtensionRuntime
from baldric_coding.extensions.builtin_registry import BuiltInExtension
from baldric_coding.session import JsonlSessionStorage
from baldric_mcp.client import McpContentBlock, McpToolInfo, McpToolResultData
from baldric_mcp.config import McpServerConfig
from baldric_mcp.supervisor import McpServerStatus
from tests.coding.extensions.test_extensions import RecordingSession, RecordingUiBridge

pytestmark = pytest.mark.anyio


def anyio_backend() -> str:
    return "asyncio"


USER_SERVER = {"command": "srv-cmd", "args": ["--x"]}
PROJECT_SERVER = {"command": "proj-cmd"}


class FakeSupervisor:
    """Scripted stand-in; the extension sees the real supervisor surface."""

    def __init__(self, configs: Any, environment: Any) -> None:
        self.configs = tuple(configs)
        self.environment = dict(environment)
        self.start_calls = 0
        self.shutdown_calls = 0
        self.wait_calls = 0
        self._servers: dict[str, dict[str, Any]] = {}
        self._on_change: Callable[[], None] | None = None

    def set_server(
        self,
        name: str,
        state: str,
        *,
        tools: tuple[McpToolInfo, ...] = (),
        instructions: str | None = None,
        error: str | None = None,
    ) -> None:
        self._servers[name] = {"state": state, "tools": tools, "instructions": instructions, "error": error}
        if self._on_change is not None:
            self._on_change()

    def statuses(self) -> tuple[McpServerStatus, ...]:
        return tuple(
            McpServerStatus(
                name=name,
                state=server["state"],
                tool_count=len(server["tools"]) if server["state"] == "connected" else 0,
                error=server["error"],
            )
            for name, server in self._servers.items()
        )

    def any_connecting(self) -> bool:
        return any(server["state"] == "connecting" for server in self._servers.values())

    def tool_names(self, server: str) -> tuple[McpToolInfo, ...]:
        return self._servers.get(server, {"tools": ()})["tools"]

    def instructions(self, server: str) -> str | None:
        return self._servers.get(server, {}).get("instructions")

    def on_change(self, callback: Callable[[], None]) -> None:
        self._on_change = callback

    async def start(self) -> None:
        self.start_calls += 1

    async def shutdown(self) -> None:
        self.shutdown_calls += 1

    async def wait_ready(self, timeout: float = 10.0) -> None:
        self.wait_calls += 1

    async def call_tool(
        self, server: str, tool: str, arguments: dict[str, Any], *, on_progress: Any = None
    ) -> McpToolResultData:
        return McpToolResultData(blocks=(McpContentBlock(text=f"{server}/{tool}"),), is_error=False)


def _tool_info(name: str, description: str) -> McpToolInfo:
    return McpToolInfo(name=name, description=description, title=None, input_schema={"type": "object"})


class Factory:
    def __init__(self) -> None:
        self.supervisors: list[FakeSupervisor] = []
        self.config_lists: list[tuple[McpServerConfig, ...]] = []

    def __call__(self, configs: Any, environment: Any) -> FakeSupervisor:
        supervisor = FakeSupervisor(configs, environment)
        self.supervisors.append(supervisor)
        self.config_lists.append(supervisor.configs)
        return supervisor


def _write_user_config(paths: BaldricPaths, servers: dict[str, Any]) -> None:
    path = paths.user_mcp_config_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")


def _write_project_config(tmp_path: Path, servers: dict[str, Any]) -> None:
    path = tmp_path / ".baldric" / "mcp.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")


def _runtime(
    tmp_path: Path,
    *,
    trusted: bool = True,
    ui: RecordingUiBridge | None = None,
) -> tuple[ExtensionRuntime, list[tuple[Any, Any]], RecordingUiBridge, BaldricPaths]:
    """A real runtime whose only built-in is the capture-wired mcp extension."""
    from baldric_coding.extensions.builtins import mcp as mcp_extension

    captured: list[tuple[Any, Any]] = []

    def setup_with_context(api: Any, context: Any) -> None:
        captured.append((api, context))
        mcp_extension.setup(api, context)

    paths = BaldricPaths(home=tmp_path / "home-baldric")
    ui_bridge = ui if ui is not None else RecordingUiBridge()
    runtime = ExtensionRuntime(
        paths=paths,
        built_in_extensions=[
            BuiltInExtension(
                name="mcp",
                setup=lambda api: None,
                hidden=True,
                setup_with_context=setup_with_context,
            )
        ],
        ui=ui_bridge,
    )
    runtime.load(
        BaldricResourcePaths(
            root=tmp_path / "home-baldric",
            cwd=tmp_path / "project",
            agents_root=tmp_path / "agents-home",
        )
    )
    session = RecordingSession(tmp_path)
    if not trusted:
        session.project_trust_resolution = None
    runtime.bind(session)
    return runtime, captured, ui_bridge, paths


async def _settle() -> None:
    for _ in range(20):
        await anyio.sleep(0)


async def test_no_config_files_boots_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from baldric_coding.extensions.builtins import mcp as mcp_extension

    factory = Factory()
    monkeypatch.setattr(mcp_extension.extension, "_supervisor_factory", factory)
    runtime, _, _, _ = _runtime(tmp_path)

    await runtime.emit_session_start("startup")
    await _settle()

    assert factory.supervisors == []
    assert runtime.compose_tools([]) == runtime.compose_tools([])  # no crash; no tools added


async def test_untrusted_project_is_ignored_with_a_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from baldric_coding.extensions.builtins import mcp as mcp_extension

    factory = Factory()
    monkeypatch.setattr(mcp_extension.extension, "_supervisor_factory", factory)
    paths = BaldricPaths(home=tmp_path / "home-baldric")
    _write_user_config(paths, {"user-srv": USER_SERVER})
    _write_project_config(tmp_path, {"proj-srv": PROJECT_SERVER})
    runtime, _, ui, _ = _runtime(tmp_path, trusted=False)

    await runtime.emit_session_start("startup")
    await _settle()

    assert len(factory.supervisors) == 1
    assert [server.name for server in factory.config_lists[0]] == ["user-srv"]
    assert any("not trusted" in message for message, _ in ui.notifications)


async def test_trusted_project_servers_boot_and_tools_register(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from baldric_coding.extensions.builtins import mcp as mcp_extension

    factory = Factory()
    monkeypatch.setattr(mcp_extension.extension, "_supervisor_factory", factory)
    paths = BaldricPaths(home=tmp_path / "home-baldric")
    _write_user_config(paths, {"srv": USER_SERVER})
    _write_project_config(tmp_path, {"proj": PROJECT_SERVER})
    runtime, captured, _, _ = _runtime(tmp_path)
    live: list[Any] = []
    runtime.bind_live_tools(live, None)

    await runtime.emit_session_start("startup")
    await _settle()

    assert [sorted(server.name for server in servers) for servers in factory.config_lists] == [
        ["proj", "srv"]
    ]
    supervisor = factory.supervisors[0]
    supervisor.set_server(
        "srv",
        "connected",
        tools=(_tool_info("search", "Search things"), _tool_info("fetch", "Fetch things")),
    )
    await _settle()

    names = sorted(tool.name for tool in live)
    assert names == ["mcp__srv__fetch", "mcp__srv__search"]


async def test_failed_server_withdraws_its_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from baldric_coding.extensions.builtins import mcp as mcp_extension

    factory = Factory()
    monkeypatch.setattr(mcp_extension.extension, "_supervisor_factory", factory)
    _write_user_config(BaldricPaths(home=tmp_path / "home-baldric"), {"srv": USER_SERVER})
    runtime, _, _, _ = _runtime(tmp_path)
    live: list[Any] = []
    runtime.bind_live_tools(live, None)

    await runtime.emit_session_start("startup")
    await _settle()
    supervisor = factory.supervisors[0]
    supervisor.set_server("srv", "connected", tools=(_tool_info("search", "Search"),))
    await _settle()
    assert [tool.name for tool in live] == ["mcp__srv__search"]

    supervisor.set_server("srv", "failed", error="boom")
    await _settle()

    assert live == []


async def test_session_shutdown_closes_the_supervisor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from baldric_coding.extensions.builtins import mcp as mcp_extension

    factory = Factory()
    monkeypatch.setattr(mcp_extension.extension, "_supervisor_factory", factory)
    _write_user_config(BaldricPaths(home=tmp_path / "home-baldric"), {"srv": USER_SERVER})
    runtime, _, _, _ = _runtime(tmp_path)

    await runtime.emit_session_start("startup")
    await _settle()
    await runtime.emit_session_shutdown("quit")

    assert factory.supervisors[0].shutdown_calls == 1


async def test_repeated_session_start_boots_only_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from baldric_coding.extensions.builtins import mcp as mcp_extension

    factory = Factory()
    monkeypatch.setattr(mcp_extension.extension, "_supervisor_factory", factory)
    _write_user_config(BaldricPaths(home=tmp_path / "home-baldric"), {"srv": USER_SERVER})
    runtime, _, _, _ = _runtime(tmp_path)

    await runtime.emit_session_start("startup")
    await _settle()
    await runtime.emit_session_start("startup")
    await _settle()

    assert factory.supervisors[0].start_calls == 1
    assert len(factory.supervisors) == 1


async def test_child_config_excludes_the_mcp_builtin(tmp_path: Path) -> None:
    session = await CodingSession.load(
        CodingSessionConfig(
            provider=FakeProvider([]),
            model="fake",
            storage=JsonlSessionStorage(tmp_path / "child.jsonl"),
            cwd=tmp_path,
            disabled_built_in_extensions=frozenset({"mcp"}),
        )
    )

    assert "mcp" not in [extension.name for extension in session._extension_runtime._extensions]  # noqa: SLF001
