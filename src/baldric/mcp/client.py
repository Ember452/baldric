"""One supervised MCP server connection: state machine, retries, per-call deadline.

Ports pi's connection semantics
(``pi-main/packages/coding-agent/src/extensions/mcp/runtime.ts``): the
``connecting/connected/disconnected/needs-auth/failed/closed`` state machine,
transient-error retry for initial connects (HTTP servers only — a stdio spawn
failure is deterministic), lazy reconnect when a dropped connection is next
used, and a per-call deadline that progress notifications reset.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from dataclasses import dataclass
from functools import partial
from typing import Any, Literal, Protocol

import anyio
import httpx
import mcp.types as mt
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters
from mcp.client.stdio import stdio_client as _sdk_stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

from baldric.mcp.config import McpServerConfig
from baldric.protocol.types import JSONValue

McpConnectionState = Literal["connecting", "connected", "disconnected", "needs-auth", "failed", "closed"]

# Cap between deadline polls so a frozen test clock cannot spin the watchdog.
_WATCHDOG_POLL_SECONDS = 0.25

_MISSING = object()


class McpToolUnavailable(RuntimeError):
    """The tool call cannot be served: server failed, needs auth, or closed."""


@dataclass(frozen=True, slots=True)
class McpToolInfo:
    """One tool as the server advertised it."""

    name: str
    description: str
    title: str | None
    input_schema: Mapping[str, JSONValue]


@dataclass(frozen=True, slots=True)
class McpContentBlock:
    """One content block of a tool result."""

    text: str | None = None
    image_data: str | None = None
    image_mime: str | None = None


@dataclass(frozen=True, slots=True)
class McpToolResultData:
    """A converted tool result."""

    blocks: tuple[McpContentBlock, ...]
    is_error: bool


class McpTransport(Protocol):
    """Async context manager yielding ``(read_stream, write_stream)``."""

    async def __aenter__(self) -> tuple[Any, Any]: ...

    async def __aexit__(self, *exc: object) -> bool: ...


TransportFactory = Callable[[McpServerConfig, Mapping[str, str]], Any]
SessionFactory = Callable[[Any, Any], Any]


def default_transport(
    config: McpServerConfig,
    environment: Mapping[str, str],
    stderr_sink: Any = None,
) -> Any:
    """Build the SDK transport for one configured server.

    The command is passed verbatim: the SDK resolves Windows ``.cmd``/``.bat``
    shims itself. The merged snapshot+config env supersedes the SDK's default
    environment (stdio_client merges the passed env over
    ``get_default_environment()``).
    """
    if config.server_type == "http":
        # Config validation pairs the http type with a url.
        assert config.url is not None
        http_client = create_mcp_http_client(headers=dict(config.headers))
        return _pair_transport(streamable_http_client(config.url, http_client=http_client))
    params = StdioServerParameters(
        command=config.command or "",
        args=list(config.args),
        env={**environment, **config.env},
        cwd=config.cwd,
    )
    if stderr_sink is not None:
        return _sdk_stdio_client(params, errlog=stderr_sink)
    return _sdk_stdio_client(params)


@asynccontextmanager
async def _pair_transport(triplets: Any) -> Any:
    """Normalize the http transport's ``(read, write, get_session_id)`` yield."""
    async with triplets as streams:
        yield streams[0], streams[1]


def _iter_exceptions(error: BaseException) -> Iterator[BaseException]:
    """Flatten (possibly nested) ExceptionGroups from the anyio transport layer."""
    if isinstance(error, ExceptionGroup):
        for inner in error.exceptions:
            yield from _iter_exceptions(inner)
    else:
        yield error


def _needs_auth(error: BaseException) -> bool:
    """HTTP 401 during connect means the server wants credentials, not retries."""
    return any(
        isinstance(item, httpx.HTTPStatusError) and item.response.status_code == 401
        for item in _iter_exceptions(error)
    )


def _is_transient(error: BaseException) -> bool:
    """Network failures and overloaded/restarting servers (pi: isTransientError)."""
    for item in _iter_exceptions(error):
        if isinstance(item, httpx.HTTPStatusError):
            status = item.response.status_code
            if status == 408 or status == 429 or (status >= 500 and status != 501):
                return True
        if isinstance(item, (TimeoutError, ConnectionError, OSError)):
            return True
        if isinstance(item, (anyio.BrokenResourceError, anyio.EndOfStream, anyio.ClosedResourceError)):
            return True
    return False


def _is_connection_dropped(error: BaseException) -> bool:
    """The transport died under an in-flight call; the next call reconnects."""
    dropped = (
        ConnectionError,
        OSError,
        anyio.BrokenResourceError,
        anyio.ClosedResourceError,
        anyio.EndOfStream,
    )
    return any(isinstance(item, dropped) for item in _iter_exceptions(error))


def _message(error: BaseException) -> str:
    return str(error) or type(error).__name__


def _progress_text(progress: float, total: float | None, message: str | None) -> str:
    total_text = "unknown" if total is None else f"{total:g}"
    return f"Progress {progress:g}/{total_text} {message or ''}".rstrip()


class _Deadline:
    """Shared, mutable per-call deadline; progress notifications push it out."""

    __slots__ = ("deadline",)

    def __init__(self, deadline: float) -> None:
        self.deadline = deadline


class McpServerConnection:
    """Owns one server's transport and session across reconnects."""

    def __init__(
        self,
        config: McpServerConfig,
        *,
        environment: Mapping[str, str],
        transport_factory: TransportFactory = default_transport,
        session_factory: SessionFactory | None = None,
        clock: Callable[[], float] = time.monotonic,
        retry_delays: Sequence[float] = (1.0, 3.0),
        stderr_sink_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._config = config
        self._environment = environment
        self._transport_factory = transport_factory
        self._session_factory: SessionFactory = session_factory or _sdk_session_factory
        self._clock = clock
        self._retry_delays = tuple(retry_delays)
        # A factory, not an instance: every connect attempt needs a fresh
        # handle, because teardown closes the previous one (lazy reconnect).
        self._stderr_sink_factory = stderr_sink_factory
        self._state: McpConnectionState = "connecting"
        self._error: str | None = None
        self._stack: AsyncExitStack | None = None
        self._session: Any = None
        self._stderr_sink: Any = None
        self.tools: tuple[McpToolInfo, ...] = ()
        self.instructions: str | None = None

    @property
    def name(self) -> str:
        return self._config.name

    @property
    def state(self) -> McpConnectionState:
        return self._state

    @property
    def error(self) -> str | None:
        return self._error

    async def connect(self) -> bool:
        """Connect once, retrying transient failures; ``False`` on failure."""
        if self._state == "closed":
            raise McpToolUnavailable(f'MCP server "{self._config.name}" is closed')
        self._state = "connecting"
        # pi retries HTTP servers only (runtime.ts:344): a stdio spawn failure
        # is deterministic, so retrying would just delay the error report.
        retries = self._retry_delays if self._config.server_type == "http" else ()
        for attempt in range(len(retries) + 1):
            error = await self._connect_once()
            if error is None:
                return True
            if _needs_auth(error):
                self._state = "needs-auth"
                self._error = _message(error)
                return False
            if attempt < len(retries) and _is_transient(error):
                await anyio.sleep(retries[attempt])
                continue
            self._state = "failed"
            self._error = _message(error)
            return False
        raise AssertionError("unreachable retry loop exit")

    async def call_tool(
        self,
        tool: str,
        arguments: Mapping[str, Any],
        *,
        on_progress: Callable[[str], None] | None = None,
    ) -> McpToolResultData:
        """Run one tool call, reconnecting first when the connection dropped."""
        if self._state in ("failed", "needs-auth", "closed"):
            raise McpToolUnavailable(self._error or f'MCP server "{self._config.name}" is {self._state}')
        if self._state == "disconnected" and not await self.connect():
            raise McpToolUnavailable(self._error or f'MCP server "{self._config.name}" could not reconnect')
        assert self._session is not None
        holder = _Deadline(self._clock() + self._config.timeout)

        async def on_sdk_progress(progress: float, total: float | None, message: str | None) -> None:
            holder.deadline = self._clock() + self._config.timeout
            if on_progress is not None:
                on_progress(_progress_text(progress, total, message))

        cancelled = anyio.get_cancelled_exc_class()
        try:
            result = await self._call_with_deadline(
                lambda: self._session.call_tool(tool, dict(arguments), progress_callback=on_sdk_progress),
                holder,
            )
        except (Exception, cancelled) as exc:
            # The deadline watchdog and external cancellation pass through;
            # everything else is classified for the model.
            if isinstance(exc, (McpToolUnavailable, cancelled)):
                raise
            if _is_connection_dropped(exc):
                await self._teardown()
                self._state = "disconnected"
                self._error = _message(exc)
                raise McpToolUnavailable(
                    f'MCP server "{self._config.name}" lost the connection: {_message(exc)}'
                ) from exc
            raise McpToolUnavailable(f"MCP tool call failed: {_message(exc)}") from exc
        return _convert_result(result)

    async def close(self) -> None:
        """Tear down transport and session; idempotent."""
        if self._state == "closed":
            return
        await self._teardown()
        self._state = "closed"

    async def _connect_once(self) -> BaseException | None:
        """One connect attempt; returns the failure instead of raising."""
        stack: AsyncExitStack | None = None
        try:
            stack = AsyncExitStack()
            sink = self._stderr_sink_factory() if self._stderr_sink_factory is not None else None
            self._stderr_sink = sink
            factory = self._transport_factory
            if factory is default_transport:
                factory = partial(default_transport, stderr_sink=sink)
            transport = await stack.enter_async_context(factory(self._config, self._environment))
            read, write = transport
            session = await stack.enter_async_context(self._session_factory(read, write))
            result = await session.initialize()
            capabilities = session.get_server_capabilities()
            # Servers without the tools capability (prompts/resources only) do
            # not answer tools/list (pi: runtime.ts:386-387).
            if capabilities is not None and capabilities.tools is not None:
                listing = await session.list_tools()
                self.tools = tuple(
                    McpToolInfo(
                        name=tool.name,
                        description=tool.description or "",
                        title=tool.title,
                        input_schema=dict(tool.inputSchema or {}),
                    )
                    for tool in listing.tools
                )
            else:
                self.tools = ()
            self.instructions = (result.instructions or "").strip() or None
            self._stack = stack
            self._session = session
            self._state = "connected"
            self._error = None
            return None
        except BaseException as exc:
            if stack is not None:
                await self._aclose(stack)
            return exc

    async def _call_with_deadline(self, coro_factory: Callable[[], Any], holder: _Deadline) -> Any:
        box: dict[str, object] = {"result": _MISSING}
        done = anyio.Event()

        async def run() -> None:
            box["result"] = await coro_factory()
            done.set()

        async def watchdog() -> None:
            while not done.is_set():
                remaining = holder.deadline - self._clock()
                if remaining <= 0:
                    # A late response after this cancel is dropped by request
                    # id; that is benign and must not be "fixed".
                    scope.cancel()
                    return
                with anyio.move_on_after(min(remaining, _WATCHDOG_POLL_SECONDS)):
                    await done.wait()

        with anyio.CancelScope() as scope:
            async with anyio.create_task_group() as tg:
                tg.start_soon(watchdog)
                tg.start_soon(run)
        result = box["result"]
        if result is _MISSING:
            raise McpToolUnavailable(f"MCP tool call timed out after {self._config.timeout:g}s")
        return result

    async def _teardown(self) -> None:
        stack, self._stack, self._session = self._stack, None, None
        if stack is not None:
            await self._aclose(stack)
        sink, self._stderr_sink = self._stderr_sink, None
        if sink is not None and hasattr(sink, "close"):
            # The stderr log file handle lives exactly as long as the
            # connection that opened it.
            with suppress(Exception):
                sink.close()

    @staticmethod
    async def _aclose(stack: AsyncExitStack) -> None:
        # Teardown must never raise into the caller: a broken server process is
        # a state problem, not a crash.
        with suppress(BaseException):
            await stack.aclose()


def _sdk_session_factory(read: Any, write: Any) -> Any:
    """Build the SDK ClientSession (itself the async context manager)."""
    return ClientSession(read, write)


def _convert_result(result: Any) -> McpToolResultData:
    """Map the SDK's CallToolResult onto Baldric's content blocks."""
    blocks: list[McpContentBlock] = []
    for item in result.content:
        if isinstance(item, mt.TextContent):
            blocks.append(McpContentBlock(text=item.text))
        elif isinstance(item, mt.ImageContent):
            blocks.append(McpContentBlock(image_data=item.data, image_mime=item.mimeType))
        else:
            blocks.append(McpContentBlock(text=f"[unsupported content block: {item.type}]"))
    if not blocks and result.structuredContent is not None:
        blocks.append(McpContentBlock(text=json.dumps(result.structuredContent)))
    return McpToolResultData(blocks=tuple(blocks), is_error=bool(result.isError))


__all__ = [
    "McpConnectionState",
    "McpContentBlock",
    "McpServerConnection",
    "McpToolInfo",
    "McpToolResultData",
    "McpToolUnavailable",
    "McpTransport",
    "TransportFactory",
    "default_transport",
]
