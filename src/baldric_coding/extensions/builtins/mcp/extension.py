"""Bundled MCP client extension: boot, trust gate, dynamic registration.

Thin glue over ``baldric_mcp``: the supervisor owns connections, the adapter
owns naming and conversion, and this module only wires them into the session
lifecycle. One instance exists per runtime generation (the session always
stages a fresh runtime), so the handlers below manage exactly one supervisor.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from baldric_coding.auth.credentials import FileCredentialStore, credentials_path
from baldric_coding.config.paths import BaldricPaths
from baldric_coding.extensions.api import EXTENSION_API_VERSION, ExtensionAPI, ExtensionCapabilities
from baldric_coding.extensions.builtin_registry import BuiltInExtensionContext
from baldric_mcp.adapter import create_mcp_tool_name, mcp_tool_to_agent_tool

if TYPE_CHECKING:
    from collections.abc import Callable

    from baldric_coding.extensions.api import ExtensionContext
    from baldric_mcp.supervisor import McpSupervisor

API_VERSION = EXTENSION_API_VERSION
CAPABILITIES = ExtensionCapabilities(tools=True, hooks=True)


def _default_supervisor_factory(configs: Any, environment: Any) -> Any:
    from baldric_mcp.supervisor import McpSupervisor

    return McpSupervisor(configs, environment=environment)


# Module-level so tests can inject a fake supervisor without the SDK.
_supervisor_factory: Callable[[Any, Any], Any] = _default_supervisor_factory


class _McpExtension:
    """One generation's MCP state: supervisor, registrations, notifications."""

    def __init__(self, api: ExtensionAPI, context: BuiltInExtensionContext) -> None:
        self._api = api
        self._context = context
        self._supervisor: McpSupervisor | None = None
        self._shut_down = False
        # tool name -> owning server name; registration order = sync order.
        self._registered: dict[str, str] = {}

    def register_handlers(self) -> None:
        self._api.on("session_start", self.on_session_start)
        self._api.on("session_shutdown", self.on_session_shutdown)

    async def on_session_start(self, event: object, context: ExtensionContext) -> None:
        if self._supervisor is not None and not self._shut_down:
            self._sync()
            return
        configs = self._load_configs(context)
        if not configs:
            return
        self._supervisor = _supervisor_factory(configs, self._context.environment)
        self._shut_down = False
        self._supervisor.on_change(self._sync)
        # Non-blocking boot: session_start must not wait on server connects;
        # the first user prompt waits instead (the input hook, Task 8).
        asyncio.get_running_loop().create_task(self._supervisor.start())

    async def on_session_shutdown(self, event: object, context: ExtensionContext) -> None:
        # Every shutdown reason precedes this generation's retirement, so the
        # supervisor is always closed; keeping connections would orphan the
        # server processes (corrected Task 0 Step 2b matrix).
        if self._supervisor is None or self._shut_down:
            return
        await self._supervisor.shutdown()
        self._shut_down = True

    def _load_configs(self, context: ExtensionContext) -> tuple[Any, ...]:
        from baldric_mcp.config import load_mcp_config

        user_path = self._context.paths.user_mcp_config_path
        configured_project_path = self._context.paths.project_mcp_config_path(context.cwd)
        project_path: Path | None = configured_project_path
        if not context.project_trusted:
            if configured_project_path.exists():
                self._api.notify(f"mcp: {configured_project_path} ignored: project not trusted", "warning")
            project_path = None
        result = load_mcp_config(user_path, project_path, self._context.environment)
        for diagnostic in result.diagnostics:
            name = f" [{diagnostic.name}]" if diagnostic.name else ""
            self._api.notify(f"mcp: {diagnostic.path}{name}: {diagnostic.message}", "warning")
        return tuple(server for server in result.servers if server.enabled)

    def _sync(self) -> None:
        """Bring registrations in step with the supervisor's server states.

        A no-op when nothing visible changed: registrations are keyed by the
        final tool name, so already-registered tools are skipped and withdrawn
        tools leave the map without touching the others.
        """
        supervisor = self._supervisor
        if supervisor is None:
            return
        connected: dict[str, bool] = {
            status.name: status.state == "connected" for status in supervisor.statuses()
        }
        for server, is_connected in connected.items():
            if not is_connected:
                continue
            for info in supervisor.tool_names(server):
                name = create_mcp_tool_name(server, info.name)
                if name in self._registered:
                    continue
                self._registered[name] = server
                self._api.register_tool(mcp_tool_to_agent_tool(server, info, self._caller(server, info.name)))
        for name, server in list(self._registered.items()):
            if not connected.get(server, False):
                del self._registered[name]
                self._api.unregister_tool(name)

    def _caller(self, server: str, tool: str) -> Callable[..., Any]:
        async def call(arguments: dict[str, Any], *, on_progress: Any = None) -> Any:
            supervisor = self._supervisor
            assert supervisor is not None  # a registered tool implies a live supervisor
            return await supervisor.call_tool(server, tool, arguments, on_progress=on_progress)

        return call


def setup(api: ExtensionAPI, context: BuiltInExtensionContext | None = None) -> None:
    """Wire the MCP client into the session lifecycle (sync, per generation)."""
    dependencies = context or BuiltInExtensionContext(
        paths=BaldricPaths(),
        credential_store=FileCredentialStore(credentials_path(BaldricPaths())),
        environment=dict(os.environ),
    )
    state = _McpExtension(api, dependencies)
    state.register_handlers()


__all__ = ["API_VERSION", "CAPABILITIES", "setup"]
