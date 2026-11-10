"""Tests for ``baldric.mcp.supervisor``: ownership of all connections."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest

from baldric.mcp.client import McpConnectionState, McpToolInfo, McpToolUnavailable
from baldric.mcp.config import McpServerConfig
from baldric.mcp.supervisor import McpSupervisor

pytestmark = pytest.mark.anyio


def _infos(*names: str) -> tuple[McpToolInfo, ...]:
    return tuple(McpToolInfo(name=name, description="", title=None, input_schema={}) for name in names)


ENABLED_A = McpServerConfig(name="a", server_type="stdio", command="a-cmd")
ENABLED_B = McpServerConfig(name="b", server_type="http", url="https://b/mcp")
DISABLED_C = McpServerConfig(name="c", server_type="stdio", command="c-cmd", enabled=False)


class FakeClock:
    def __init__(self, now: float = 100.0, step: float = 0.0) -> None:
        self.now = now
        self.step = step

    def __call__(self) -> float:
        current = self.now
        self.now += self.step
        return current


class FakeConnection:
    def __init__(
        self,
        config: McpServerConfig,
        *,
        connect_state: McpConnectionState = "connected",
        tools: tuple[McpToolInfo, ...] = _infos("echo"),
        instructions: str | None = None,
    ) -> None:
        self.config = config
        self.state: McpConnectionState = "connecting"
        self.error: str | None = None
        self.connect_state = connect_state
        self.tools = tools
        self.instructions = instructions
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.connect_count = 0
        self.closed = False

    async def connect(self) -> bool:
        self.connect_count += 1
        self.state = self.connect_state
        if self.connect_state in ("failed", "needs-auth"):
            self.error = f"cannot connect ({self.connect_state})"
            return False
        self.error = None
        return True

    async def call_tool(
        self,
        tool: str,
        arguments: dict[str, Any],
        *,
        on_progress: Callable[[str], None] | None = None,
    ) -> object:
        if self.state != "connected":
            raise McpToolUnavailable(f'"{self.config.name}" is {self.state}')
        self.calls.append((tool, dict(arguments)))
        return object()

    async def close(self) -> None:
        self.closed = True
        self.state = "closed"


class Factory:
    def __init__(self, connect_state: McpConnectionState = "connected") -> None:
        self.connections: dict[str, FakeConnection] = {}
        self.configs: list[McpServerConfig] = []
        self.connect_state = connect_state

    def __call__(self, config: McpServerConfig) -> FakeConnection:
        connection = FakeConnection(config, connect_state=self.connect_state)
        self.connections[config.name] = connection
        self.configs.append(config)
        return connection


async def _supervisor(
    factory: Factory | None = None,
    **kwargs: Any,
) -> tuple[McpSupervisor, Factory]:
    factory = factory or Factory()
    supervisor = McpSupervisor(
        [ENABLED_A, ENABLED_B, DISABLED_C],
        environment={},
        connection_factory=factory,
        **kwargs,
    )
    return supervisor, factory


async def test_start_connects_enabled_concurrently_and_skips_disabled() -> None:
    supervisor, factory = await _supervisor()

    await supervisor.start()

    assert factory.connections["a"].state == "connected"
    assert factory.connections["b"].state == "connected"
    assert "c" not in factory.connections  # disabled: no connection exists at all
    assert not supervisor.any_connecting()


async def test_wait_ready_returns_promptly_when_nothing_connecting() -> None:
    supervisor, _ = await _supervisor()

    await supervisor.wait_ready()  # nothing connecting: returns without waiting


async def test_wait_ready_caps_while_connecting() -> None:
    factory = Factory(connect_state="connecting")
    supervisor, _ = await _supervisor(factory, wait_ready_cap=0.2, clock=FakeClock(step=0.1))
    await supervisor.start()

    await supervisor.wait_ready(timeout=30.0)  # capped by wait_ready_cap, never raises

    assert supervisor.any_connecting() is True


async def test_on_change_fires_on_state_affecting_operations() -> None:
    supervisor, factory = await _supervisor()
    fired: list[str] = []
    supervisor.on_change(lambda: fired.append("x"))

    await supervisor.start()
    await factory.connections["b"].connect()
    config = McpServerConfig(name="b", server_type="http", url="https://b2/mcp")
    await supervisor.restart("b", config)
    await supervisor.set_enabled("c", True, replace(DISABLED_C, enabled=True))
    await supervisor.shutdown()

    assert len(fired) >= 4


async def test_call_tool_routes_to_the_right_connection() -> None:
    supervisor, factory = await _supervisor()
    await supervisor.start()

    await supervisor.call_tool("a", "echo", {"x": 1})
    await supervisor.call_tool("b", "echo", {})

    assert factory.connections["a"].calls == [("echo", {"x": 1})]
    assert factory.connections["b"].calls == [("echo", {})]


async def test_call_tool_unknown_server_or_tool_raises() -> None:
    supervisor, _ = await _supervisor()
    await supervisor.start()

    with pytest.raises(McpToolUnavailable):
        await supervisor.call_tool("missing", "echo", {})
    with pytest.raises(McpToolUnavailable):
        await supervisor.call_tool("a", "no-such-tool", {})


async def test_set_enabled_false_closes_and_hides_tools() -> None:
    supervisor, factory = await _supervisor()
    await supervisor.start()

    await supervisor.set_enabled("a", False, None)

    assert factory.connections["a"].closed is True
    status = next(status for status in supervisor.statuses() if status.name == "a")
    assert status.tool_count == 0
    with pytest.raises(McpToolUnavailable):
        await supervisor.call_tool("a", "echo", {})


async def test_set_enabled_true_connects_with_provided_config() -> None:
    supervisor, factory = await _supervisor()
    await supervisor.start()
    enabled_config = replace(DISABLED_C, enabled=True)

    await supervisor.set_enabled("c", True, enabled_config)

    assert factory.connections["c"].state == "connected"
    assert factory.configs[-1] == enabled_config


async def test_restart_replaces_the_connection() -> None:
    supervisor, factory = await _supervisor()
    await supervisor.start()
    old = factory.connections["a"]
    config = McpServerConfig(name="a", server_type="stdio", command="a2-cmd")

    await supervisor.restart("a", config)

    assert old.closed is True
    assert factory.connections["a"] is not old
    assert factory.connections["a"].config == config
    assert factory.connections["a"].state == "connected"


async def test_shutdown_closes_all_and_blocks_calls() -> None:
    supervisor, factory = await _supervisor()
    await supervisor.start()

    await supervisor.shutdown()

    assert factory.connections["a"].closed is True
    assert factory.connections["b"].closed is True
    with pytest.raises(McpToolUnavailable):
        await supervisor.call_tool("a", "echo", {})


async def test_statuses_reflect_states_and_tool_counts() -> None:
    factory = Factory()
    factory.connect_state = "needs-auth"
    supervisor, _ = await _supervisor(factory)
    await supervisor.start()

    statuses = {status.name: status for status in supervisor.statuses()}

    assert statuses["a"].state == "needs-auth"
    assert statuses["a"].tool_count == 0
    assert "cannot connect" in (statuses["a"].error or "")
    assert statuses["c"].state == "closed"  # disabled from the start


def test_stderr_sink_factory_binds_each_connection() -> None:
    created: list[str] = []

    def make(config: McpServerConfig) -> object:
        created.append(config.name)
        return object()

    supervisor = McpSupervisor([ENABLED_A, ENABLED_B], environment={}, stderr_sink_factory=make)

    # The sink opens per connect attempt, bound to that server's config.
    connection = supervisor._connections["a"]  # noqa: SLF001 - asserting the wiring
    sink_factory = connection._stderr_sink_factory  # noqa: SLF001
    assert sink_factory is not None
    assert sink_factory() is not None
    assert created == ["a"]
