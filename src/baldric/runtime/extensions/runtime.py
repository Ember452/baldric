"""Extension runtime: hook dispatch, tool wrapping, and session binding."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from inspect import isawaitable
from pathlib import Path
from time import time_ns
from typing import Literal, Protocol, cast
from uuid import uuid4

import httpx

import baldric.runtime.extensions.builtin_registry as built_in_extension_registry
from baldric.agent.events import AgentEvent, AgentStartEvent
from baldric.agent.events import TurnEndEvent as AgentTurnEndEvent
from baldric.agent.events import TurnStartEvent as AgentTurnStartEvent
from baldric.agent.tool_calls import BeforeToolCall
from baldric.ai.hooks import (
    ContextHook,
    ProviderContext,
    ProviderHooks,
    StreamEventHook,
)
from baldric.protocol.messages import AgentMessage, TextContent
from baldric.protocol.provider import (
    HeadersHook,
    HookContext,
    PayloadHook,
    ResponseHook,
)
from baldric.protocol.tools import (
    AgentTool,
    AgentToolResult,
    ToolCancellationToken,
    ToolUpdateCallback,
)
from baldric.protocol.types import JSONValue
from baldric.runtime.auth.credentials import (
    CredentialStore,
    FileCredentialStore,
    credentials_path,
)
from baldric.runtime.backends.contracts import LocalBackend, LocalBackendRegistry
from baldric.runtime.commands.base import handled_result, message_outcome
from baldric.runtime.commands.registry import (
    CommandContext,
    CommandRegistry,
    CommandResult,
    SlashCommand,
    create_default_command_registry,
)
from baldric.runtime.config.paths import BaldricPaths
from baldric.runtime.context.resources import BaldricResourcePaths, ResourceDiagnostic
from baldric.runtime.context.system_prompt import PromptSection
from baldric.runtime.extensions.api import (
    AGENT_EVENT_TYPES,
    AGENT_EVENT_WILDCARD,
    EVENT_NAME_ALIASES,
    EXTENSION_API_VERSION,
    LIFECYCLE_EVENT_TYPES,
    PROVIDER_EVENT_TYPES,
    CompactionSummaryResult,
    CustomEntryView,
    CustomMessageView,
    EntryRenderer,
    ExtensionAPI,
    ExtensionCommandContext,
    ExtensionCommandHandler,
    ExtensionContext,
    ExtensionError,
    ExtensionGeneration,
    ExtensionHandler,
    InputEvent,
    InputHookResult,
    MarkdownRenderContext,
    MarkdownTransformer,
    MessageRenderer,
    MessageRenderOptions,
    NullUiBridge,
    ProviderContextEvent,
    ProviderHeadersEvent,
    ProviderRequestEvent,
    ProviderResponseEvent,
    ProviderStreamEvent,
    RegisteredExtension,
    SessionBeforeCompactEvent,
    SessionLifecycleReason,
    SessionShutdownEvent,
    SessionStartEvent,
    ToolCallHookEvent,
    ToolCallHookResult,
    ToolCallResolver,
    ToolResultHookEvent,
    ToolResultHookResult,
    ToolResultResolver,
    TurnEndEvent,
    TurnStartEvent,
    UiBridge,
    UserBashEvent,
    UserBashResult,
)
from baldric.runtime.extensions.builtin_registry import (
    BuiltInExtension,
    BuiltInExtensionContext,
)
from baldric.runtime.extensions.loader import (
    ExtensionSourceMetadata,
    LoadedExtension,
    load_extensions,
    unload_extension_modules,
)
from baldric.runtime.extensions.provider_registry import (
    DynamicProviderRegistry,
    ProviderRegistryCloseResult,
)
from baldric.runtime.extensions.providers import CredentialReader, DynamicProvider
from baldric.runtime.providers.config import ProviderConfig
from baldric.runtime.trust.policy import (
    ExtensionTrustResult,
    ProjectTrustEvent,
    ProjectTrustResolution,
)

# Host callback that delivers a message through the frontend's serialized run
# path when the session is idle. Carries the same presentation metadata as a
# queued message so custom messages render correctly whether they trigger a new
# turn or are injected into a running one.
TurnRequestedCallback = Callable[[str, "str | None", "dict[str, JSONValue] | None"], None]


class BoundModelChoice(Protocol):
    """Provider/model identifiers exposed by a bound session."""

    @property
    def provider_name(self) -> str: ...

    @property
    def model(self) -> str: ...


class BoundSession(Protocol):
    """The slice of `CodingSession` the extension runtime binds to."""

    @property
    def cwd(self) -> Path: ...

    @property
    def model(self) -> str: ...

    @property
    def provider_name(self) -> str: ...

    @property
    def available_providers(self) -> tuple[str, ...]: ...

    @property
    def available_model_choices(self) -> tuple[BoundModelChoice, ...]: ...

    @property
    def inference_provider(self) -> str | None: ...

    @property
    def inference_provider_mode(self) -> str: ...

    @property
    def session_id(self) -> str | None: ...

    @property
    def session_name(self) -> str | None: ...

    @property
    def thinking_level(self) -> str: ...

    @property
    def system_prompt(self) -> str: ...

    @property
    def shell(self) -> str: ...

    @property
    def shell_command_prefix(self) -> str | None: ...

    @property
    def project_trust_resolution(self) -> ProjectTrustResolution | None: ...

    @property
    def before_tool_call(self) -> BeforeToolCall | None: ...

    @property
    def is_running(self) -> bool: ...

    @property
    def messages(self) -> tuple[AgentMessage, ...]: ...

    def queue_steering_message(
        self,
        content: str,
        *,
        custom_type: str | None = None,
        details: dict[str, JSONValue] | None = None,
    ) -> None: ...

    def queue_follow_up_message(
        self,
        content: str,
        *,
        custom_type: str | None = None,
        details: dict[str, JSONValue] | None = None,
    ) -> None: ...

    async def append_custom_entry(self, namespace: str, data: dict[str, JSONValue]) -> None: ...

    async def set_label(self, target_id: str, label: str | None) -> object: ...

    def set_inference_provider(self, route: str | None) -> str: ...

    def set_model(self, model: str) -> None: ...

    async def notify_model_selected(self, previous_model: str | None) -> None: ...

    async def set_thinking_level(self, level: str) -> str: ...

    def refresh_system_prompt(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ExtensionCommand:
    """A slash command registered by an extension."""

    extension: str
    source_id: str
    name: str
    description: str
    usage: str
    aliases: tuple[str, ...]
    handler: ExtensionCommandHandler


@dataclass(frozen=True, slots=True)
class RegisteredExtensionTool:
    """A tool registered by an extension."""

    extension: str
    source_id: str
    tool: AgentTool


@dataclass(frozen=True, slots=True)
class InputHookOutcome:
    """Combined outcome of running all `input` hooks over prompt text."""

    handled: bool
    text: str
    message: str | None = None


@dataclass(frozen=True, slots=True)
class ExtensionInfo:
    """User-facing metadata for one loaded extension."""

    name: str
    path: Path | None
    scope: Literal["project", "user", "explicit", "built-in"]
    status: Literal["loaded"] = "loaded"


class ExtensionRuntime:
    """Owns loaded extensions and dispatches events between them and a session.

    Each runtime belongs to one prepared session snapshot. Reload and
    destination replacement stage a fresh runtime, then retire the prior
    generation only after preparation succeeds. This prevents project extension
    registrations from crossing cwd trust boundaries.
    """

    def __init__(
        self,
        *,
        ui: UiBridge | None = None,
        durable_providers: Sequence[ProviderConfig] = (),
        credentials: CredentialReader | None = None,
        environment: Mapping[str, str] | None = None,
        built_in_extensions: Sequence[BuiltInExtension] | None = None,
        paths: BaldricPaths | None = None,
        built_in_credentials: CredentialStore | None = None,
        built_in_http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._generation = ExtensionGeneration()
        self._built_in_extensions = tuple(
            built_in_extension_registry.BUILT_IN_EXTENSIONS
            if built_in_extensions is None
            else built_in_extensions
        )
        self._built_ins_loaded = False
        self._durable_providers = tuple(durable_providers)
        self._provider_credentials = credentials
        self._provider_environment = environment
        built_in_paths = paths or BaldricPaths()
        resolved_built_in_credentials: CredentialStore = (
            built_in_credentials
            if built_in_credentials is not None
            else (
                cast(CredentialStore, credentials)
                if credentials is not None
                and all(callable(getattr(credentials, name, None)) for name in ("set", "delete", "names"))
                else FileCredentialStore(credentials_path(built_in_paths))
            )
        )
        self._built_in_context = BuiltInExtensionContext(
            paths=built_in_paths,
            credential_store=resolved_built_in_credentials,
            environment=dict(environment) if environment is not None else dict(os.environ),
            http_client=built_in_http_client,
        )
        self._provider_registry = DynamicProviderRegistry(
            self._durable_providers,
            generation_id=self._generation.id,
            credentials=credentials,
            environment=environment,
        )
        self._local_backend_registry = LocalBackendRegistry(
            self._provider_registry,
            generation_id=self._generation.id,
        )
        # Modules imported by this runtime's own loads, recorded so ``retire``
        # can remove exactly its generation from ``sys.modules``.
        self._loaded_module_names: list[str] = []
        self._extensions: list[RegisteredExtension] = []
        # Extensions whose ``setup`` raised after registering handlers. They are
        # not active, but they stay here until the next ``session_shutdown``
        # reaches the handlers they installed before failing (see retire path).
        self._failed_extensions: list[RegisteredExtension] = []
        self._tools: dict[str, RegisteredExtensionTool] = {}
        self._commands: dict[str, ExtensionCommand] = {}
        self._prompt_guidelines: list[tuple[str, str, str]] = []
        self._prompt_sections: list[tuple[str, str, PromptSection]] = []
        self._message_renderers: dict[str, tuple[str, str, MessageRenderer]] = {}
        self._entry_renderers: dict[str, tuple[str, str, EntryRenderer]] = {}
        self._tool_call_resolvers: list[tuple[str, str, ToolCallResolver]] = []
        self._tool_result_resolvers: list[tuple[str, str, ToolResultResolver]] = []
        self._markdown_transformers: list[tuple[str, str, MarkdownTransformer, frozenset[str]]] = []
        self._renderer_failures_reported: set[str] = set()
        self._load_diagnostics: list[ResourceDiagnostic] = []
        self._runtime_diagnostics: list[ResourceDiagnostic] = []
        self._project_extensions_dir: Path | None = None
        self._user_extensions_dir: Path = BaldricPaths().home / "extensions"
        # Keep constructor-provided paths visible until ``load`` installs the
        # authoritative resource-path snapshot.
        self._paths: BaldricPaths = paths or BaldricPaths()
        self._session: BoundSession | None = None
        # The session's materialized tool list, bound by ``load`` so extension
        # registrations reach the harness per run instead of at next load.
        self._live_tools: list[AgentTool] | None = None
        self._live_allowed: frozenset[str] | None = None
        # name -> the hook-wrapped object appended to ``_live_tools``. The
        # registry keeps the raw tool (compose_tools wraps at the next load);
        # the live list must carry the same wrapped shape compose_tools
        # produces, or tool_call/tool_result hooks would bypass dynamic tools.
        self._live_wrapped: dict[str, AgentTool] = {}
        # The unfiltered materialized list; ``set_active_tools`` rewrites the
        # bound list from it so disabling is reversible without unregistering.
        self._live_tools_all: list[AgentTool] | None = None
        # ``None`` means "every tool is active"; a set restricts to exactly those
        # names, including tools registered after the restriction was set, so a
        # restricted mode cannot be widened by a later registration.
        self._active_tool_names: set[str] | None = None
        self._ui: UiBridge = ui or NullUiBridge()
        self._turn_requested: TurnRequestedCallback | None = None
        self._harness_unsubscribe: Callable[[], None] | None = None
        self._extension_turn_index = 0

    # -- loading -----------------------------------------------------------

    def load(
        self,
        paths: BaldricResourcePaths,
        *,
        extra_paths: Sequence[Path] = (),
        include_resource_dirs: bool = True,
        include_project_dir: bool = False,
        include_user_dir: bool = True,
    ) -> None:
        """Load built-ins, then discover extensions and run isolated setup."""
        self._paths = paths.paths or BaldricPaths(
            home=paths.root,
            agents_home=paths.agents_root or Path.home() / ".agents",
        )
        self._load_built_ins()
        result = load_extensions(
            paths,
            extra_paths=extra_paths,
            include_resource_dirs=include_resource_dirs,
            include_project_dir=include_project_dir,
            include_user_dir=include_user_dir,
        )
        self._load_diagnostics.extend(result.diagnostics)
        self._loaded_module_names.extend(
            extension.module_name for extension in result.extensions if extension.module_name is not None
        )
        self._project_extensions_dir = (
            paths.cwd / ".baldric" / "extensions" if paths.cwd is not None else None
        )
        self._user_extensions_dir = paths.root / "extensions"
        for extension in result.extensions:
            self._setup_extension(extension)

    def _load_built_ins(self) -> None:
        """Load each trusted declaration once, before filesystem sources."""
        if self._built_ins_loaded:
            return
        self._built_ins_loaded = True
        for declaration in self._built_in_extensions:
            setup = declaration.setup
            if declaration.setup_with_context is not None:

                def setup_with_runtime_context(
                    api: ExtensionAPI,
                    declaration: BuiltInExtension = declaration,
                ) -> None:
                    assert declaration.setup_with_context is not None
                    declaration.setup_with_context(api, self._built_in_context)

                setup = setup_with_runtime_context
            self._setup_extension(
                LoadedExtension(
                    name=declaration.name,
                    path=None,
                    source_id=declaration.source_id,
                    setup=setup,
                    source="built-in",
                    hidden=declaration.hidden,
                )
            )

    @property
    def active(self) -> bool:
        """Return whether this runtime generation still owns live registrations."""
        return self._generation.active

    def retire(self) -> None:
        """Invalidate this generation and release all source-owned work."""
        if not self._generation.active:
            return
        # Replacement callers clear host UI before a successor uses the shared
        # bridge; clearing here could erase that successor's freshly mounted UI.
        # Provider retirement synchronously detaches every layer and requests
        # cancellation of generation-owned provider and backend work.
        self._local_backend_registry.retire()
        self._provider_registry.retire()
        self._generation.invalidate()
        if self._harness_unsubscribe is not None:
            self._harness_unsubscribe()
            self._harness_unsubscribe = None
        self._extensions.clear()
        self._failed_extensions.clear()
        self._tools.clear()
        self._commands.clear()
        self._prompt_guidelines.clear()
        self._prompt_sections.clear()
        self._message_renderers.clear()
        self._entry_renderers.clear()
        self._tool_call_resolvers.clear()
        self._tool_result_resolvers.clear()
        self._markdown_transformers.clear()
        self._renderer_failures_reported.clear()
        self._live_tools = None
        self._live_allowed = None
        self._live_wrapped.clear()
        self._turn_requested = None
        self._session = None
        self._unload_loaded_modules()

    async def aclose(self) -> ProviderRegistryCloseResult:
        """Retire this generation and report drain or bounded containment."""
        self.retire()
        try:
            _, result = await asyncio.gather(
                self._local_backend_registry.aclose(),
                self._provider_registry.aclose(),
            )
            return result
        finally:
            self._generation.invalidate()
            if self._harness_unsubscribe is not None:
                self._harness_unsubscribe()
                self._harness_unsubscribe = None

    def _unload_loaded_modules(self) -> None:
        """Remove exactly the extension modules this runtime imported."""
        if not self._loaded_module_names:
            return
        unload_extension_modules(tuple(self._loaded_module_names))
        self._loaded_module_names.clear()

    def _setup_extension(self, extension: LoadedExtension) -> None:
        source_id = extension.source_id
        if extension.api_version != EXTENSION_API_VERSION:
            self._load_diagnostics.append(
                ResourceDiagnostic(
                    kind="extension",
                    name=extension.name,
                    path=extension.path,
                    message=(
                        f"extension declares API_VERSION {extension.api_version}, but this host"
                        f" implements extension API version {EXTENSION_API_VERSION}; refusing to load it"
                    ),
                    severity="error",
                )
            )
            return
        if self._extension_by_source(source_id) is not None:
            self._load_diagnostics.append(
                ResourceDiagnostic(
                    kind="extension",
                    name=extension.name,
                    path=extension.path,
                    message="duplicate extension source ignored (first-loaded wins)",
                )
            )
            return
        api = ExtensionAPI(
            self,
            extension.name,
            self._generation,
            source_id=source_id,
        )
        registered = RegisteredExtension(
            name=extension.name,
            source_id=source_id,
            path=extension.path,
            api=api,
            source=extension.source,
            hidden=extension.hidden,
            api_version=extension.api_version,
            capabilities=extension.capabilities,
        )
        self._extensions.append(registered)
        try:
            extension.setup(api)
        except Exception as exc:  # noqa: BLE001 - extensions are an isolation boundary
            # A failed setup may already have started tasks, timers, or threads
            # and may have registered `session_shutdown` handlers before raising.
            # Keep the registration in a shutdown-only roster so the host's
            # awaited `session_shutdown` (the real reload/quit path) reaches
            # those handlers before retirement drops the extension, instead of
            # silently orphaning its resources.
            self._extensions.remove(registered)
            self._remove_registrations(source_id)
            self._failed_extensions.append(registered)
            self._load_diagnostics.append(
                ResourceDiagnostic(
                    kind="extension",
                    name=extension.name,
                    path=extension.path,
                    message=(
                        f"built-in setup failed: {exc!r}"
                        if extension.source == "built-in"
                        else f"setup failed: {exc!r}"
                    ),
                    severity="error",
                )
            )

    def _remove_registrations(self, source_id: str) -> None:
        removed_names = [
            name for name, registration in self._tools.items() if registration.source_id == source_id
        ]
        self._tools = {
            name: registration
            for name, registration in self._tools.items()
            if registration.source_id != source_id
        }
        self._drop_live_tools(
            [self._live_wrapped.pop(name) for name in removed_names if name in self._live_wrapped]
        )
        self._commands = {
            name: command for name, command in self._commands.items() if command.source_id != source_id
        }
        self._prompt_guidelines = [
            (owner, extension, guideline)
            for owner, extension, guideline in self._prompt_guidelines
            if owner != source_id
        ]
        self._prompt_sections = [
            (owner, extension, section)
            for owner, extension, section in self._prompt_sections
            if owner != source_id
        ]
        self._message_renderers = {
            custom_type: registration
            for custom_type, registration in self._message_renderers.items()
            if registration[0] != source_id
        }
        self._entry_renderers = {
            custom_type: registration
            for custom_type, registration in self._entry_renderers.items()
            if registration[0] != source_id
        }
        self._tool_call_resolvers = [r for r in self._tool_call_resolvers if r[0] != source_id]
        self._tool_result_resolvers = [r for r in self._tool_result_resolvers if r[0] != source_id]
        self._markdown_transformers = [t for t in self._markdown_transformers if t[0] != source_id]
        self._provider_registry.unregister_source(source_id)
        self._local_backend_registry.unregister_source(source_id)

    # -- registration (called through ExtensionAPI) -------------------------

    def register_provider(self, source_id: str, provider: DynamicProvider) -> None:
        """Register or atomically replace one exact extension source layer."""
        self._provider_registry.register(source_id, provider)

    def update_provider(self, source_id: str, provider: DynamicProvider) -> bool:
        """Publish a provider snapshot without invalidating paired backends."""
        return self._provider_registry.update(source_id, provider)

    def register_local_backend(self, source_id: str, backend: LocalBackend) -> None:
        """Register a backend against its exact source-owned provider layer."""
        self._local_backend_registry.register(source_id, backend)

    def register_tool(self, source_id: str, extension_name: str, tool: AgentTool) -> None:
        """Register an extension tool; first registration per name wins."""
        existing = self._tools.get(tool.name)
        if existing is not None:
            self._load_diagnostics.append(
                ResourceDiagnostic(
                    kind="extension",
                    name=extension_name,
                    message=(
                        f"tool `{tool.name}` already registered by extension"
                        f" `{existing.extension}`; ignoring duplicate"
                    ),
                )
            )
            return
        if self._live_allowed is not None and tool.name not in self._live_allowed:
            self._load_diagnostics.append(
                ResourceDiagnostic(
                    kind="extension",
                    name=extension_name,
                    message=f"tool `{tool.name}` is not in allowed_tool_names; ignoring",
                )
            )
            return
        self._tools[tool.name] = RegisteredExtensionTool(
            extension=extension_name,
            source_id=source_id,
            tool=tool,
        )
        if self._live_tools is not None:
            wrapped = self._wrap_tool(tool)
            self._live_wrapped[tool.name] = wrapped
            if self._live_tools_all is not None:
                self._live_tools_all.append(wrapped)
            self._apply_live_tool_filter()

    def unregister_tool(self, source_id: str, extension_name: str, name: str) -> None:
        """Remove this extension's tool registration; a no-op when absent.

        Only the extension that registered the name may withdraw it, and the
        same object is removed from the bound live list so the next run stops
        offering the tool.
        """
        registered = self._tools.get(name)
        if registered is None or registered.source_id != source_id:
            return
        del self._tools[name]
        wrapped = self._live_wrapped.pop(name, None)
        self._drop_live_tools([wrapped] if wrapped is not None else [])

    def register_command(
        self,
        source_id: str,
        extension_name: str,
        name: str,
        handler: ExtensionCommandHandler,
        *,
        description: str = "",
        usage: str | None = None,
        aliases: tuple[str, ...] = (),
    ) -> None:
        """Register an extension slash command; first registration wins."""
        normalized = name.strip().removeprefix("/").lower()
        existing = self._commands.get(normalized)
        if existing is not None:
            self._load_diagnostics.append(
                ResourceDiagnostic(
                    kind="extension",
                    name=extension_name,
                    message=(
                        f"command `/{normalized}` already registered by extension"
                        f" `{existing.extension}`; ignoring duplicate"
                    ),
                )
            )
            return
        self._commands[normalized] = ExtensionCommand(
            extension=extension_name,
            source_id=source_id,
            name=normalized,
            description=description,
            usage=usage or f"/{normalized}",
            aliases=aliases,
            handler=handler,
        )

    def register_message_renderer(
        self,
        source_id: str,
        extension_name: str,
        custom_type: str,
        renderer: MessageRenderer,
    ) -> None:
        """Register a custom-message renderer; first registration per type wins."""
        normalized = custom_type.strip()
        if not normalized:
            self._load_diagnostics.append(
                ResourceDiagnostic(
                    kind="extension",
                    name=extension_name,
                    message="empty custom_type for message renderer ignored",
                )
            )
            return
        existing = self._message_renderers.get(normalized)
        if existing is not None:
            self._load_diagnostics.append(
                ResourceDiagnostic(
                    kind="extension",
                    name=extension_name,
                    message=(
                        f"message renderer for `{normalized}` already registered by"
                        f" extension `{existing[1]}`; ignoring duplicate"
                    ),
                )
            )
            return
        self._message_renderers[normalized] = (source_id, extension_name, renderer)

    def register_entry_renderer(
        self,
        source_id: str,
        extension_name: str,
        custom_type: str,
        renderer: EntryRenderer,
    ) -> None:
        """Register a custom-entry renderer; first registration per namespace wins."""
        normalized = custom_type.strip()
        if not normalized:
            self._load_diagnostics.append(
                ResourceDiagnostic(
                    kind="extension",
                    name=extension_name,
                    message="empty custom_type for entry renderer ignored",
                )
            )
            return
        existing = self._entry_renderers.get(normalized)
        if existing is not None:
            self._load_diagnostics.append(
                ResourceDiagnostic(
                    kind="extension",
                    name=extension_name,
                    message=(
                        f"entry renderer for `{normalized}` already registered by"
                        f" extension `{existing[1]}`; ignoring duplicate"
                    ),
                )
            )
            return
        self._entry_renderers[normalized] = (source_id, extension_name, renderer)

    def register_tool_renderer(
        self,
        source_id: str,
        extension_name: str,
        *,
        render_call: ToolCallResolver | None,
        render_result: ToolResultResolver | None,
    ) -> None:
        """Append tool render resolvers in extension load order (Pi's chain)."""
        if render_call is not None:
            self._tool_call_resolvers.append((source_id, extension_name, render_call))
        if render_result is not None:
            self._tool_result_resolvers.append((source_id, extension_name, render_result))

    def register_markdown_transformer(
        self,
        source_id: str,
        extension_name: str,
        transformer: MarkdownTransformer,
        *,
        message_types: tuple[str, ...],
    ) -> None:
        """Append a chained markdown transformer; empty message_types = transcript default."""
        surfaces = frozenset(message_types) or frozenset({"user", "assistant", "assistant-thinking"})
        self._markdown_transformers.append((source_id, extension_name, transformer, surfaces))

    def render_custom_entry(
        self,
        namespace: str,
        data: Mapping[str, JSONValue],
        expanded: bool,
    ) -> str | None:
        """Render a custom entry to markup, or ``None`` to fall back to generic text."""
        registration = self._entry_renderers.get(namespace)
        if registration is None:
            return None
        _, extension_name, renderer = registration
        view = CustomEntryView(namespace=namespace, data=data)
        options = MessageRenderOptions(expanded=expanded)
        event_name = f"entry_renderer:{namespace}"
        markup = self._render_isolated(
            failure_key=namespace,
            extension_label=extension_name,
            event_name=event_name,
            producer=lambda: renderer(view, options),
        )
        if not isinstance(markup, str):
            if namespace not in self._renderer_failures_reported:
                self._renderer_failures_reported.add(namespace)
                self._record_bad_result(extension_name, event_name, markup)
            return None
        return markup

    def render_tool_call_via_resolvers(
        self,
        name: str,
        arguments: Mapping[str, JSONValue],
    ) -> str | None:
        """Resolve a tool-call line through the extension resolver chain.

        Each resolver receives ``next``, which yields the next resolver's result
        (and finally the tool's own ``render_call``). A raising resolver is
        skipped (fail-open), matching the hook-composition contract.
        """

        def base() -> str | None:
            return self.render_tool_call(name, arguments)

        chain: Callable[[], str | None] = base
        for _source_id, _extension_name, resolver in reversed(self._tool_call_resolvers):
            next_call = chain
            chain = self._chain_tool_resolver(resolver, name, next_call, arguments)
        return chain()

    def _chain_tool_resolver(
        self,
        resolver: ToolCallResolver,
        name: str,
        next_call: Callable[[], str | None],
        arguments: Mapping[str, JSONValue],
    ) -> Callable[[], str | None]:
        def wrapped() -> str | None:
            result = self._render_isolated(
                failure_key=name,
                extension_label=f"tool-renderer:{name}",
                event_name=name,
                producer=lambda: resolver(name, next_call),
            )
            return result if isinstance(result, str) else next_call()

        return wrapped

    def render_tool_result_via_resolvers(
        self,
        tool_name: str,
        result: AgentToolResult,
        expanded: bool,
    ) -> str | None:
        """Resolve a tool-result block through the extension resolver chain."""

        def base() -> str | None:
            return self.render_tool_result(tool_name, result, expanded)

        chain: Callable[[], str | None] = base
        for _source_id, _extension_name, resolver in reversed(self._tool_result_resolvers):
            next_call = chain
            chain = self._chain_tool_result_resolver(resolver, tool_name, next_call, result, expanded)
        return chain()

    def _chain_tool_result_resolver(
        self,
        resolver: ToolResultResolver,
        tool_name: str,
        next_call: Callable[[], str | None],
        result: AgentToolResult,
        expanded: bool,
    ) -> Callable[[], str | None]:
        def wrapped() -> str | None:
            rendered = self._render_isolated(
                failure_key=tool_name,
                extension_label=f"tool-renderer:{tool_name}",
                event_name=tool_name,
                producer=lambda: resolver(tool_name, result, expanded, next_call),
            )
            return rendered if isinstance(rendered, str) else next_call()

        return wrapped

    def transform_markdown(
        self,
        markdown: str,
        *,
        message_type: str,
        is_streaming: bool = False,
        available_width: int | None = None,
    ) -> str:
        """Run the chained markdown transformers for one surface (display-only).

        A raising transformer is skipped (fail-open); the markdown produced so
        far continues down the chain. Returns the final markdown.
        """
        current = markdown
        for source_id, extension_name, transformer, surfaces in self._markdown_transformers:
            if message_type not in surfaces:
                continue
            context = MarkdownRenderContext(
                message_type=message_type,
                is_streaming=is_streaming,
                available_width=available_width,
            )
            event_name = f"markdown_transformer:{message_type}"
            transformed = self._render_isolated(
                failure_key=f"markdown:{source_id}:{message_type}",
                extension_label=extension_name,
                event_name=event_name,
                producer=partial(transformer, current, context),
            )
            if not isinstance(transformed, str):
                if transformed is not None:
                    self._record_bad_result(extension_name, event_name, transformed)
                continue
            current = transformed
        return current

    def _render_isolated(
        self,
        *,
        failure_key: str,
        extension_label: str,
        event_name: str,
        producer: Callable[[], object],
    ) -> object | None:
        """Run one registered renderer through the shared isolation boundary.

        A renderer must never crash the frontend: a raise is recorded once per
        ``failure_key`` (render paths re-run on every redraw) and yields ``None``
        so the caller can fall back to its default.
        """
        try:
            return producer()
        except Exception as exc:  # noqa: BLE001 - a renderer must never crash the frontend
            if failure_key not in self._renderer_failures_reported:
                self._renderer_failures_reported.add(failure_key)
                self._record_runtime_failure(extension_label, event_name, exc)
            return None

    def render_custom_message(
        self,
        custom_type: str,
        content: str,
        details: Mapping[str, JSONValue] | None,
        expanded: bool,
    ) -> str | None:
        """Render a custom message to markup, or ``None`` to fall back to raw text.

        Installed into every render path (TUI state, print transcript). A missing
        renderer or a renderer that raises or returns a non-string yields
        ``None`` so the frontend renders the raw ``content`` instead of crashing.
        Failures are diagnosed once per ``custom_type`` (render paths re-run on
        every redraw, which would otherwise grow diagnostics without bound).
        """
        registration = self._message_renderers.get(custom_type)
        if registration is None:
            return None
        _, extension_name, renderer = registration
        view = CustomMessageView(custom_type=custom_type, content=content, details=details)
        options = MessageRenderOptions(expanded=expanded)
        event_name = f"message_renderer:{custom_type}"
        markup = self._render_isolated(
            failure_key=custom_type,
            extension_label=extension_name,
            event_name=event_name,
            producer=lambda: renderer(view, options),
        )
        if not isinstance(markup, str):
            if custom_type not in self._renderer_failures_reported:
                self._renderer_failures_reported.add(custom_type)
                self._record_bad_result(extension_name, event_name, markup)
            return None
        return markup

    def render_tool_call(
        self,
        name: str,
        arguments: Mapping[str, JSONValue],
    ) -> str | None:
        """Render a tool call via its tool's `render_call`, or ``None``.

        Installed into frontends as the tool-call display resolver. A tool
        without a `render_call`, or a renderer that raises or returns a
        non-string, yields ``None`` so the frontend falls back to its
        generic invocation formatting. Failures are diagnosed once per tool
        name (render paths re-run on every redraw).
        """
        registered = self._tools.get(name)
        if registered is None or registered.tool.render_call is None:
            return None
        try:
            line = registered.tool.render_call(arguments)
        except Exception as exc:  # noqa: BLE001 - a renderer must never crash the frontend
            if name not in self._renderer_failures_reported:
                self._renderer_failures_reported.add(name)
                self._record_runtime_failure(registered.extension, f"render_call:{name}", exc)
            return None
        if line is not None and not isinstance(line, str):
            if name not in self._renderer_failures_reported:
                self._renderer_failures_reported.add(name)
                self._record_bad_result(registered.extension, f"render_call:{name}", line)
            return None
        return line

    def render_tool_result(
        self,
        tool_name: str,
        result: AgentToolResult,
        expanded: bool,
    ) -> str | None:
        """Render a named tool's result via `render_result`, or ``None``.

        Installed into frontends as the tool-result display resolver, the
        counterpart of `render_tool_call` for the other end of the row's
        lifecycle. A tool without a `render_result`, or a renderer that raises
        or returns a non-string, yields ``None`` so the frontend falls back to
        its generic result formatting. Failures are diagnosed once per tool
        name (render paths re-run on every redraw).
        """
        registered = self._tools.get(tool_name)
        if registered is None or registered.tool.render_result is None:
            return None
        failure_key = f"render_result:{tool_name}"
        try:
            markup = registered.tool.render_result(result, expanded=expanded)
        except Exception as exc:  # noqa: BLE001 - a renderer must never crash the frontend
            if failure_key not in self._renderer_failures_reported:
                self._renderer_failures_reported.add(failure_key)
                self._record_runtime_failure(registered.extension, f"render_result:{tool_name}", exc)
            return None
        if markup is not None and not isinstance(markup, str):
            if failure_key not in self._renderer_failures_reported:
                self._renderer_failures_reported.add(failure_key)
                self._record_bad_result(registered.extension, f"render_result:{tool_name}", markup)
            return None
        return markup

    def register_prompt_guideline(self, source_id: str, extension_name: str, guideline: str) -> None:
        """Register a standalone system-prompt guideline line."""
        normalized = guideline.strip()
        if not normalized:
            self._load_diagnostics.append(
                ResourceDiagnostic(
                    kind="extension",
                    name=extension_name,
                    message="empty prompt guideline ignored",
                )
            )
            return
        self._prompt_guidelines.append((source_id, extension_name, normalized))

    def register_prompt_section(
        self,
        source_id: str,
        extension_name: str,
        title: str | None,
        body: str,
    ) -> None:
        """Register a free-form system-prompt section."""
        normalized_body = body.strip()
        if not normalized_body:
            self._load_diagnostics.append(
                ResourceDiagnostic(
                    kind="extension",
                    name=extension_name,
                    message="empty prompt section ignored",
                )
            )
            return
        normalized_title = title.strip() if title is not None else None
        if normalized_title == "":
            normalized_title = None
        if normalized_title is not None and any(separator in normalized_title for separator in ("\r", "\n")):
            self._load_diagnostics.append(
                ResourceDiagnostic(
                    kind="extension",
                    name=extension_name,
                    message="prompt section ignored because its title spans multiple lines",
                )
            )
            return
        if normalized_title is not None:
            # Titled sections upsert per source: an extension may refresh its
            # section body as its state changes (e.g. live server listings)
            # without stacking duplicates. Untitled sections keep append
            # semantics, preserving the original free-form behavior.
            self._prompt_sections = [
                entry
                for entry in self._prompt_sections
                if not (entry[0] == source_id and entry[2].title == normalized_title)
            ]
        self._prompt_sections.append(
            (
                source_id,
                extension_name,
                PromptSection(title=normalized_title, body=normalized_body),
            )
        )

    def subscribe(self, source_id: str, event: str, handler: ExtensionHandler) -> None:
        """Subscribe an extension handler to a named event."""
        canonical = EVENT_NAME_ALIASES.get(event, event)
        known = (
            canonical in AGENT_EVENT_TYPES
            or canonical in LIFECYCLE_EVENT_TYPES
            or canonical in PROVIDER_EVENT_TYPES
            or canonical == AGENT_EVENT_WILDCARD
        )
        if not known:
            self._load_diagnostics.append(
                ResourceDiagnostic(
                    kind="extension",
                    name=self._extension_display_name(source_id),
                    message=f"unknown event `{event}`; handler ignored",
                )
            )
            return
        extension = self._extension_by_source(source_id)
        if extension is None:
            raise ExtensionError(f"unknown extension source: {source_id}")
        extension.handlers.setdefault(canonical, []).append(handler)

    # -- provider seams (plan Task A2) ---------------------------------------

    def has_provider_hooks(self) -> bool:
        """Return whether any extension registered a provider-seam handler."""
        return any(next(self._handlers_for(name), None) is not None for name in PROVIDER_EVENT_TYPES)

    def build_provider_hooks(self) -> ProviderHooks:
        """Adapt registered provider-seam handlers onto the AI-layer seams.

        Bridges Baldric's extension events (``context`` / ``before_provider_*`` /
        ``after_provider_response`` / ``provider_stream_event``) onto either the
        provider-boundary seams (``HookableProvider``) or the adapter request
        seams (``RequestHooks``), matching Pi's coding-agent -> ai bridge. Returns
        an empty :class:`ProviderHooks` (``is_empty()``) when nothing is
        registered, so the session can skip wrapping entirely.
        """
        hooks = ProviderHooks()
        context_handlers = [*self._handlers_for("context"), *self._handlers_for("context_with_system")]
        for owner, handler in context_handlers:
            hooks.context.append(self._adapt_context_handler(owner, handler))
        for owner, handler in self._handlers_for("before_provider_headers"):
            hooks.headers.append(self._adapt_headers_handler(owner, handler))
        for owner, handler in self._handlers_for("before_provider_request"):
            hooks.payload.append(self._adapt_payload_handler(owner, handler))
        for owner, handler in self._handlers_for("after_provider_response"):
            hooks.response.append(self._adapt_response_handler(owner, handler))
        for owner, handler in self._handlers_for("provider_stream_event"):
            hooks.stream_event.append(self._adapt_stream_handler(owner, handler))
        return hooks

    async def _invoke_handler(
        self, owner: RegisteredExtension, event_name: str, event: object, handler: ExtensionHandler
    ) -> object:
        """Run one extension handler with the shared isolation boundary.

        This is the single try/except for gated/async lifecycle seams: a handler
        (sync or async) that raises is recorded as a runtime failure and yields
        ``_PROVIDER_HANDLER_FAILED`` so the caller can defer to its fallback.
        Provider seams and ``user_bash`` share it, matching ``ai.hooks._guarded``.
        """
        try:
            return await _resolve(handler(event, self._fresh_context(owner.source_id)))
        except Exception as exc:  # noqa: BLE001 - extensions are an isolation boundary
            self._record_runtime_failure(owner.name, event_name, exc)
            return _PROVIDER_HANDLER_FAILED

    def _adapt_context_handler(self, owner: RegisteredExtension, handler: ExtensionHandler) -> ContextHook:
        async def adapted(request: ProviderContext, _ctx: HookContext) -> ProviderContext | None:
            event = ProviderContextEvent(
                model=request.model,
                system=request.system,
                messages=tuple(request.messages),
                tools=tuple(request.tools),
            )
            result = await self._invoke_handler(owner, "context", event, handler)
            if isinstance(result, ProviderContextEvent):
                return ProviderContext(
                    model=result.model,
                    system=result.system,
                    messages=list(result.messages),
                    tools=list(result.tools),
                    session_id=request.session_id,
                )
            return None

        return adapted

    def _adapt_headers_handler(self, owner: RegisteredExtension, handler: ExtensionHandler) -> HeadersHook:
        async def adapted(headers: dict[str, str], _ctx: HookContext) -> None:
            await self._invoke_handler(
                owner, "before_provider_headers", ProviderHeadersEvent(model="", headers=headers), handler
            )

        return adapted

    def _adapt_payload_handler(self, owner: RegisteredExtension, handler: ExtensionHandler) -> PayloadHook:
        async def adapted(payload: dict[str, JSONValue], ctx: HookContext) -> dict[str, JSONValue] | None:
            result = await self._invoke_handler(
                owner,
                "before_provider_request",
                ProviderRequestEvent(model=ctx.model, payload=payload),
                handler,
            )
            if isinstance(result, ProviderRequestEvent):
                return result.payload
            if isinstance(result, dict):
                return result
            return None

        return adapted

    def _adapt_response_handler(self, owner: RegisteredExtension, handler: ExtensionHandler) -> ResponseHook:
        async def adapted(status: int, headers: dict[str, str], ctx: HookContext) -> None:
            await self._invoke_handler(
                owner,
                "after_provider_response",
                ProviderResponseEvent(model=ctx.model, status=status, headers=headers),
                handler,
            )

        return adapted

    def _adapt_stream_handler(self, owner: RegisteredExtension, handler: ExtensionHandler) -> StreamEventHook:
        async def adapted(event: object, ctx: HookContext) -> None:
            await self._invoke_handler(
                owner, "provider_stream_event", ProviderStreamEvent(model=ctx.model, event=event), handler
            )

        return adapted

    # -- binding -------------------------------------------------------------

    def bind(self, session: BoundSession) -> None:
        """Bind (or re-bind) the runtime to a coding session."""
        self._session = session

    def attach_harness_listener(
        self,
        subscribe: Callable[[Callable[[AgentEvent], Awaitable[None] | None]], Callable[[], None]],
    ) -> None:
        """Subscribe the event fan-out to a harness, replacing any prior one."""
        if self._harness_unsubscribe is not None:
            self._harness_unsubscribe()
        self._harness_unsubscribe = subscribe(self._on_agent_event)

    @property
    def provider_credentials(self) -> CredentialReader | None:
        """Return the read-only credential reader used by dynamic runtimes."""
        return self._provider_credentials

    @property
    def provider_environment(self) -> Mapping[str, str] | None:
        """Return the environment snapshot used by dynamic provider auth."""
        return self._provider_environment

    @property
    def built_in_credentials(self) -> CredentialStore:
        """Return the injected mutable store used by trusted built-ins."""
        return self._built_in_context.credential_store

    @property
    def built_in_http_client(self) -> httpx.AsyncClient | None:
        """Return the externally owned HTTP client used by trusted built-ins."""
        return self._built_in_context.http_client

    def set_ui_bridge(self, ui: UiBridge) -> None:
        """Install the frontend UI bridge (TUI, print-mode fallback, or test)."""
        self._ui = ui

    def clear_ui_components(self) -> None:
        """Ask the host frontend to tear down all extension-owned UI.

        Invoked on the real `/reload` path by ``session/lifecycle.py`` (after
        ``emit_session_shutdown("reload")`` and before ``retire()``), and by
        session replacement flows (resume/new) before ``session_start`` fires,
        so widgets and key interceptors never outlive the world that mounted
        them while handlers keep the chance to re-mount.
        """
        self._ui.clear_components()

    def set_turn_requested_callback(self, callback: TurnRequestedCallback | None) -> None:
        """Install the host callback used to deliver messages while idle.

        The callback receives the message content plus optional custom-message
        metadata and is expected to submit it through the host's serialized run
        path (the TUI uses the same exclusive worker as user submissions, so
        extension turns cannot race user runs).
        """
        self._turn_requested = callback

    @property
    def ui(self) -> UiBridge:
        """Return the active UI bridge."""
        return self._ui

    @property
    def session_view(self) -> BoundSession:
        """Return the bound session, raising if the runtime is unbound."""
        if self._session is None:
            raise ExtensionError(
                "extension API used before the session was bound; "
                "register handlers in setup() and act on events instead"
            )
        return self._session

    @property
    def provider_registry(self) -> DynamicProviderRegistry:
        """Return this staged runtime generation's process-local provider registry."""
        return self._provider_registry

    @property
    def local_backend_registry(self) -> LocalBackendRegistry:
        """Return this staged runtime generation's local-backend registry."""
        return self._local_backend_registry

    async def set_model(self, model: str) -> None:
        """Switch the bound session's model and dispatch ``model_select``."""
        view = self.session_view
        previous = view.model
        view.set_model(model)
        if previous != view.model:
            await view.notify_model_selected(previous)

    @property
    def paths(self) -> BaldricPaths:
        """Return the resolved Baldric filesystem paths for this runtime."""
        return self._paths

    @property
    def extension_names(self) -> tuple[str, ...]:
        """Return visible extension names in load order."""
        return tuple(extension.name for extension in self._extensions if not extension.hidden)

    @property
    def extension_info(self) -> tuple[ExtensionInfo, ...]:
        """Return user-facing metadata for visible loaded extensions."""
        return tuple(
            ExtensionInfo(
                name=metadata.name,
                path=metadata.path,
                scope=extension_scope(
                    metadata.path,
                    project_dir=self._project_extensions_dir,
                    user_dir=self._user_extensions_dir,
                ),
            )
            for metadata in self.extension_metadata
            if not metadata.hidden
        )

    @property
    def extension_metadata(self) -> tuple[ExtensionSourceMetadata, ...]:
        """Return active visible and hidden source metadata in load order."""
        return tuple(
            ExtensionSourceMetadata(
                name=extension.name,
                source_id=extension.source_id,
                source=extension.source,
                hidden=extension.hidden,
                path=extension.path,
                api_version=extension.api_version,
                capabilities=extension.capabilities,
            )
            for extension in self._extensions
        )

    @property
    def diagnostics(self) -> tuple[ResourceDiagnostic, ...]:
        """Return load-time, handler, and provider-refresh diagnostics."""
        provider_diagnostics = tuple(
            ResourceDiagnostic(
                kind="provider",
                name=diagnostic.token.source_id,
                message=(
                    f"{diagnostic.message} for provider "
                    f"`{diagnostic.token.provider_id}` ({diagnostic.reason})"
                ),
            )
            for diagnostic in self._provider_registry.diagnostics
        )
        return tuple(self._load_diagnostics) + tuple(self._runtime_diagnostics) + provider_diagnostics

    @property
    def extension_tools(self) -> tuple[AgentTool, ...]:
        """Return extension-registered tools in registration order."""
        return tuple(registration.tool for registration in self._tools.values())

    @property
    def extension_tool_sources(self) -> dict[str, str]:
        """Map extension-registered tool names to their owning extension."""
        return {name: registration.extension for name, registration in self._tools.items()}

    @property
    def prompt_guidelines(self) -> tuple[str, ...]:
        """Return standalone guideline lines in registration order."""
        return tuple(guideline for _, _, guideline in self._prompt_guidelines)

    @property
    def prompt_sections(self) -> tuple[PromptSection, ...]:
        """Return free-form prompt sections in registration order."""
        return tuple(section for _, _, section in self._prompt_sections)

    @property
    def sourced_prompt_sections(self) -> tuple[PromptSection, ...]:
        """Return prompt sections annotated with their owning extension."""
        return tuple(
            PromptSection(
                title=section.title,
                body=section.body,
                source=f"extension: {extension}",
            )
            for _owner, extension, section in self._prompt_sections
        )

    # -- actions (called through ExtensionAPI) --------------------------------

    def send_user_message(self, content: str, *, deliver_as: str = "follow_up") -> None:
        """Deliver a user message into the active run, or start one when idle."""
        self._deliver_message(content, deliver_as=deliver_as, trigger_turn=True)

    def send_custom_message(
        self,
        content: str,
        *,
        custom_type: str,
        details: dict[str, JSONValue] | None = None,
        deliver_as: str = "follow_up",
        trigger_turn: bool = True,
    ) -> None:
        """Deliver a custom message carrying render metadata through the pipeline."""
        self._deliver_message(
            content,
            deliver_as=deliver_as,
            trigger_turn=trigger_turn,
            custom_type=custom_type,
            details=details,
        )

    def _deliver_message(
        self,
        content: str,
        *,
        deliver_as: str,
        trigger_turn: bool,
        custom_type: str | None = None,
        details: dict[str, JSONValue] | None = None,
    ) -> None:
        session = self.session_view
        if session.is_running:
            if deliver_as == "steer":
                session.queue_steering_message(content, custom_type=custom_type, details=details)
            else:
                session.queue_follow_up_message(content, custom_type=custom_type, details=details)
            return
        if trigger_turn and self._turn_requested is not None:
            self._turn_requested(content, custom_type, details)
            return
        # No host run-path registered (print mode, tests) or trigger_turn=False:
        # queue for whichever run happens next.
        session.queue_follow_up_message(content, custom_type=custom_type, details=details)

    async def append_custom_entry(self, namespace: str, data: dict[str, JSONValue]) -> None:
        """Persist a `CustomEntry` through the bound session."""
        await self.session_view.append_custom_entry(namespace, data)

    async def set_label(self, target_id: str, label: str | None) -> None:
        """Set or clear a per-entry session bookmark through the bound session."""
        await self.session_view.set_label(target_id, label)

    # -- tools ----------------------------------------------------------------

    def compose_tools(self, builtin_tools: Sequence[AgentTool]) -> list[AgentTool]:
        """Merge built-in and extension tools, then wrap all with hook seams.

        Extension tools override built-ins with the same name in place;
        extension-only tools append in registration order.
        """
        merged: list[AgentTool] = []
        extension_tools = dict(self._tools)
        for tool in builtin_tools:
            override = extension_tools.pop(tool.name, None)
            merged.append(override.tool if override is not None else tool)
        merged.extend(registration.tool for registration in extension_tools.values())
        return [self._wrap_tool(tool) for tool in merged]

    def bind_live_tools(self, tools: list[AgentTool], allowed: frozenset[str] | None) -> None:
        """Bind the session's materialized tool list for live registration.

        The bound object is the same list handed to the agent harness, which
        reads it per run; register/unregister keep registry and list in step.
        Appended tools are hook-wrapped like ``compose_tools`` output, so the
        tool pipeline covers dynamically registered tools too. Each load
        binds its own materialized list, replacing any previous binding,
        mirroring ``set_ui_bridge``.
        """
        self._live_tools = tools
        self._live_tools_all = list(tools)
        self._live_allowed = allowed
        self._live_wrapped.clear()
        self._apply_live_tool_filter()

    def set_active_tools(self, names: Sequence[str] | None) -> None:
        """Enable only the named tools for future runs (ports Pi's setActiveTools).

        ``None`` re-enables every tool. Disabling is reversible and does not
        withdraw the registration, so an extension can gate a tool per state
        without losing its handler. Unknown names are diagnosed. The system
        prompt is refreshed because it lists the available tools.
        """
        if self._live_tools_all is None:
            raise ExtensionError("set_active_tools requires a bound session")
        if names is None:
            self._active_tool_names = None
        else:
            requested = set(names)
            known = {tool.name for tool in self._live_tools_all}
            for unknown in sorted(requested - known):
                self._load_diagnostics.append(
                    ResourceDiagnostic(
                        kind="extension",
                        name="set_active_tools",
                        message=f"unknown tool `{unknown}`; ignored",
                    )
                )
            self._active_tool_names = requested
        self._apply_live_tool_filter()
        self.request_system_prompt_refresh()

    def _apply_live_tool_filter(self) -> None:
        """Rewrite the bound list to the tools that are currently active."""
        if self._live_tools is None or self._live_tools_all is None:
            return
        active = self._active_tool_names
        self._live_tools[:] = [tool for tool in self._live_tools_all if active is None or tool.name in active]

    async def execute_tool(
        self,
        name: str,
        arguments: Mapping[str, JSONValue],
        *,
        signal: ToolCancellationToken | None = None,
    ) -> AgentToolResult:
        """Run one active tool through the session's tool pipeline (ports ``ctx.executeTool``).

        The call goes through the wrapped tool, so ``tool_call``/``tool_result``
        hooks and project trust apply exactly as they do for the model. A tool
        disabled with :meth:`set_active_tools` is not reachable here.
        """
        tool = next(
            (candidate for candidate in self._live_tools or () if candidate.name == name),
            None,
        )
        if tool is None:
            raise ExtensionError(f"tool `{name}` is not active or not registered")
        return await tool.execute(uuid4().hex, arguments, signal=signal)

    def request_system_prompt_refresh(self) -> None:
        """Ask the bound session to rebuild its system prompt."""
        if self._session is not None:
            self._session.refresh_system_prompt()

    def _drop_live_tools(self, tools: list[AgentTool]) -> None:
        """Remove exact tool objects from the bound (and unfiltered) lists."""
        withdrawn = {id(tool) for tool in tools}
        if self._live_tools is not None:
            self._live_tools[:] = [tool for tool in self._live_tools if id(tool) not in withdrawn]
        if self._live_tools_all is not None:
            self._live_tools_all[:] = [tool for tool in self._live_tools_all if id(tool) not in withdrawn]

    def _wrap_tool(self, tool: AgentTool) -> AgentTool:
        async def executor(
            tool_call_id: str,
            arguments: Mapping[str, JSONValue],
            signal: ToolCancellationToken | None = None,
            on_update: ToolUpdateCallback | None = None,
        ) -> AgentToolResult:
            call_outcome = await self._run_tool_call_hooks(tool.name, arguments)
            if call_outcome.block:
                reason = call_outcome.reason or "blocked by an extension"
                return AgentToolResult(content=[TextContent(text=f"Tool call blocked: {reason}")])
            effective_arguments = call_outcome.arguments if call_outcome.arguments is not None else arguments
            result = await tool.execute(
                tool_call_id,
                effective_arguments,
                signal=signal,
                on_update=on_update,
            )
            return await self._run_tool_result_hooks(tool.name, effective_arguments, result)

        return AgentTool(
            name=tool.name,
            label=tool.label,
            description=tool.description,
            parameters=tool.parameters,
            execute_fn=executor,
            prompt_snippet=tool.prompt_snippet,
            prompt_guidelines=tool.prompt_guidelines,
            prepare_arguments=tool.prepare_arguments,
            execution_mode=tool.execution_mode,
            render_call=tool.render_call,
            render_result=tool.render_result,
        )

    async def _run_tool_call_hooks(
        self,
        tool_name: str,
        arguments: Mapping[str, JSONValue],
    ) -> ToolCallHookResult:
        effective: Mapping[str, JSONValue] = arguments
        for owner, handler in self._handlers_for("tool_call"):
            event = ToolCallHookEvent(tool_name=tool_name, arguments=effective)
            try:
                result = await _resolve(handler(event, self._fresh_context(owner.source_id)))
            except Exception as exc:  # noqa: BLE001 - fail-safe: an error blocks the tool
                self._record_runtime_failure(owner.name, "tool_call", exc)
                return ToolCallHookResult(
                    block=True,
                    reason=f"extension `{owner.name}` tool_call hook failed: {exc}",
                )
            if result is None:
                continue
            if not isinstance(result, ToolCallHookResult):
                self._record_bad_result(owner.name, "tool_call", result)
                continue
            if result.block:
                return ToolCallHookResult(block=True, reason=result.reason)
            if result.arguments is not None:
                effective = result.arguments
        if effective is arguments:
            return ToolCallHookResult()
        return ToolCallHookResult(arguments=effective)

    async def _run_tool_result_hooks(
        self,
        tool_name: str,
        arguments: Mapping[str, JSONValue],
        result: AgentToolResult,
    ) -> AgentToolResult:
        current = result
        for owner, handler in self._handlers_for("tool_result"):
            event = ToolResultHookEvent(tool_name=tool_name, arguments=arguments, result=current)
            try:
                outcome = await _resolve(handler(event, self._fresh_context(owner.source_id)))
            except Exception as exc:  # noqa: BLE001 - result hooks are observational-ish
                self._record_runtime_failure(owner.name, "tool_result", exc)
                continue
            if outcome is None:
                continue
            if not isinstance(outcome, ToolResultHookResult):
                self._record_bad_result(owner.name, "tool_result", outcome)
                continue
            updates: dict[str, object] = {}
            if outcome.content is not None:
                updates["content"] = [TextContent(text=outcome.content)]
            if outcome.details is not None:
                updates["details"] = outcome.details
            if updates:
                current = current.model_copy(update=updates)
        return current

    # -- commands ---------------------------------------------------------------

    def build_command_registry(self) -> CommandRegistry:
        """Build a session command registry: defaults plus extension commands."""
        registry = create_default_command_registry()
        for command in self._commands.values():
            slash_command = SlashCommand(
                name=command.name,
                description=command.description or f"Extension command ({command.extension}).",
                usage=command.usage,
                handler=self._command_handler(command),
                aliases=command.aliases,
                search_terms=(command.extension, "extension"),
            )
            try:
                registry.register(slash_command)
            except ValueError as exc:
                self._load_diagnostics.append(
                    ResourceDiagnostic(
                        kind="extension",
                        name=command.extension,
                        message=f"could not register command `/{command.name}`: {exc}",
                    )
                )
        return registry

    def _command_handler(self, command: ExtensionCommand) -> Callable[[CommandContext], CommandResult]:
        def handler(context: CommandContext) -> CommandResult:
            extension_context = ExtensionCommandContext(
                name=command.name,
                args=context.args,
                api=self._api_for(command.source_id),
            )
            try:
                message = command.handler(context.args, extension_context)
            except Exception as exc:  # noqa: BLE001 - extensions are an isolation boundary
                self._record_runtime_failure(command.extension, f"command:/{command.name}", exc)
                return handled_result(message_outcome(f"Extension command /{command.name} failed: {exc}"))
            return handled_result(message_outcome(message or ""))

        return handler

    # -- event dispatch -----------------------------------------------------------

    async def decide_project_trust(self, event: ProjectTrustEvent) -> ExtensionTrustResult | None:
        """Return the first decisive eligible extension trust result.

        This runtime must contain only built-in, user, and explicit extensions;
        callers load project extensions only after this method resolves.
        """
        for owner, handler in self._handlers_for("project_trust"):
            try:
                result = await _resolve(handler(event, self._fresh_context(owner.source_id)))
            except Exception as exc:  # noqa: BLE001 - trust handlers fail closed/defer
                self._record_runtime_failure(owner.name, "project_trust", exc)
                continue
            if result is None:
                continue
            if not isinstance(result, ExtensionTrustResult):
                self._record_bad_result(owner.name, "project_trust", result)
                continue
            if result.decision != "defer":
                return result
        return None

    async def emit_session_start(self, reason: SessionLifecycleReason) -> None:
        """Dispatch `session_start` to subscribed extensions."""
        await self._emit_lifecycle("session_start", SessionStartEvent(reason=reason))

    async def emit_session_shutdown(self, reason: SessionLifecycleReason) -> None:
        """Dispatch `session_shutdown` to subscribed extensions."""
        await self._emit_lifecycle("session_shutdown", SessionShutdownEvent(reason=reason))

    async def run_input_hooks(
        self,
        text: str,
        *,
        source: Literal["interactive", "extension"] = "interactive",
        streaming_behavior: Literal["steer", "follow_up"] | None = None,
    ) -> InputHookOutcome:
        """Run `input` hooks over prompt text; transforms chain, handled wins.

        `source`/`streaming_behavior` are surfaced to handlers on the
        `InputEvent` payload; they do not change chaining semantics.
        """
        current = text
        for owner, handler in self._handlers_for("input"):
            try:
                result = await _resolve(
                    handler(
                        InputEvent(
                            text=current,
                            source=source,
                            streaming_behavior=streaming_behavior,
                        ),
                        self._fresh_context(owner.source_id),
                    )
                )
            except Exception as exc:  # noqa: BLE001 - extensions are an isolation boundary
                self._record_runtime_failure(owner.name, "input", exc)
                continue
            if result is None:
                continue
            if not isinstance(result, InputHookResult):
                self._record_bad_result(owner.name, "input", result)
                continue
            if result.action == "handled":
                return InputHookOutcome(handled=True, text=current, message=result.message)
            if result.action == "transform" and result.text is not None:
                current = result.text
        return InputHookOutcome(handled=False, text=current)

    async def emit_event(self, event: object) -> None:
        """Dispatch one canonical agent or coding-session event to extensions."""
        event_type = getattr(event, "type", None)
        if not isinstance(event_type, str):
            raise TypeError("Extension events must expose a string type")
        handlers = list(self._handlers_for(event_type))
        handlers.extend(self._handlers_for(AGENT_EVENT_WILDCARD))
        for owner, handler in handlers:
            try:
                await _resolve(handler(event, self._fresh_context(owner.source_id)))
            except Exception as exc:  # noqa: BLE001 - extensions are an isolation boundary
                self._record_runtime_failure(owner.name, event_type, exc)

    async def run_user_bash(self, event: UserBashEvent) -> UserBashResult | None:
        """Ask extensions to answer a ``!``/``!!`` command before local execution.

        Gate semantics from the hook-composition contract: the first handler
        returning a :class:`UserBashResult` wins and the shell does not run;
        ``None`` defers to the next handler. A raising handler is skipped.
        """
        for owner, handler in self._handlers_for("user_bash"):
            result = await self._invoke_handler(owner, "user_bash", event, handler)
            if result is _PROVIDER_HANDLER_FAILED or result is None:
                continue
            if isinstance(result, UserBashResult):
                return result
            self._record_bad_result(owner.name, "user_bash", result)
        return None

    async def request_compaction_summary(self, event: SessionBeforeCompactEvent) -> str | None:
        """Ask extensions for a compaction summary (Pi's ``session_before_compact``).

        First non-empty summary wins; ``None`` falls back to the built-in
        summarizer. ``block`` is deliberately not offered: compaction must
        always complete, so an extension can only supply text, never veto.
        """
        for owner, handler in self._handlers_for("session_before_compact"):
            result = await self._invoke_handler(owner, "session_before_compact", event, handler)
            if result is _PROVIDER_HANDLER_FAILED or result is None:
                continue
            if isinstance(result, CompactionSummaryResult):
                if result.summary.strip():
                    return result.summary.strip()
                self._record_bad_result(owner.name, "session_before_compact", result)
                continue
            self._record_bad_result(owner.name, "session_before_compact", result)
        return None

    async def _on_agent_event(self, event: AgentEvent) -> None:
        """Adapt core turn events to Pi's extension-facing session metadata."""
        extension_event: object = event
        if isinstance(event, AgentStartEvent):
            self._extension_turn_index = 0
        elif isinstance(event, AgentTurnStartEvent):
            extension_event = TurnStartEvent(
                turn_index=self._extension_turn_index,
                timestamp=time_ns() // 1_000_000,
            )
        elif isinstance(event, AgentTurnEndEvent):
            extension_event = TurnEndEvent(
                turn_index=self._extension_turn_index,
                message=event.message,
                tool_results=list(event.tool_results),
            )
        await self.emit_event(extension_event)
        if isinstance(event, AgentTurnEndEvent):
            self._extension_turn_index += 1

    async def _emit_lifecycle(self, event_name: str, payload: object) -> None:
        # Extensions whose setup raised never reached session_start, but they may
        # already own tasks/timers/threads and registered shutdown handlers
        # before failing. For ``session_shutdown`` they join this same dispatch
        # loop (and are dropped afterwards), so the host's awaited shutdown is
        # their retire path instead of an orphaned registration.
        failed = tuple(self._failed_extensions) if event_name == "session_shutdown" else ()
        handlers = [
            *self._handlers_for(event_name),
            *((owner, handler) for owner in failed for handler in owner.handlers.get(event_name, ())),
        ]
        for owner, handler in handlers:
            try:
                await _resolve(handler(payload, self._fresh_context(owner.source_id)))
            except Exception as exc:  # noqa: BLE001 - extensions are an isolation boundary
                self._record_runtime_failure(owner.name, event_name, exc)
        if failed:
            self._failed_extensions.clear()

    # -- internals -------------------------------------------------------------

    def _handlers_for(self, event: str) -> Iterator[tuple[RegisteredExtension, ExtensionHandler]]:
        for extension in self._extensions:
            for handler in extension.handlers.get(event, ()):
                yield extension, handler

    def _extension_by_source(self, source_id: str) -> RegisteredExtension | None:
        for extension in self._extensions:
            if extension.source_id == source_id:
                return extension
        # Failed-setup registrations stay addressable until their shutdown runs,
        # so a shutdown handler can still read its own context.
        for extension in self._failed_extensions:
            if extension.source_id == source_id:
                return extension
        return None

    def _extension_display_name(self, source_id: str) -> str:
        extension = self._extension_by_source(source_id)
        return extension.name if extension is not None else source_id

    def _fresh_context(self, source_id: str) -> ExtensionContext:
        """Return a fresh context for one handler invocation."""
        api = self._api_for(source_id)
        return ExtensionContext(
            self,
            api._generation,
            extension_name=self._extension_display_name(source_id),
        )

    def _api_for(self, source_id: str) -> ExtensionAPI:
        extension = self._extension_by_source(source_id)
        if extension is None:
            raise ExtensionError(f"unknown extension source: {source_id}")
        return extension.api

    def record_ui_failure(self, extension: str, context: str, exc: BaseException) -> None:
        """Record a host-isolated extension UI failure in session diagnostics."""
        self._runtime_diagnostics.append(
            ResourceDiagnostic(
                kind="extension",
                name=extension,
                message=f"UI component `{context}` failed: {exc!r}",
                severity="error",
            )
        )

    def _record_runtime_failure(self, extension: str, event: str, exc: Exception) -> None:
        self._runtime_diagnostics.append(
            ResourceDiagnostic(
                kind="extension",
                name=extension,
                message=f"handler for `{event}` raised: {exc!r}",
                severity="error",
            )
        )

    def _record_bad_result(self, extension: str, event: str, result: object) -> None:
        self._runtime_diagnostics.append(
            ResourceDiagnostic(
                kind="extension",
                name=extension,
                message=(
                    f"handler for `{event}` returned unsupported result type {type(result).__name__}; ignored"
                ),
            )
        )


def extension_scope(
    path: Path | None,
    *,
    project_dir: Path | None,
    user_dir: Path,
) -> Literal["project", "user", "explicit", "built-in"]:
    """Classify where a loaded extension came from."""
    if path is None:
        return "built-in"
    resolved = path.resolve()
    if project_dir is not None and resolved.is_relative_to(project_dir.resolve()):
        return "project"
    if resolved.is_relative_to(user_dir.resolve()):
        return "user"
    return "explicit"


async def _resolve(value: object) -> object:
    if isawaitable(value):
        return await value
    return value


class _ProviderHandlerFailed:
    """Sentinel: a provider-seam handler raised and was recorded (isolation)."""


_PROVIDER_HANDLER_FAILED = _ProviderHandlerFailed()
