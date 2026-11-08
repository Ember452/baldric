"""Ownership of all MCP server connections for one session.

The supervisor never reads config files or paths (low coupling): ``restart``
and ``set_enabled(..., config)`` receive re-read configs from the extension
layer. Disabled servers have no connection at all; they appear in
``statuses()`` as ``closed`` until enabled.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from functools import partial
from typing import Any

import anyio

from baldric_mcp.client import (
    McpConnectionState,
    McpServerConnection,
    McpToolInfo,
    McpToolResultData,
    McpToolUnavailable,
)
from baldric_mcp.config import McpServerConfig
from baldric_protocol.types import JSONValue


@dataclass(frozen=True, slots=True)
class McpServerStatus:
    """User-facing snapshot of one configured server."""

    name: str
    state: McpConnectionState
    tool_count: int
    error: str | None


class McpSupervisor:
    """Owns one connection per enabled server and routes tool calls."""

    def __init__(
        self,
        configs: Sequence[McpServerConfig],
        *,
        environment: Mapping[str, str],
        connection_factory: Callable[[McpServerConfig], McpServerConnection] | None = None,
        wait_ready_cap: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
        stderr_sink_factory: Callable[[McpServerConfig], Any] | None = None,
    ) -> None:
        self._environment = environment
        self._connection_factory = connection_factory
        self._wait_ready_cap = wait_ready_cap
        self._clock = clock
        self._stderr_sink_factory = stderr_sink_factory
        self._configs: dict[str, McpServerConfig] = {}
        self._connections: dict[str, McpServerConnection] = {}
        self._on_change: Callable[[], None] | None = None
        for config in configs:
            self._configs[config.name] = config
            if config.enabled:
                self._connections[config.name] = self._build(config)

    def statuses(self) -> tuple[McpServerStatus, ...]:
        """Snapshot every configured server in config order."""
        statuses: list[McpServerStatus] = []
        for name in self._configs:
            connection = self._connections.get(name)
            state = connection.state if connection is not None else "closed"
            tool_count = len(connection.tools) if connection is not None and state == "connected" else 0
            statuses.append(
                McpServerStatus(
                    name=name,
                    state=state,
                    tool_count=tool_count,
                    error=connection.error if connection is not None else None,
                )
            )
        return tuple(statuses)

    def any_connecting(self) -> bool:
        return any(connection.state == "connecting" for connection in self._connections.values())

    def tool_names(self, server: str) -> tuple[McpToolInfo, ...]:
        """The server's advertised tools; empty when absent."""
        connection = self._connections.get(server)
        return connection.tools if connection is not None else ()

    def instructions(self, server: str) -> str | None:
        connection = self._connections.get(server)
        return connection.instructions if connection is not None else None

    def on_change(self, callback: Callable[[], None]) -> None:
        """Register the change callback; the last registration wins."""
        self._on_change = callback

    async def start(self) -> None:
        """Connect every enabled server concurrently; failures stay recorded."""
        connections = list(self._connections.values())
        if connections:
            async with anyio.create_task_group() as tg:
                for connection in connections:
                    tg.start_soon(self._connect_quietly, connection)
        self._fire()

    async def wait_ready(self, timeout: float = 10.0) -> None:
        """Bounded wait for first-turn admission; never raises."""
        deadline = self._clock() + min(timeout, self._wait_ready_cap)
        while self.any_connecting() and self._clock() < deadline:
            await anyio.sleep(0.05)

    async def call_tool(
        self,
        server: str,
        tool: str,
        arguments: Mapping[str, JSONValue],
        *,
        on_progress: Callable[[str], None] | None = None,
    ) -> McpToolResultData:
        connection = self._connections.get(server)
        if connection is None:
            raise McpToolUnavailable(f'unknown MCP server "{server}"')
        if tool not in {info.name for info in connection.tools}:
            raise McpToolUnavailable(f'MCP server "{server}" has no tool "{tool}"')
        return await connection.call_tool(tool, dict(arguments), on_progress=on_progress)

    async def restart(self, name: str, config: McpServerConfig) -> None:
        """Close the old connection and connect a fresh one with ``config``."""
        self._configs[name] = config
        await self._replace_connection(name, config)
        self._fire()

    async def set_enabled(self, name: str, enabled: bool, config: McpServerConfig | None) -> None:
        """Apply ``/mcp on|off``: build and connect, or close and keep closed."""
        if config is not None:
            self._configs[name] = config
        if enabled:
            effective = self._configs.get(name)
            if effective is None:
                raise McpToolUnavailable(f'unknown MCP server "{name}"')
            await self._replace_connection(name, effective)
        else:
            connection = self._connections.get(name)
            if connection is not None:
                await connection.close()
        self._fire()

    async def shutdown(self) -> None:
        """Close every connection; calls afterwards fail with ``closed``.

        Connections close concurrently (pi's ``Promise.all`` shutdown): one
        stuck teardown must not delay the others.
        """
        if self._connections:
            async with anyio.create_task_group() as tg:
                for connection in self._connections.values():
                    tg.start_soon(connection.close)
        self._fire()

    def _build(self, config: McpServerConfig) -> McpServerConnection:
        if self._connection_factory is not None:
            return self._connection_factory(config)
        # The sink factory is bound to this server: each connect attempt opens
        # a fresh stderr log handle (teardown closes the previous one).
        sink_factory = (
            partial(self._stderr_sink_factory, config) if self._stderr_sink_factory is not None else None
        )
        return McpServerConnection(
            config,
            environment=self._environment,
            stderr_sink_factory=sink_factory,
        )

    async def _replace_connection(self, name: str, config: McpServerConfig) -> None:
        old = self._connections.get(name)
        if old is not None:
            await old.close()
        connection = self._build(config)
        self._connections[name] = connection
        await self._connect_quietly(connection)

    @staticmethod
    async def _connect_quietly(connection: McpServerConnection) -> None:
        # connect() records failures in the connection itself; an unexpected
        # exception must not escape start()/set_enabled()/restart().
        with suppress(Exception):
            await connection.connect()

    def _fire(self) -> None:
        if self._on_change is not None:
            self._on_change()


__all__ = ["McpServerStatus", "McpSupervisor"]
