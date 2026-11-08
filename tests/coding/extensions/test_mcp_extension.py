"""Tests for the bundled MCP extension: boot, trust gate, dynamic registration."""

from __future__ import annotations

import json
import os
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

    def __init__(self, configs: Any, environment: Any, **kwargs: Any) -> None:
        self.configs = tuple(configs)
        self.environment = dict(environment)
        self.kwargs = kwargs
        self.start_calls = 0
        self.shutdown_calls = 0
        self.wait_calls = 0
        self.enabled_calls: list[tuple[str, bool, Any]] = []
        self.restart_calls: list[tuple[str, str]] = []
        self.next_result: Any = None
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

    async def set_enabled(self, name: str, enabled: bool, config: Any) -> None:
        self.enabled_calls.append((name, enabled, config))

    async def restart(self, name: str, config: Any) -> None:
        self.restart_calls.append((name, config.command))

    async def wait_ready(self, timeout: float = 10.0) -> None:
        self.wait_calls += 1

    async def call_tool(
        self, server: str, tool: str, arguments: dict[str, Any], *, on_progress: Any = None
    ) -> McpToolResultData:
        if self.next_result is not None:
            return self.next_result
        return McpToolResultData(blocks=(McpContentBlock(text=f"{server}/{tool}"),), is_error=False)


def _tool_info(name: str, description: str) -> McpToolInfo:
    return McpToolInfo(name=name, description=description, title=None, input_schema={"type": "object"})


class Factory:
    def __init__(self) -> None:
        self.supervisors: list[FakeSupervisor] = []
        self.config_lists: list[tuple[McpServerConfig, ...]] = []
        self.kwargs: dict[str, Any] = {}

    def __call__(self, configs: Any, environment: Any, **kwargs: Any) -> FakeSupervisor:
        supervisor = FakeSupervisor(configs, environment, **kwargs)
        self.supervisors.append(supervisor)
        self.config_lists.append(supervisor.configs)
        self.kwargs.update(kwargs)
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


async def test_first_input_waits_once_while_connecting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from baldric_coding.extensions.builtins import mcp as mcp_extension

    factory = Factory()
    monkeypatch.setattr(mcp_extension.extension, "_supervisor_factory", factory)
    _write_user_config(BaldricPaths(home=tmp_path / "home-baldric"), {"srv": USER_SERVER})
    runtime, captured, _, _ = _runtime(tmp_path)
    await runtime.emit_session_start("startup")
    await _settle()
    supervisor = factory.supervisors[0]
    supervisor.set_server("srv", "connecting")

    await runtime.run_input_hooks("one")
    await runtime.run_input_hooks("two")

    assert supervisor.wait_calls == 1

    supervisor.set_server("srv", "connected", tools=(_tool_info("search", "Search"),))
    await runtime.run_input_hooks("three")

    assert supervisor.wait_calls == 1  # admitted once; later inputs never wait


async def test_prompt_section_registers_once_and_refreshes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from baldric_coding.extensions.builtins import mcp as mcp_extension

    factory = Factory()
    monkeypatch.setattr(mcp_extension.extension, "_supervisor_factory", factory)
    _write_user_config(BaldricPaths(home=tmp_path / "home-baldric"), {"srv": USER_SERVER})
    runtime, _, _, _ = _runtime(tmp_path)
    session = runtime._session  # noqa: SLF001 - the bound RecordingSession
    assert isinstance(session, RecordingSession)
    await runtime.emit_session_start("startup")
    await _settle()

    supervisor = factory.supervisors[0]
    supervisor.set_server(
        "srv",
        "connected",
        tools=(_tool_info("a", "A"), _tool_info("b", "B")),
        instructions="Inst line one.\nline two",
    )
    await _settle()

    sections = [section for section in runtime.sourced_prompt_sections if section.title == "MCP servers"]
    assert len(sections) == 1
    assert sections[0].body == "- srv (stdio, 2 tools): Inst line one."
    assert session.refresh_calls >= 1  # type: ignore[union-attr]


async def test_prompt_section_caps_lines_and_total(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from baldric_coding.extensions.builtins import mcp as mcp_extension

    factory = Factory()
    monkeypatch.setattr(mcp_extension.extension, "_supervisor_factory", factory)
    _write_user_config(
        BaldricPaths(home=tmp_path / "home-baldric"),
        {"a": USER_SERVER, "b": USER_SERVER, "c": USER_SERVER},
    )
    runtime, _, _, _ = _runtime(tmp_path)
    await runtime.emit_session_start("startup")
    await _settle()

    supervisor = factory.supervisors[0]
    long_description = "x" * 300
    supervisor.set_server("a", "connected", tools=(), instructions=long_description)
    supervisor.set_server("b", "connected", tools=(), instructions=long_description)
    supervisor.set_server("c", "connected", tools=(), instructions=long_description)
    await _settle()

    sections = [section for section in runtime.sourced_prompt_sections if section.title == "MCP servers"]
    assert len(sections) == 1
    body = sections[0].body
    assert len(body) <= 1200
    for line in body.splitlines():
        assert len(line) <= 200


async def test_prompt_section_omits_detail_without_description_or_instructions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from baldric_coding.extensions.builtins import mcp as mcp_extension

    factory = Factory()
    monkeypatch.setattr(mcp_extension.extension, "_supervisor_factory", factory)
    _write_user_config(BaldricPaths(home=tmp_path / "home-baldric"), {"bare": USER_SERVER})
    runtime, _, _, _ = _runtime(tmp_path)
    await runtime.emit_session_start("startup")
    await _settle()

    factory.supervisors[0].set_server("bare", "connected", tools=(_tool_info("t", "T"),))
    await _settle()

    sections = [section for section in runtime.sourced_prompt_sections if section.title == "MCP servers"]
    assert sections[0].body == "- bare (stdio, 1 tools)"


def _mcp_handler(runtime: ExtensionRuntime, api: Any) -> Callable[[str], str | None]:
    from baldric_coding.extensions.api import ExtensionCommandContext

    handler = runtime._commands["mcp"].handler  # noqa: SLF001 - test reaches the command
    return lambda args: handler(args, ExtensionCommandContext(name="mcp", args=args, api=api))


async def test_mcp_command_lists_servers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from baldric_coding.extensions.builtins import mcp as mcp_extension

    factory = Factory()
    monkeypatch.setattr(mcp_extension.extension, "_supervisor_factory", factory)
    _write_user_config(BaldricPaths(home=tmp_path / "home-baldric"), {"srv": USER_SERVER})
    runtime, captured, _, _ = _runtime(tmp_path)
    await runtime.emit_session_start("startup")
    await _settle()
    factory.supervisors[0].set_server("srv", "connected", tools=(_tool_info("t", "T"),))
    factory.supervisors[0].set_server("bad", "failed", error="boom\nstack")
    await _settle()

    message = _mcp_handler(runtime, captured[0][0])("")

    assert message == "srv  connected  stdio  1 tools\nbad  failed  stdio  0 tools: boom"


async def test_mcp_off_persists_and_disables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from baldric_coding.extensions.builtins import mcp as mcp_extension

    factory = Factory()
    monkeypatch.setattr(mcp_extension.extension, "_supervisor_factory", factory)
    paths = BaldricPaths(home=tmp_path / "home-baldric")
    _write_user_config(paths, {"srv": USER_SERVER})
    runtime, captured, _, _ = _runtime(tmp_path)
    await runtime.emit_session_start("startup")
    await _settle()

    message = _mcp_handler(runtime, captured[0][0])("off srv")
    await _settle()

    assert message == "mcp: disabling srv"
    text = paths.user_mcp_config_path.read_text(encoding="utf-8")
    assert '"enabled": false' in text
    supervisor = factory.supervisors[0]
    assert supervisor.enabled_calls == [("srv", False, None)]


async def test_mcp_on_rereads_and_enables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from baldric_coding.extensions.builtins import mcp as mcp_extension

    factory = Factory()
    monkeypatch.setattr(mcp_extension.extension, "_supervisor_factory", factory)
    paths = BaldricPaths(home=tmp_path / "home-baldric")
    _write_user_config(paths, {"srv": {**USER_SERVER, "enabled": False}})
    runtime, captured, _, _ = _runtime(tmp_path)
    await runtime.emit_session_start("startup")
    await _settle()

    message = _mcp_handler(runtime, captured[0][0])("on srv")
    await _settle()

    assert message == "mcp: enabling srv"
    supervisor = factory.supervisors[0]
    assert len(supervisor.enabled_calls) == 1
    name, enabled, fresh = supervisor.enabled_calls[0]
    assert (name, enabled) == ("srv", True)
    assert fresh is not None and fresh.command == "srv-cmd" and fresh.enabled is True


async def test_mcp_restart_reconnects_with_fresh_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from baldric_coding.extensions.builtins import mcp as mcp_extension

    factory = Factory()
    monkeypatch.setattr(mcp_extension.extension, "_supervisor_factory", factory)
    _write_user_config(BaldricPaths(home=tmp_path / "home-baldric"), {"srv": USER_SERVER})
    runtime, captured, _, _ = _runtime(tmp_path)
    await runtime.emit_session_start("startup")
    await _settle()

    message = _mcp_handler(runtime, captured[0][0])("restart srv")
    await _settle()

    assert message == "mcp: restarting srv"
    supervisor = factory.supervisors[0]
    assert supervisor.restart_calls == [("srv", "srv-cmd")]


async def test_stderr_sink_factory_wired_and_opens_the_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from baldric_coding.extensions.builtins import mcp as mcp_extension

    factory = Factory()
    monkeypatch.setattr(mcp_extension.extension, "_supervisor_factory", factory)
    _write_user_config(BaldricPaths(home=tmp_path / "home-baldric"), {"srv": USER_SERVER})
    runtime, _, _, _ = _runtime(tmp_path)
    await runtime.emit_session_start("startup")
    await _settle()

    make_sink = factory.kwargs["stderr_sink_factory"]
    assert callable(make_sink)

    sink = make_sink(factory.supervisors[0].configs[0])

    try:
        assert sink.name.endswith(f"mcp{os.sep}srv.log")
    finally:
        sink.close()


async def test_output_saver_saves_full_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from baldric_coding.extensions.builtins import mcp as mcp_extension

    factory = Factory()
    monkeypatch.setattr(mcp_extension.extension, "_supervisor_factory", factory)
    _write_user_config(BaldricPaths(home=tmp_path / "home-baldric"), {"srv": USER_SERVER})
    runtime, captured, _, _ = _runtime(tmp_path)
    live: list[Any] = []
    runtime.bind_live_tools(live, None)
    await runtime.emit_session_start("startup")
    await _settle()

    full_text = "y" * 40000
    factory.supervisors[0].set_server("srv", "connected", tools=(_tool_info("big", "Big"),))
    await _settle()
    factory.supervisors[0].next_result = McpToolResultData(
        blocks=(McpContentBlock(text=full_text),), is_error=False
    )

    result = await live[0].execute("call-1", {}, None, None)

    note = result.content[0].text
    marker = "[Full output: "
    assert marker in note
    saved_path = note.split(marker, 1)[1].split(" (read it with offset/limit)]", 1)[0]
    assert Path(saved_path).read_text(encoding="utf-8") == full_text


async def test_mcp_unknown_server_reports_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from baldric_coding.extensions.builtins import mcp as mcp_extension

    factory = Factory()
    monkeypatch.setattr(mcp_extension.extension, "_supervisor_factory", factory)
    _write_user_config(BaldricPaths(home=tmp_path / "home-baldric"), {"srv": USER_SERVER})
    runtime, captured, _, _ = _runtime(tmp_path)
    await runtime.emit_session_start("startup")
    await _settle()

    message = _mcp_handler(runtime, captured[0][0])("off nope")

    assert 'unknown server "nope"' in (message or "")
