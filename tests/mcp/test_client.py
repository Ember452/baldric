"""Tests for ``baldric_mcp.client``: one supervised connection per server."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import anyio
import httpx
import mcp.types as mt
import pytest

from baldric_mcp.client import (
    McpNeedsAuthError,
    McpServerConnection,
    McpToolUnavailable,
)
from baldric_mcp.config import McpServerConfig

pytestmark = pytest.mark.anyio


def anyio_backend() -> str:
    return "asyncio"


HTTP_CONFIG = McpServerConfig(name="srv", server_type="http", url="https://example.com/mcp")
STDIO_CONFIG = McpServerConfig(name="srv", server_type="stdio", command="srv-cmd")


class FakeClock:
    def __init__(self, now: float = 100.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class FakeSession:
    """Scripted ClientSession stand-in."""

    def __init__(
        self,
        *,
        initialize_error: Exception | None = None,
        tools: list[mt.Tool] | None = None,
        instructions: str | None = None,
        call_results: list[Any] | None = None,
        call_hook: Callable[..., None] | None = None,
        has_tools_capability: bool = True,
    ) -> None:
        self.initialize_error = initialize_error
        self.tools = tools if tools is not None else [mt.Tool(name="echo", inputSchema={"type": "object"})]
        self.instructions = instructions
        self.call_results = list(call_results or [])
        self.call_hook = call_hook
        self.has_tools_capability = has_tools_capability
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.initialized = 0

    async def initialize(self) -> mt.InitializeResult:
        self.initialized += 1
        if self.initialize_error is not None:
            raise self.initialize_error
        return mt.InitializeResult(
            protocolVersion="2025-06-18",
            capabilities=(
                mt.ServerCapabilities(tools=mt.ToolsCapability())
                if self.has_tools_capability
                else mt.ServerCapabilities()
            ),
            serverInfo=mt.Implementation(name="fake", version="0"),
            instructions=self.instructions,
        )

    def get_server_capabilities(self) -> mt.ServerCapabilities | None:
        return (
            mt.ServerCapabilities(tools=mt.ToolsCapability())
            if self.has_tools_capability
            else mt.ServerCapabilities()
        )

    async def list_tools(self) -> mt.ListToolsResult:
        return mt.ListToolsResult(tools=self.tools)

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None, **kwargs: Any
    ) -> mt.CallToolResult:
        self.calls.append((name, dict(arguments or {})))
        if self.call_hook is not None:
            await self.call_hook(self, kwargs.get("progress_callback"))
        if self.call_results:
            outcome = self.call_results.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return mt.CallToolResult(content=[mt.TextContent(type="text", text="ok")])

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


class FakeTransport:
    def __init__(self, session: FakeSession) -> None:
        self.session = session
        self.entered = 0
        self.exited = 0

    async def __aenter__(self) -> tuple[object, object]:
        self.entered += 1
        return (object(), object())

    async def __aexit__(self, *exc: object) -> bool:
        self.exited += 1
        return False


class Harness:
    """Scripted transports/sessions in connect order."""

    def __init__(self, sessions: list[FakeSession]) -> None:
        self.sessions = sessions
        self.transports: list[FakeTransport] = []

    def transport_factory(self, config: McpServerConfig, environment: Any = None) -> FakeTransport:
        transport = FakeTransport(self.sessions[len(self.transports)])
        self.transports.append(transport)
        return transport

    def session_factory(self, read: Any, write: Any) -> FakeSession:
        return self.transports[-1].session

    def connection(self, config: McpServerConfig = HTTP_CONFIG, **kwargs: Any) -> McpServerConnection:
        defaults: dict[str, Any] = {
            "environment": {},
            "transport_factory": self.transport_factory,
            "session_factory": self.session_factory,
            "clock": FakeClock(),
            "retry_delays": (0.0, 0.0),
        }
        defaults.update(kwargs)
        return McpServerConnection(config, **defaults)


def status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.com/mcp")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(f"HTTP {status}", request=request, response=response)


async def test_successful_connect() -> None:
    harness = Harness(
        [
            FakeSession(
                tools=[mt.Tool(name="echo", description="Echo", inputSchema={"type": "object"})],
                instructions="  echo server  ",
            )
        ]
    )
    connection = harness.connection()

    assert await connection.connect() is True

    assert connection.state == "connected"
    assert connection.error is None
    assert [tool.name for tool in connection.tools] == ["echo"]
    assert connection.tools[0].description == "Echo"
    assert connection.instructions == "echo server"  # trimmed


async def test_transient_failure_then_success() -> None:
    harness = Harness([FakeSession(initialize_error=TimeoutError("boom")), FakeSession()])
    connection = harness.connection()

    assert await connection.connect() is True

    assert connection.state == "connected"
    assert len(harness.transports) == 2
    assert harness.transports[0].exited == 1  # the failed attempt tore down


async def test_retry_budget_exhausted() -> None:
    harness = Harness([FakeSession(initialize_error=TimeoutError("boom")) for _ in range(3)])
    connection = harness.connection()

    assert await connection.connect() is False

    assert connection.state == "failed"
    assert "boom" in (connection.error or "")
    assert len(harness.transports) == 3  # 1 + len(retry_delays)


async def test_non_transient_failure_fails_immediately() -> None:
    harness = Harness([FakeSession(initialize_error=ValueError("bad config")), FakeSession()])
    connection = harness.connection()

    assert await connection.connect() is False

    assert connection.state == "failed"
    assert len(harness.transports) == 1


async def test_http_401_maps_to_needs_auth_without_retry() -> None:
    harness = Harness([FakeSession(initialize_error=status_error(401)), FakeSession()])
    connection = harness.connection()

    assert await connection.connect() is False

    assert connection.state == "needs-auth"
    assert len(harness.transports) == 1


async def test_http_401_inside_exception_group_maps_to_needs_auth() -> None:
    harness = Harness(
        [FakeSession(initialize_error=ExceptionGroup("eg", [status_error(401)])), FakeSession()]
    )
    connection = harness.connection()

    assert await connection.connect() is False

    assert connection.state == "needs-auth"


async def test_lazy_reconnect_after_drop() -> None:
    dropped = FakeSession(call_results=[ConnectionError("pipe closed")])
    restored = FakeSession()
    harness = Harness([dropped, restored])
    connection = harness.connection()
    assert await connection.connect() is True

    with pytest.raises(McpToolUnavailable):
        await connection.call_tool("echo", {})

    assert connection.state == "disconnected"

    result = await connection.call_tool("echo", {"x": 1})

    assert connection.state == "connected"
    assert result.blocks[0].text == "ok"
    assert len(harness.transports) == 2
    assert restored.calls == [("echo", {"x": 1})]


async def test_call_while_failed_or_closed_raises() -> None:
    harness = Harness([FakeSession(initialize_error=ValueError("bad"))])
    connection = harness.connection()
    assert await connection.connect() is False

    with pytest.raises(McpToolUnavailable):
        await connection.call_tool("echo", {})

    await connection.close()
    with pytest.raises(McpToolUnavailable):
        await connection.call_tool("echo", {})


async def test_call_timeout_keeps_state_connected() -> None:
    clock = FakeClock()

    async def hook(session: FakeSession, progress_callback: object) -> None:
        clock.now = 200.0  # blow past the deadline mid-call
        await anyio.sleep(0.5)  # the watchdog (poll cap 0.25s) cancels first

    harness = Harness([FakeSession(call_hook=hook)])
    connection = harness.connection(clock=clock)
    connection._config = McpServerConfig(  # noqa: SLF001 - test-only timeout tweak
        name="srv", server_type="http", url="https://example.com/mcp", timeout=5.0
    )
    assert await connection.connect() is True

    with pytest.raises(McpToolUnavailable, match="timed out"):
        await connection.call_tool("echo", {})

    assert connection.state == "connected"


async def test_progress_resets_deadline_and_reports() -> None:
    clock = FakeClock(now=100.0)
    messages: list[str] = []

    async def hook(session: FakeSession, progress_callback: object) -> None:
        clock.now = 104.0
        assert progress_callback is not None
        await progress_callback(1, 2, "half")  # deadline -> 109
        clock.now = 108.0  # past the unreset deadline, inside the reset one
        await anyio.sleep(0.3)  # the watchdog polls but must not fire

    harness = Harness([FakeSession(call_hook=hook)])
    connection = harness.connection(clock=clock)
    connection._config = McpServerConfig(  # noqa: SLF001 - test-only timeout tweak
        name="srv", server_type="http", url="https://example.com/mcp", timeout=5.0
    )
    assert await connection.connect() is True

    result = await connection.call_tool("echo", {}, on_progress=messages.append)

    assert result.blocks[0].text == "ok"
    assert messages == ["Progress 1/2 half"]
    assert connection.state == "connected"


async def test_result_mapping() -> None:
    session = FakeSession(
        call_results=[
            mt.CallToolResult(content=[mt.TextContent(type="text", text="hi")]),
            mt.CallToolResult(content=[mt.ImageContent(type="image", data="aGk=", mimeType="image/png")]),
            mt.CallToolResult(content=[], structuredContent={"a": 1}),
            mt.CallToolResult(content=[mt.TextContent(type="text", text="nope")], isError=True),
        ]
    )
    harness = Harness([session])
    connection = harness.connection()
    assert await connection.connect() is True

    text = await connection.call_tool("echo", {})
    image = await connection.call_tool("echo", {})
    structured = await connection.call_tool("echo", {})
    error = await connection.call_tool("echo", {})

    assert text.blocks[0].text == "hi"
    assert text.is_error is False
    assert image.blocks[0].image_data == "aGk="
    assert image.blocks[0].image_mime == "image/png"
    assert structured.blocks[0].text == '{"a": 1}'
    assert error.is_error is True
    assert session.calls == [("echo", {})] * 4


async def test_close_exits_transport() -> None:
    harness = Harness([FakeSession()])
    connection = harness.connection()
    assert await connection.connect() is True

    await connection.close()

    assert connection.state == "closed"
    assert harness.transports[0].exited == 1
    await connection.close()  # idempotent


async def test_needs_auth_sentinel_exists() -> None:
    """The 401 sentinel stays importable for the transport error path."""

    assert issubclass(McpNeedsAuthError, RuntimeError)
