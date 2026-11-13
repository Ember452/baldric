"""Bundled MCP client extension: boot, trust gate, dynamic registration.

Thin glue over ``baldric.mcp``: the supervisor owns connections, the adapter
owns naming and conversion, and this module only wires them into the session
lifecycle. One instance exists per runtime generation (the session always
stages a fresh runtime), so the handlers below manage exactly one supervisor.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from baldric.mcp.adapter import create_mcp_tool_name, mcp_tool_to_agent_tool
from baldric.mcp.client import McpToolUnavailable
from baldric.runtime.config.paths import BaldricPaths
from baldric.runtime.platform.api import EXTENSION_API_VERSION, ExtensionAPI, ExtensionCapabilities
from baldric.runtime.platform.builtin_registry import BuiltInExtensionContext
from baldric.runtime.providers.auth.credentials import FileCredentialStore, credentials_path
from baldric.runtime.tools.output_accumulator import write_temp_output

if TYPE_CHECKING:
    from collections.abc import Callable

    from baldric.mcp.supervisor import McpSupervisor
    from baldric.runtime.platform.api import ExtensionContext

API_VERSION = EXTENSION_API_VERSION
CAPABILITIES = ExtensionCapabilities(tools=True, hooks=True)


def _default_supervisor_factory(configs: Any, environment: Any, stderr_sink_factory: Any = None) -> Any:
    from baldric.mcp.supervisor import McpSupervisor

    return McpSupervisor(configs, environment=environment, stderr_sink_factory=stderr_sink_factory)


# Module-level so tests can inject a fake supervisor without the SDK.
_supervisor_factory: Callable[..., Any] = _default_supervisor_factory


def _mcp_output_saver(full_text: str, suffix: str) -> str:
    """Save full MCP tool output with the house temp-file convention."""
    return write_temp_output(full_text, prefix="baldric-mcp-", suffix=suffix)


class _McpExtension:
    """One generation's MCP state: supervisor, registrations, notifications."""

    def __init__(self, api: ExtensionAPI, context: BuiltInExtensionContext) -> None:
        self._api = api
        self._context = context
        self._supervisor: McpSupervisor | None = None
        self._shut_down = False
        self._admitted = False
        self._configs: tuple[Any, ...] = ()
        # tool name -> owning server name; registration order = sync order.
        self._registered: dict[str, str] = {}
        self._registered_section: str | None = None

    def register_handlers(self) -> None:
        self._api.on("session_start", self.on_session_start)
        self._api.on("session_shutdown", self.on_session_shutdown)
        self._api.on("input", self.on_input)
        self._api.register_command(
            "mcp",
            self.mcp_command,
            description="List and manage MCP servers.",
            usage="/mcp [on|off|restart] <name>",
        )

    async def on_session_start(self, event: object, context: ExtensionContext) -> None:
        if self._supervisor is not None and not self._shut_down:
            self._sync()
            return
        configs = self._load_configs(context)
        if not configs:
            return
        self._configs = configs
        self._supervisor = _supervisor_factory(
            configs,
            self._context.environment,
            stderr_sink_factory=self._make_stderr_sink,
        )
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

    async def on_input(self, event: object, context: ExtensionContext) -> None:
        """First-turn admission: wait (bounded) for connecting servers once."""
        supervisor = self._supervisor
        if self._admitted or supervisor is None or not supervisor.any_connecting():
            return
        self._admitted = True
        await supervisor.wait_ready(timeout=10.0)

    def _load_configs(self, context: ExtensionContext) -> tuple[Any, ...]:
        from baldric.mcp.config import load_mcp_config

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
        # Disabled servers are included so `/mcp on` can reach them; the
        # supervisor only connects the enabled ones (Task 4 semantics).
        return tuple(result.servers)

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
                # is_taken: two tools whose names sanitize identically must get
                # distinct final names (pi appends the hash suffix), not a
                # silent first-wins drop.
                name = create_mcp_tool_name(server, info.name, is_taken=self._registered.__contains__)
                if name in self._registered:
                    continue
                self._registered[name] = server
                self._api.register_tool(
                    mcp_tool_to_agent_tool(
                        server,
                        info,
                        self._caller(server, info.name),
                        output_saver=_mcp_output_saver,
                        name=name,
                    )
                )
        for name, server in list(self._registered.items()):
            if not connected.get(server, False):
                del self._registered[name]
                self._api.unregister_tool(name)
        self._sync_section()

    def _sync_section(self) -> None:
        """Refresh the `MCP servers` prompt section when its body changed.

        The section upserts per title, and the body only changes when a state
        transition changed the listing; every real change rebuilds the system
        prompt and invalidates the provider prefix cache, so identical bodies
        must not re-register.
        """
        body = self._section_body()
        if body is None or body == self._registered_section:
            return
        self._registered_section = body
        self._api.add_prompt_section("MCP servers", body)
        self._api.refresh_system_prompt()

    def _section_body(self) -> str | None:
        supervisor = self._supervisor
        if supervisor is None or not self._configs:
            return None
        states = {status.name: status for status in supervisor.statuses()}
        lines: list[str] = []
        for config in self._configs:
            if not config.enabled:
                continue
            count = states[config.name].tool_count if config.name in states else 0
            line = f"- {config.name} ({config.server_type}, {count} tools)"
            detail = _first_line(config.description)
            if detail is None:
                detail = _first_line(supervisor.instructions(config.name))
            if detail is not None:
                line = f"{line}: {detail}"
            lines.append(line[:200])
        return "\n".join(lines)[:1200]

    def mcp_command(self, args: str, command_context: Any) -> str | None:
        supervisor = self._supervisor
        if supervisor is None:
            return "mcp: no servers configured"
        parts = args.split()
        verb = parts[0] if parts else ""
        name = parts[1] if len(parts) > 1 else ""
        if not verb:
            return self._listing(supervisor)
        if verb in ("on", "off", "restart"):
            if not name:
                return f"usage: /mcp {verb} <name>"
            return self._schedule_toggle(supervisor, verb, name, command_context.api)
        return "usage: /mcp [on|off|restart] <name>"

    def _listing(self, supervisor: McpSupervisor) -> str:
        transports = {config.name: config.server_type for config in self._configs}
        lines: list[str] = []
        for status in supervisor.statuses():
            transport = transports.get(status.name, "stdio")
            line = f"{status.name}  {status.state}  {transport}  {status.tool_count} tools"
            if status.error:
                line += f": {status.error.splitlines()[0]}"
            lines.append(line)
        return "\n".join(lines) or "no servers configured"

    def _schedule_toggle(self, supervisor: McpSupervisor, verb: str, name: str, api: ExtensionAPI) -> str:
        stored = {config.name: config for config in self._configs}
        if name not in stored:
            return f'mcp: unknown server "{name}"'
        if verb == "restart":
            fresh = self._fresh_config(api, name)
            if fresh is None:
                return f'mcp: unknown server "{name}"'
            asyncio.get_running_loop().create_task(supervisor.restart(name, fresh))
            return f"mcp: restarting {name}"
        # Validate before mutating the file: a corrupt or untrusted config must
        # not be rewritten on the way to an error message.
        fresh = self._fresh_config(api, name)
        if fresh is None:
            return f'mcp: unknown server "{name}"'
        source = fresh.source or stored[name].source
        if source is None:
            return f"mcp: cannot persist {name}: no source file"
        from baldric.mcp.config import set_server_enabled

        set_server_enabled(source, name, verb == "on")
        if verb == "on":
            asyncio.get_running_loop().create_task(
                supervisor.set_enabled(name, True, replace(fresh, enabled=True))
            )
            return f"mcp: enabling {name}"
        asyncio.get_running_loop().create_task(supervisor.set_enabled(name, False, None))
        return f"mcp: disabling {name}"

    def _fresh_config(self, api: ExtensionAPI, name: str) -> Any | None:
        from baldric.mcp.config import load_mcp_config

        context = api.context
        user_path = self._context.paths.user_mcp_config_path
        project_path = (
            self._context.paths.project_mcp_config_path(context.cwd) if context.project_trusted else None
        )
        result = load_mcp_config(user_path, project_path, self._context.environment)
        return next((server for server in result.servers if server.name == name), None)

    def _make_stderr_sink(self, config: Any) -> Any:
        """Open the per-server stderr log (`~/.baldric/logs/mcp/<server>.log`).

        The connection closes the handle when its transport goes away; http
        servers have no stderr and never ask for a sink.
        """
        log_dir = self._context.paths.logs_dir / "mcp"
        log_dir.mkdir(parents=True, exist_ok=True)
        return (log_dir / f"{config.name}.log").open("a", encoding="utf-8")

    def _caller(self, server: str, tool: str) -> Callable[..., Any]:
        async def call(arguments: dict[str, Any], *, on_progress: Any = None) -> Any:
            supervisor = self._supervisor
            if supervisor is None:
                # Retire/shutdown window: a registered tool outlives its
                # supervisor. Report it the same way any unavailable call is.
                raise McpToolUnavailable(f'MCP server "{server}" is no longer available')
            return await supervisor.call_tool(server, tool, arguments, on_progress=on_progress)

        return call


def _first_line(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return value.strip().splitlines()[0]


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
