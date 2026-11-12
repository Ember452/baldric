"""Extension-facing API types and hook payloads."""

from __future__ import annotations

import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, cast
from uuid import uuid4

from baldric.agent.tool_calls import BeforeToolCall
from baldric.protocol.messages import AgentMessage
from baldric.protocol.tools import AgentTool, AgentToolResult, ToolCancellationToken
from baldric.protocol.types import JSONValue

if TYPE_CHECKING:
    from textual import events
    from textual.widget import Widget

    from baldric.runtime.backends.contracts import LocalBackend
    from baldric.runtime.config.paths import BaldricPaths
    from baldric.runtime.extensions.provider_registry import DynamicProviderRegistry
    from baldric.runtime.extensions.providers import DynamicProvider
    from baldric.runtime.extensions.runtime import ExtensionRuntime
    from baldric.runtime.session.session import ModelChoice
    from baldric.runtime.trust.policy import ProjectTrustResolution
    from baldric.runtime.tui.config import TuiTheme

# Pure contract shapes (event payloads, capabilities, type aliases, and event
# constants) live in ``baldric.protocol.extension`` so any layer can depend on
# them without pulling the runtime. They are re-exported here unchanged (the
# ``X as X`` form marks them explicit re-exports, not unused imports) so the
# existing ``baldric.runtime.extensions.api`` import surface keeps working while
# the structural rearchitecture proceeds; the single source of truth is the
# protocol module.
from baldric.protocol.extension import (
    AGENT_EVENT_TYPES as AGENT_EVENT_TYPES,
)
from baldric.protocol.extension import (
    AGENT_EVENT_WILDCARD as AGENT_EVENT_WILDCARD,
)
from baldric.protocol.extension import (
    EVENT_NAME_ALIASES as EVENT_NAME_ALIASES,
)
from baldric.protocol.extension import (
    EXTENSION_API_VERSION as EXTENSION_API_VERSION,
)
from baldric.protocol.extension import (
    LIFECYCLE_EVENT_TYPES as LIFECYCLE_EVENT_TYPES,
)
from baldric.protocol.extension import (
    PROVIDER_EVENT_TYPES as PROVIDER_EVENT_TYPES,
)
from baldric.protocol.extension import (
    CompactionSummaryResult as CompactionSummaryResult,
)
from baldric.protocol.extension import (
    CustomEntryView as CustomEntryView,
)
from baldric.protocol.extension import (
    CustomMessageMarkup as CustomMessageMarkup,
)
from baldric.protocol.extension import (
    CustomMessageView as CustomMessageView,
)
from baldric.protocol.extension import (
    DeliverAs as DeliverAs,
)
from baldric.protocol.extension import (
    EntryRenderer as EntryRenderer,
)
from baldric.protocol.extension import (
    ExtensionCapabilities as ExtensionCapabilities,
)
from baldric.protocol.extension import (
    InputEvent as InputEvent,
)
from baldric.protocol.extension import (
    InputHookResult as InputHookResult,
)
from baldric.protocol.extension import (
    MarkdownRenderContext as MarkdownRenderContext,
)
from baldric.protocol.extension import (
    MarkdownTransformer as MarkdownTransformer,
)
from baldric.protocol.extension import (
    MessageRenderer as MessageRenderer,
)
from baldric.protocol.extension import (
    MessageRenderOptions as MessageRenderOptions,
)
from baldric.protocol.extension import (
    NotifyLevel as NotifyLevel,
)
from baldric.protocol.extension import (
    ProviderContextEvent as ProviderContextEvent,
)
from baldric.protocol.extension import (
    ProviderHeadersEvent as ProviderHeadersEvent,
)
from baldric.protocol.extension import (
    ProviderRequestEvent as ProviderRequestEvent,
)
from baldric.protocol.extension import (
    ProviderResponseEvent as ProviderResponseEvent,
)
from baldric.protocol.extension import (
    ProviderStreamEvent as ProviderStreamEvent,
)
from baldric.protocol.extension import (
    SessionBeforeCompactEvent as SessionBeforeCompactEvent,
)
from baldric.protocol.extension import (
    SessionLifecycleReason as SessionLifecycleReason,
)
from baldric.protocol.extension import (
    SessionShutdownEvent as SessionShutdownEvent,
)
from baldric.protocol.extension import (
    SessionStartEvent as SessionStartEvent,
)
from baldric.protocol.extension import (
    ToolCallHookEvent as ToolCallHookEvent,
)
from baldric.protocol.extension import (
    ToolCallHookResult as ToolCallHookResult,
)
from baldric.protocol.extension import (
    ToolCallMarkup as ToolCallMarkup,
)
from baldric.protocol.extension import (
    ToolCallResolver as ToolCallResolver,
)
from baldric.protocol.extension import (
    ToolResultHookEvent as ToolResultHookEvent,
)
from baldric.protocol.extension import (
    ToolResultHookResult as ToolResultHookResult,
)
from baldric.protocol.extension import (
    ToolResultMarkup as ToolResultMarkup,
)
from baldric.protocol.extension import (
    ToolResultResolver as ToolResultResolver,
)
from baldric.protocol.extension import (
    TurnEndEvent as TurnEndEvent,
)
from baldric.protocol.extension import (
    TurnStartEvent as TurnStartEvent,
)
from baldric.protocol.extension import (
    UserBashEvent as UserBashEvent,
)
from baldric.protocol.extension import (
    UserBashResult as UserBashResult,
)

# --- component seam ---------------------------------------------------------
# Widget-hosting capability that lets an extension mount its own Textual widgets
# into host-owned slots and a main-area view, and intercept keys pre-dispatch
# (before the host's priority bindings and the focused widget). The "component"
# type is Textual's own ``Widget`` (referenced only under TYPE_CHECKING so
# print-mode stays import-clean). Textual is deliberately part of the public
# extension contract, but only for extensions that declare the ``components``
# capability (``ExtensionCapabilities.components``); an extension that never
# touches this seam needs no Textual at all. Extensions that do build widgets
# target the Textual version baldric pins; a Textual major bump is a coordinated
# break for core and components extensions together.
# History and measured trade-offs: dev-notes/design/component-seam-experiment.md.
# It replaced the older transcript-source seam, which Step 3 removed from core.

Placement = Literal["above_prompt", "below_prompt"]

# Factories run on the UI thread and receive the live theme (theme handoff,
# mirrors Pi's ``(tui, theme) => Component``).
SlotWidgetFactory = Callable[["TuiTheme"], "Widget"]
# A slot widget may be given as a factory or, for the simple case, as a plain
# list of display lines the HOST turns into a widget — this lets an extension
# mount text without importing Textual at all (ports Pi's ``string[]`` form of
# ``setWidget``). Strings are rendered as Rich markup, with a literal-text
# fallback if the markup is malformed.
SlotWidgetContent = Sequence[str] | SlotWidgetFactory
# Sidebar bodies use the same data-first shape: simple sections provide Rich
# display lines without importing Textual; advanced sections provide a widget
# factory receiving the live theme.
SidebarWidgetFactory = Callable[["TuiTheme"], "Widget"]
SidebarContent = Sequence[str] | SidebarWidgetFactory
# The main-view factory also receives the handle so the widget can close itself.
MainViewFactory = Callable[["MainViewHandle", "TuiTheme"], "Widget"]

# Pre-dispatch key hook (ports Pi's ``onTerminalInput``). Returns True to
# consume the key. Fires for every main-screen key regardless of focus; the host
# passes the Textual ``Key`` event and the current prompt text so the handler
# can self-gate (Pi gates on ``getEditorText() === ""``).
KeyInterceptor = Callable[["events.Key", str], bool]


_DEFAULT_THEME: TuiTheme | None = None


def _default_theme() -> TuiTheme:
    """Return a shared default theme without importing the TUI at module load.

    The import is deferred (and cached) so merely importing the extensions API
    stays free of the Textual/TUI dependency graph; only an extension that
    actually reads ``theme`` in print mode pays for it, and it never raises.
    """
    global _DEFAULT_THEME
    if _DEFAULT_THEME is None:
        from baldric.runtime.tui.config import BALDRIC_DARK_THEME

        _DEFAULT_THEME = BALDRIC_DARK_THEME
    return _DEFAULT_THEME


class MainViewHandle(Protocol):
    """Handle to an open main-area view (ports Pi's ``OverlayHandle``, trimmed).

    Carries Pi's ``done(result)`` semantics: the factory (or a key interceptor)
    calls ``close(result)`` to tear the view down *and* hand a value back to
    whoever opened it, and the opener awaits :meth:`wait` for that value. This
    is the result-resolution half of Pi's ``ctx.ui.custom<T>``, kept on the
    synchronous open/handle model rather than an ``async`` open.

    ``close()`` unmounts the view and restores the main transcript. It is safe
    to call more than once; the first close wins and later closes are no-ops.
    """

    def close(self, result: object | None = None) -> None:
        """Close the view, resolving :meth:`wait` with ``result`` (Pi's ``done``).

        The first close wins: its ``result`` is what :meth:`wait` returns, and
        any later ``close(...)`` is a no-op. Safe to call more than once.
        """
        ...

    async def wait(self) -> object | None:
        """Await the view's teardown and return the result passed to ``close``.

        Resolves with the value handed to :meth:`close` (``None`` when closed
        with no result). Also resolves with ``None`` — never hangs — when the
        view is force-cleared on a session rebind, quarantined after a widget
        crash, or superseded by a later ``open_main_view``. Returns immediately
        if the view was already closed before ``wait`` is awaited.
        """
        ...

    @property
    def is_open(self) -> bool: ...


class ComponentBridge(Protocol):
    """Host widget-hosting capability, exposed via ``context.ui.components``.

    Part of what a :class:`UiBridge` provides when a TUI is attached;
    :class:`NullUiBridge`/:class:`StderrUiBridge` implement it as no-ops so an
    extension stays fully functional (just widget-less) in print mode. Check
    :attr:`supports_components` before building widgets.
    """

    @property
    def supports_components(self) -> bool:
        """Return whether the frontend can host extension widgets."""
        ...

    @property
    def theme(self) -> TuiTheme:
        """Return the live TUI theme handed to widget factories."""
        ...

    def get_prompt_text(self) -> str:
        """Return the current prompt-editor text (Pi's getEditorText).

        Key interceptors receive the prompt text as their second argument;
        this is for reads outside the key path.
        """
        ...

    def request_render(self) -> None:
        """Ask the host to re-render mounted extension widgets (Pi's requestRender)."""
        ...

    def set_slot_widget(
        self,
        key: str,
        content: SlotWidgetContent | None,
        *,
        placement: Placement = "above_prompt",
    ) -> None:
        """Mount an extension widget into a prompt-adjacent slot under ``key``.

        ``content`` is either a ``factory(theme) -> Widget`` callable or a plain
        list of display lines (``Sequence[str]``) the host renders as Rich
        markup — the string form lets simple extensions avoid importing Textual.
        Passing ``content=None`` unmounts and forgets that key. Re-setting a key
        replaces its content. Multiple keys per placement mount in call order.
        Placement defaults to ``"above_prompt"`` (Pi's ``aboveEditor``).
        """
        ...

    def open_main_view(self, factory: MainViewFactory) -> MainViewHandle:
        """Mount ``factory(handle, theme)`` as a full main-area view.

        The widget replaces the main transcript in place (a display-toggled
        sibling, not a modal screen), so prompt-adjacent widgets such as slot
        widgets stay visible. ``handle.close(result)`` restores the transcript
        and resolves ``await handle.wait()`` with ``result`` (Pi's ``done``),
        so the opener can show a view and get an answer back.
        """
        ...

    def register_key_interceptor(self, handler: KeyInterceptor) -> Callable[[], None]:
        """Register a pre-dispatch key hook; return an unsubscribe callable.

        Ports Pi's ``onTerminalInput``. The handler sees a key before the
        host's app-level priority bindings and before the focused widget, so it
        can own navigation keys the host otherwise reserves. It fires for EVERY
        main-screen key regardless of focus (never while a modal screen is on
        top), so the handler MUST self-gate and return ``True`` only for keys it
        consumes.

        The host's hard interrupt/exit keys (``ctrl+c`` and ``ctrl+d``) are
        reserved: the interceptor is never consulted for them and cannot
        consume them, so a bug in the handler can never swallow the session's
        escape hatches. All other keys — escape, enter, arrows, tab — remain
        interceptable.
        """
        ...


class ExtensionSidebar:
    """Extension-owned facade for host-framed TUI sidebar sections.

    Sections are isolated by extension name and stable key. Re-setting a key
    updates it without changing its position; removing and re-adding it appends
    it after the remaining extension sections. The host owns headings,
    separators, width, scrolling, sidebar placement, and lifecycle cleanup.
    """

    def __init__(
        self,
        runtime: ExtensionRuntime,
        extension_name: str,
        generation: ExtensionGeneration,
    ) -> None:
        self._runtime = runtime
        self._extension_name = extension_name
        self._generation = generation

    @property
    def supported(self) -> bool:
        """Return whether the active frontend can display sidebar sections."""
        self._generation.assert_active()
        return bool(getattr(self._runtime.ui, "supports_sidebar", False))

    def set_section(self, key: str, *, title: str, content: SidebarContent) -> None:
        """Add or replace a host-framed sidebar section under stable ``key``."""
        self._generation.assert_active()
        normalized_key = key.strip()
        normalized_title = title.strip()
        if not normalized_key:
            raise ExtensionError("sidebar section key must not be empty")
        if not normalized_title:
            raise ExtensionError("sidebar section title must not be empty")
        if not self.supported:
            return
        setter = getattr(self._runtime.ui, "set_sidebar_section", None)
        if setter is not None:
            setter(
                self._extension_name,
                normalized_key,
                title=normalized_title,
                content=content,
            )

    def remove_section(self, key: str) -> None:
        """Remove this extension's sidebar section under ``key``, if present."""
        self._generation.assert_active()
        normalized_key = key.strip()
        if not normalized_key:
            raise ExtensionError("sidebar section key must not be empty")
        if not self.supported:
            return
        remover = getattr(self._runtime.ui, "remove_sidebar_section", None)
        if remover is not None:
            remover(self._extension_name, normalized_key)


class ExtensionError(RuntimeError):
    """Raised when an extension misuses the API (e.g. actions before binding)."""


_STALE_MESSAGE = (
    "extension instance is stale after reload: state captured before /reload"
    " (a saved `baldric` API object, context, or ui handle) must not be reused;"
    " the reloaded extension received a fresh API in its new setup()"
)


class ExtensionGeneration:
    """Liveness token for one extension load generation.

    Ports Pi's ``assertActive``/``invalidate`` staleness guard: every
    :class:`ExtensionAPI` method and every :class:`ExtensionContext`/
    :class:`ExtensionUi` read checks this token before touching the runtime,
    so state captured before a `/reload` fails loudly instead of silently
    acting against the new registration set. Only reload invalidates; session
    rebinding (resume/new/branch) keeps the generation alive by design (see
    the phase-21 lifecycle Ruling).
    """

    __slots__ = ("_id", "_stale_message")

    def __init__(self) -> None:
        self._id = uuid4().hex
        self._stale_message: str | None = None

    @property
    def id(self) -> str:
        """Return this generation's stable process-local identity."""
        return self._id

    @property
    def active(self) -> bool:
        """Return whether this generation is still the live one."""
        return self._stale_message is None

    def invalidate(self, message: str | None = None) -> None:
        """Mark this generation stale; the first message wins (Pi parity)."""
        if self._stale_message is None:
            self._stale_message = message or _STALE_MESSAGE

    def assert_active(self) -> None:
        """Raise :class:`ExtensionError` when this generation is stale."""
        if self._stale_message is not None:
            raise ExtensionError(self._stale_message)


# Extension-facing event payloads (TurnStartEvent, ProviderContextEvent,
# ToolCallHookEvent, UserBashEvent, SessionBeforeCompactEvent, …) are pure shapes
# defined in and re-exported from ``baldric.protocol.extension`` (see the import
# at the top of this module). They live there so a feature or extension can name
# them without importing the runtime layer.


ExtensionHandler = Callable[[object, "ExtensionContext"], object | Awaitable[object]]
# Command handlers are sync-only: the slash-command path (CommandRegistry ->
# CodingSession.handle_command -> TUI submit) is synchronous end to end.
ExtensionCommandHandler = Callable[["str", "ExtensionCommandContext"], "str | None"]


@dataclass(frozen=True, slots=True)
class ExtensionRuntimeDiagnostic:
    """A runtime failure raised by an extension handler."""

    extension: str
    event: str
    message: str


class UiBridge(Protocol):
    """Host-provided UI capabilities available to extensions.

    Dialog methods (`select`/`confirm`/`input`) are async and mirror Pi's
    `ctx.ui`. Without an interactive frontend they return the Pi no-op
    defaults (`None`/`False`/`None`). `timeout` (seconds) auto-dismisses a
    dialog with the no-op default; `None` waits indefinitely.
    """

    @property
    def has_ui(self) -> bool:
        """Return whether an interactive UI is attached."""
        ...

    def notify(self, message: str, level: NotifyLevel = "info") -> None:
        """Show a notification to the user (no-op without a UI)."""
        ...

    def suspend(self) -> AbstractContextManager[None]:
        """Return a context manager that pauses the UI for an external program."""
        ...

    async def select(
        self,
        title: str,
        options: Sequence[str],
        *,
        timeout: float | None = None,
    ) -> str | None:
        """Show a picker; return the chosen option, or None on cancel."""
        ...

    async def confirm(
        self,
        title: str,
        message: str,
        *,
        timeout: float | None = None,
    ) -> bool:
        """Show a confirmation; return True only if confirmed."""
        ...

    async def input(
        self,
        title: str,
        placeholder: str = "",
        *,
        timeout: float | None = None,
    ) -> str | None:
        """Show a text prompt; return the entered text, or None on cancel."""
        ...

    # -- component seam -- see ComponentBridge for docs -----------------------

    @property
    def supports_components(self) -> bool:
        """Return whether the frontend can host extension widgets."""
        ...

    @property
    def theme(self) -> TuiTheme:
        """Return the live TUI theme handed to widget factories."""
        ...

    def get_prompt_text(self) -> str:
        """Return the current prompt-editor text."""
        ...

    def request_render(self) -> None:
        """Ask the host to re-render mounted extension widgets."""
        ...

    def set_slot_widget(
        self,
        key: str,
        content: SlotWidgetContent | None,
        *,
        placement: Placement = "above_prompt",
    ) -> None:
        """Mount or remove an extension slot widget (factory or string lines)."""
        ...

    def open_main_view(self, factory: MainViewFactory) -> MainViewHandle:
        """Open a full main-area extension view."""
        ...

    def register_key_interceptor(self, handler: KeyInterceptor) -> Callable[[], None]:
        """Register a pre-dispatch key hook; return an unsubscribe callable.

        See the base bridge protocol: the handler is consulted before the
        host's priority bindings and the focused widget, fires for every
        main-screen key regardless of focus, and must self-gate. The hard
        interrupt/exit keys (``ctrl+c`` and ``ctrl+d``) are reserved and never
        reach the interceptor.
        """
        ...

    @property
    def supports_sidebar(self) -> bool:
        """Return whether this frontend can host extension sidebar sections."""
        ...

    def set_sidebar_section(
        self,
        extension_name: str,
        key: str,
        *,
        title: str,
        content: SidebarContent,
    ) -> None:
        """Add or replace one extension-owned, host-framed sidebar section."""
        ...

    def remove_sidebar_section(self, extension_name: str, key: str) -> None:
        """Remove one extension-owned sidebar section, if present."""
        ...

    def clear_components(self) -> None:
        """Tear down all extension-owned UI (host-driven, not for extensions).

        The runtime drives this on `/reload` (the stale generation's widgets
        and interceptors must not outlive its registrations) and on session
        rebinds (resume/new), before ``session_start`` fires so handlers can
        re-mount. Slot widgets and any main view are unmounted (a pending
        ``wait()`` resolves with ``None``) and key interceptors are dropped.
        """
        ...


class _DeadMainViewHandle:
    """A no-op main-view handle returned when no UI can host a view."""

    def close(self, result: object | None = None) -> None:
        """Do nothing: there is no view to close (``result`` is ignored)."""

    async def wait(self) -> object | None:
        """Return None immediately: a dead handle never opens a view."""
        return None

    @property
    def is_open(self) -> bool:
        """Return False: a dead handle is never open."""
        return False


class NullUiBridge:
    """UI bridge used when no interactive frontend is attached."""

    @property
    def has_ui(self) -> bool:
        """Return False: print mode has no interactive UI."""
        return False

    def notify(self, message: str, level: NotifyLevel = "info") -> None:
        """Ignore notifications without a UI."""

    def suspend(self) -> AbstractContextManager[None]:
        """Return a no-op context manager: there is no UI to pause."""
        return nullcontext()

    async def select(
        self,
        title: str,
        options: Sequence[str],
        *,
        timeout: float | None = None,
    ) -> str | None:
        """Return None: no UI to pick from (Pi no-op default)."""
        return None

    async def confirm(
        self,
        title: str,
        message: str,
        *,
        timeout: float | None = None,
    ) -> bool:
        """Return False: no UI to confirm with (Pi no-op default)."""
        return False

    async def input(
        self,
        title: str,
        placeholder: str = "",
        *,
        timeout: float | None = None,
    ) -> str | None:
        """Return None: no UI to enter text into (Pi no-op default)."""
        return None

    # -- component seam -------------------------------------------------------

    @property
    def supports_components(self) -> bool:
        """Return False: print mode cannot host widgets."""
        return False

    @property
    def theme(self) -> TuiTheme:
        """Return a usable default theme (never raise; print-mode may read it)."""
        return _default_theme()

    def get_prompt_text(self) -> str:
        """Return an empty prompt: there is no editor in print mode."""
        return ""

    def request_render(self) -> None:
        """Do nothing: there is no frontend to re-render."""

    def set_slot_widget(
        self,
        key: str,
        content: SlotWidgetContent | None,
        *,
        placement: Placement = "above_prompt",
    ) -> None:
        """Do nothing: there is no slot to mount into."""

    def open_main_view(self, factory: MainViewFactory) -> MainViewHandle:
        """Return a dead handle: there is no main area to host a view."""
        return _DeadMainViewHandle()

    def register_key_interceptor(self, handler: KeyInterceptor) -> Callable[[], None]:
        """Return a no-op unsubscribe: no key stream to intercept."""
        return lambda: None

    @property
    def supports_sidebar(self) -> bool:
        """Return False: print mode has no interactive sidebar."""
        return False

    def set_sidebar_section(
        self,
        extension_name: str,
        key: str,
        *,
        title: str,
        content: SidebarContent,
    ) -> None:
        """Do nothing: there is no sidebar in print mode."""

    def remove_sidebar_section(self, extension_name: str, key: str) -> None:
        """Do nothing: there is no sidebar in print mode."""

    def clear_components(self) -> None:
        """Do nothing: no components were ever mounted."""


class StderrUiBridge(NullUiBridge):
    """UI bridge that writes extension notifications to stderr (print mode).

    Inherits the Pi no-op dialog defaults from `NullUiBridge`; only
    `notify` is observable in print mode.
    """

    def notify(self, message: str, level: NotifyLevel = "info") -> None:
        """Print the notification to stderr."""
        print(f"[extension:{level}] {message}", file=sys.stderr)


@dataclass(frozen=True, slots=True)
class ExtensionCommandContext:
    """Context passed to extension slash-command handlers."""

    name: str
    args: str
    api: ExtensionAPI


class ExtensionUi:
    """Interactive UI facade exposed to extensions as `context.ui`.

    Mirrors Pi's `ctx.ui`: async `select`/`confirm`/`input` dialogs plus a
    synchronous `notify`. Every call delegates to the host UI bridge, which
    returns the Pi no-op defaults when no interactive frontend is attached.
    Every member (trivial reads included, matching Pi) asserts the owning
    load generation is still active and raises :class:`ExtensionError` when
    the facade was captured before a `/reload`.
    """

    def __init__(
        self,
        runtime: ExtensionRuntime,
        generation: ExtensionGeneration | None = None,
        *,
        extension_name: str = "",
    ) -> None:
        self._runtime = runtime
        self._generation = generation if generation is not None else ExtensionGeneration()
        self._sidebar = ExtensionSidebar(runtime, extension_name, self._generation)

    @property
    def has_ui(self) -> bool:
        """Return whether an interactive UI is attached."""
        self._generation.assert_active()
        return self._runtime.ui.has_ui

    async def select(
        self,
        title: str,
        options: Sequence[str],
        *,
        timeout: float | None = None,
    ) -> str | None:
        """Prompt the user to pick an option; None on cancel/no UI."""
        self._generation.assert_active()
        return await self._runtime.ui.select(title, options, timeout=timeout)

    async def confirm(
        self,
        title: str,
        message: str,
        *,
        timeout: float | None = None,
    ) -> bool:
        """Ask the user to confirm; True only if confirmed."""
        self._generation.assert_active()
        return await self._runtime.ui.confirm(title, message, timeout=timeout)

    async def input(
        self,
        title: str,
        placeholder: str = "",
        *,
        timeout: float | None = None,
    ) -> str | None:
        """Prompt the user for text; None on cancel/no UI."""
        self._generation.assert_active()
        return await self._runtime.ui.input(title, placeholder, timeout=timeout)

    @property
    def sidebar(self) -> ExtensionSidebar:
        """Return this extension's host-framed sidebar capability."""
        self._generation.assert_active()
        return self._sidebar

    @property
    def components(self) -> ComponentBridge:
        """Return the host widget-hosting capability.

        Using this seam is the one place an extension needs Textual, so an
        extension that reaches it must declare
        ``ExtensionCapabilities(components=True)`` in its module. Straight
        pass-through to the installed UI bridge, which implements the
        :class:`ComponentBridge` members (the TUI hosts real widgets; the
        print-mode bridges are no-ops with ``supports_components == False``).
        Gate widget work on ``context.ui.components.supports_components``.
        A stale facade raises here, before the bridge is ever reachable.
        """
        self._generation.assert_active()
        return cast("ComponentBridge", self._runtime.ui)

    def notify(self, message: str, level: NotifyLevel = "info") -> None:
        """Show a notification in the UI, if one is attached."""
        self._generation.assert_active()
        self._runtime.ui.notify(message, level)

    def suspend(self) -> AbstractContextManager[None]:
        """Pause the UI so an external program can use the terminal."""
        self._generation.assert_active()
        return self._runtime.ui.suspend()


class ExtensionContext:
    """Read-only session context exposed to extensions.

    Every property (trivial reads included, matching Pi's context getters)
    asserts the owning load generation is still active, so a context captured
    before a `/reload` raises :class:`ExtensionError` instead of reading the
    reloaded world.
    """

    def __init__(
        self,
        runtime: ExtensionRuntime,
        generation: ExtensionGeneration | None = None,
        *,
        extension_name: str = "",
    ) -> None:
        self._runtime = runtime
        self._generation = generation if generation is not None else ExtensionGeneration()
        self._ui = ExtensionUi(runtime, self._generation, extension_name=extension_name)

    @property
    def cwd(self) -> Path:
        """Return the session working directory."""
        self._generation.assert_active()
        return self._runtime.session_view.cwd

    @property
    def paths(self) -> BaldricPaths:
        """Return the resolved Baldric filesystem paths for this session."""
        self._generation.assert_active()
        return self._runtime.paths

    @property
    def model(self) -> str:
        """Return the active model name."""
        self._generation.assert_active()
        return self._runtime.session_view.model

    @property
    def provider_name(self) -> str:
        """Return the active provider name."""
        self._generation.assert_active()
        return self._runtime.session_view.provider_name

    @property
    def provider_registry(self) -> DynamicProviderRegistry:
        """Return this generation's process-local provider registry (read-only)."""
        self._generation.assert_active()
        return self._runtime.provider_registry

    @property
    def available_providers(self) -> tuple[str, ...]:
        """Return provider IDs that the active session can call."""
        self._generation.assert_active()
        return tuple(self._runtime.session_view.available_providers)

    @property
    def available_model_choices(self) -> tuple[ModelChoice, ...]:
        """Return provider/model IDs from the active session's runtime view."""
        self._generation.assert_active()
        return cast("tuple[ModelChoice, ...]", self._runtime.session_view.available_model_choices)

    @property
    def inference_provider(self) -> str | None:
        """Return the active Hugging Face inference-provider pin, if any."""
        self._generation.assert_active()
        return self._runtime.session_view.inference_provider

    @property
    def inference_provider_mode(self) -> str:
        """Return whether Hugging Face routing is automatic or explicitly fixed."""
        self._generation.assert_active()
        return self._runtime.session_view.inference_provider_mode

    @property
    def session_id(self) -> str | None:
        """Return the current session id, if the session is indexed."""
        self._generation.assert_active()
        return self._runtime.session_view.session_id

    @property
    def session_name(self) -> str | None:
        """Return the session's human-friendly name, if it has one."""
        self._generation.assert_active()
        return self._runtime.session_view.session_name

    @property
    def thinking_level(self) -> str:
        """Return the active thinking mode for future turns."""
        self._generation.assert_active()
        return self._runtime.session_view.thinking_level

    @property
    def system_prompt(self) -> str:
        """Return the active system prompt."""
        self._generation.assert_active()
        return self._runtime.session_view.system_prompt

    @property
    def shell(self) -> str:
        """Return the shell preference (auto/bash/pwsh/cmd) for this session.

        A child session created from this context should pass it back as
        ``CodingSessionConfig(shell=context.shell)`` so subagents run commands in
        the same shell the user selected.
        """
        self._generation.assert_active()
        return self._runtime.session_view.shell

    @property
    def shell_command_prefix(self) -> str | None:
        """Return the shell command prefix applied to this session's bash tool."""
        self._generation.assert_active()
        return self._runtime.session_view.shell_command_prefix

    @property
    def project_trust_resolution(self) -> ProjectTrustResolution | None:
        """Return the completed project-input trust decision for the session cwd.

        The resolution is a frozen snapshot with the ``trusted`` decision plus
        ``source``/``saved_path`` diagnostics. It is ``None`` only for sessions
        that never resolved trust (for example a bare ``CodingSession`` built
        outside ``CodingSession.load``). During a ``session_start("reload")``
        hook it still reflects the outgoing generation's decision, like every
        other session property read at that point.
        """
        self._generation.assert_active()
        return self._runtime.session_view.project_trust_resolution

    @property
    def project_trusted(self) -> bool:
        """Return whether the session cwd's project inputs were approved.

        A host that constructs child ``CodingSession``s (e.g. subagents) should
        forward this as ``CodingSessionConfig(trust_override="approve")`` when
        ``True`` and ``"decline"`` when ``False``, so children inherit the
        user's decision instead of re-resolving headlessly as untrusted.
        """
        self._generation.assert_active()
        resolution = self._runtime.session_view.project_trust_resolution
        return resolution is not None and resolution.trusted

    @property
    def is_running(self) -> bool:
        """Return whether an agent run is currently active."""
        self._generation.assert_active()
        return self._runtime.session_view.is_running

    @property
    def before_tool_call(self) -> BeforeToolCall | None:
        """Return the harness's tool gate so a child session can inherit it.

        Subagents build their own ``CodingSessionConfig``; without this read they
        would drop the approval gate and let a child run mutating tools without
        the parent's (or the user's) decision.
        """
        self._generation.assert_active()
        return self._runtime.session_view.before_tool_call

    @property
    def transcript(self) -> tuple[AgentMessage, ...]:
        """Return the active-path parent conversation as read-only copies.

        Mirrors the read access Pi extensions get via
        ``ctx.sessionManager.getBranch()``: the user/assistant/tool messages on
        the current branch, with compaction and branch summaries already folded
        in as ``UserMessage`` entries (Baldric has no separate summary message
        type). Each message is deep-copied so an extension mutating a returned
        object cannot corrupt the live session transcript.
        """
        self._generation.assert_active()
        messages = self._runtime.session_view.messages
        return tuple(message.model_copy(deep=True) for message in messages)

    @property
    def has_ui(self) -> bool:
        """Return whether an interactive UI is attached."""
        self._generation.assert_active()
        return self._runtime.ui.has_ui

    @property
    def ui(self) -> ExtensionUi:
        """Return the interactive UI facade (Pi's `ctx.ui`).

        Use `await context.ui.select/confirm/input(...)` to drive dialogs.
        Because command handlers are sync (see the docs), a `/command` that
        needs a dialog should spawn a loop task that awaits `context.ui`.
        """
        self._generation.assert_active()
        return self._ui


class ExtensionAPI:
    """The object handed to each extension's `setup(baldric)` entry point.

    Every method and property asserts the load generation first (Pi's
    ``assertActive`` parity): after `/reload` replaces the registration set,
    a `baldric` object captured by the previous instance raises
    :class:`ExtensionError` on any use instead of silently acting against
    the new world.
    """

    def __init__(
        self,
        runtime: ExtensionRuntime,
        extension_name: str,
        generation: ExtensionGeneration | None = None,
        *,
        source_id: str | None = None,
    ) -> None:
        self._runtime = runtime
        self._extension_name = extension_name
        self._source_id = source_id or f"extension-name:{extension_name}"
        self._generation = generation if generation is not None else ExtensionGeneration()
        self._context = ExtensionContext(
            runtime,
            self._generation,
            extension_name=extension_name,
        )

    @property
    def name(self) -> str:
        """Return this extension's name."""
        self._generation.assert_active()
        return self._extension_name

    @property
    def context(self) -> ExtensionContext:
        """Return read-only session context."""
        self._generation.assert_active()
        return self._context

    def set_inference_provider(self, route: str | None) -> str:
        """Select or reset the active Hugging Face session route."""
        self._generation.assert_active()
        return self._runtime.session_view.set_inference_provider(route)

    async def set_model(self, model: str) -> None:
        """Switch the active session model (ports Pi's ``setModel``).

        The change fires the ``model_select`` event for every extension,
        including this one, and persists the selection the way the ``/model``
        command does.
        """
        self._generation.assert_active()
        await self._runtime.set_model(model)

    async def set_thinking_level(self, level: str) -> str:
        """Switch the active thinking level (ports Pi's ``setThinkingLevel``).

        Returns the level actually applied (the runtime coerces/clamps it). The
        change fires ``thinking_level_select``.
        """
        self._generation.assert_active()
        return await self._runtime.session_view.set_thinking_level(level)

    def register_tool(self, tool: AgentTool) -> None:
        """Register an agent tool (first registration per name wins)."""
        self._generation.assert_active()
        self._runtime.register_tool(self._source_id, self._extension_name, tool)

    def unregister_tool(self, name: str) -> None:
        """Withdraw a tool this extension registered (silent no-op otherwise)."""
        self._generation.assert_active()
        self._runtime.unregister_tool(self._source_id, self._extension_name, name)

    def set_active_tools(self, names: Sequence[str] | None) -> None:
        """Enable only the named tools for future runs (ports Pi's ``setActiveTools``).

        ``None`` re-enables every tool. Disabling is reversible and keeps the
        registration, so an extension can gate a tool per state. The system
        prompt is refreshed because it lists the available tools.
        """
        self._generation.assert_active()
        self._runtime.set_active_tools(names)

    async def execute_tool(
        self,
        name: str,
        arguments: Mapping[str, JSONValue],
        *,
        signal: ToolCancellationToken | None = None,
    ) -> AgentToolResult:
        """Run an active tool through the session pipeline (ports ``ctx.executeTool``).

        ``tool_call``/``tool_result`` hooks and project trust apply exactly as
        for a model-issued call. A tool disabled with :meth:`set_active_tools`
        (or never registered) raises :class:`ExtensionError`.
        """
        self._generation.assert_active()
        return await self._runtime.execute_tool(name, arguments, signal=signal)

    def refresh_system_prompt(self) -> None:
        """Ask the bound session to rebuild its system prompt from registries."""
        self._generation.assert_active()
        self._runtime.request_system_prompt_refresh()

    def register_provider(self, provider: DynamicProvider) -> None:
        """Register or atomically replace this source's dynamic provider layer."""
        self._generation.assert_active()
        self._runtime.register_provider(self._source_id, provider)

    def update_provider(self, provider: DynamicProvider) -> bool:
        """Update this source's provider snapshot while preserving its layer token."""
        self._generation.assert_active()
        return self._runtime.update_provider(self._source_id, provider)

    def register_local_backend(self, backend: LocalBackend) -> None:
        """Register a backend paired with this source's provider layer."""
        self._generation.assert_active()
        self._runtime.register_local_backend(self._source_id, backend)

    def register_command(
        self,
        name: str,
        handler: ExtensionCommandHandler,
        *,
        description: str = "",
        usage: str | None = None,
        aliases: tuple[str, ...] = (),
    ) -> None:
        """Register a slash command backed by this extension."""
        self._generation.assert_active()
        self._runtime.register_command(
            self._source_id,
            self._extension_name,
            name,
            handler,
            description=description,
            usage=usage,
            aliases=aliases,
        )

    def add_prompt_guideline(self, guideline: str) -> None:
        """Add a standalone guideline line to the system prompt.

        Tool-attached guidance belongs on the tool (`prompt_snippet`,
        `prompt_guidelines`); this is for behavioral guidance not tied to
        any tool. Duplicate lines are de-duplicated at prompt build time.
        """
        self._generation.assert_active()
        self._runtime.register_prompt_guideline(self._source_id, self._extension_name, guideline)

    def add_prompt_section(self, title: str | None, body: str) -> None:
        """Append a free-form, optionally titled section to the system prompt.

        Use this for structured, always-on extension context such as procedures,
        paragraphs, and code blocks. Use :meth:`add_prompt_guideline` for one
        behavioral bullet instead.
        """
        self._generation.assert_active()
        self._runtime.register_prompt_section(
            self._source_id,
            self._extension_name,
            title,
            body,
        )

    def on(
        self,
        event: str,
        handler: ExtensionHandler | None = None,
    ) -> Callable[[ExtensionHandler], ExtensionHandler] | ExtensionHandler:
        """Subscribe to an event, directly or as a decorator."""
        self._generation.assert_active()
        if handler is not None:
            self._runtime.subscribe(self._source_id, event, handler)
            return handler

        def decorator(decorated: ExtensionHandler) -> ExtensionHandler:
            self._generation.assert_active()
            self._runtime.subscribe(self._source_id, event, decorated)
            return decorated

        return decorator

    def send_user_message(
        self,
        content: str,
        *,
        deliver_as: DeliverAs = "follow_up",
    ) -> None:
        """Queue a user message for the active or next agent run."""
        self._generation.assert_active()
        self._runtime.send_user_message(content, deliver_as=deliver_as)

    def register_message_renderer(
        self,
        custom_type: str,
        renderer: MessageRenderer,
    ) -> None:
        """Register a renderer for custom messages with this ``custom_type``.

        Ports Pi's ``registerMessageRenderer``: the first registration per
        ``custom_type`` wins. The renderer receives a :class:`CustomMessageView`
        and :class:`MessageRenderOptions` and returns a Rich-markup string; it
        must not return a Textual widget (that keeps extensions TUI-free).
        """
        self._generation.assert_active()
        self._runtime.register_message_renderer(self._source_id, self._extension_name, custom_type, renderer)

    def register_entry_renderer(
        self,
        custom_type: str,
        renderer: EntryRenderer,
    ) -> None:
        """Register a renderer for custom entries with this ``namespace``.

        Ports Pi's ``registerEntryRenderer``: entries are created with
        :meth:`append_entry` and render inside the transcript. The renderer
        receives a :class:`CustomEntryView` and :class:`MessageRenderOptions` and
        returns Rich-markup text (never a Textual widget). First registration per
        ``custom_type`` wins.
        """
        self._generation.assert_active()
        self._runtime.register_entry_renderer(self._source_id, self._extension_name, custom_type, renderer)

    def register_tool_renderer(
        self,
        render_call: ToolCallResolver | None = None,
        render_result: ToolResultResolver | None = None,
    ) -> None:
        """Register tool-call/result render resolvers covering any tool.

        Ports Pi's ``registerToolRenderer``: each resolver receives the tool name
        and a ``next`` callable yielding the lower-priority result (other
        resolvers, then the tool's own renderer, then None). Return ``None`` to
        defer, or a Rich-markup string to take over. At least one of
        ``render_call``/``render_result`` must be given.
        """
        self._generation.assert_active()
        self._runtime.register_tool_renderer(
            self._source_id, self._extension_name, render_call=render_call, render_result=render_result
        )

    def register_markdown_transformer(
        self,
        transformer: MarkdownTransformer,
        *,
        message_types: Sequence[str] = (),
    ) -> None:
        """Register a display-only Markdown transformer (chained, applies in load order).

        Ports Pi's ``registerMarkdownTransformer``. ``message_types`` selects the
        surfaces it runs on (empty = user/assistant/assistant-thinking). The
        transformer is display-only: the session and model context are unchanged.
        """
        self._generation.assert_active()
        self._runtime.register_markdown_transformer(
            self._source_id, self._extension_name, transformer, message_types=tuple(message_types)
        )

    def send_custom_message(
        self,
        content: str,
        *,
        custom_type: str,
        details: dict[str, JSONValue] | None = None,
        deliver_as: DeliverAs = "follow_up",
        trigger_turn: bool = True,
    ) -> None:
        """Send a custom message that renders via a registered renderer.

        Ports Pi's ``sendMessage``: ``content`` still enters LLM context, while
        ``custom_type``/``details`` let a registered renderer format the
        transcript block. With ``trigger_turn`` (the default) the message starts
        a turn when the session is idle, mirroring ``send_user_message``; set it
        to ``False`` to only queue for the next run.
        """
        self._generation.assert_active()
        self._runtime.send_custom_message(
            content,
            custom_type=custom_type,
            details=details,
            deliver_as=deliver_as,
            trigger_turn=trigger_turn,
        )

    async def append_entry(self, namespace: str, data: dict[str, JSONValue]) -> None:
        """Persist extension-owned data to the session as a custom entry."""
        self._generation.assert_active()
        await self._runtime.append_custom_entry(namespace, data)

    async def set_label(self, entry_id: str, label: str | None) -> None:
        """Set or clear a bookmark on an existing session entry."""
        self._generation.assert_active()
        await self._runtime.set_label(entry_id, label)

    def notify(self, message: str, level: NotifyLevel = "info") -> None:
        """Show a notification in the UI, if one is attached."""
        self._generation.assert_active()
        self._runtime.ui.notify(message, level)

    def suspend(self) -> AbstractContextManager[None]:
        """Pause the UI so an external program can use the terminal."""
        self._generation.assert_active()
        return self._runtime.ui.suspend()


@dataclass(slots=True)
class RegisteredExtension:
    """Book-keeping for one loaded extension inside the runtime."""

    name: str
    source_id: str
    path: Path | None
    api: ExtensionAPI
    source: Literal["built-in", "user", "explicit", "project"] = "explicit"
    hidden: bool = False
    handlers: dict[str, list[ExtensionHandler]] = field(default_factory=dict)
    api_version: int = EXTENSION_API_VERSION
    capabilities: ExtensionCapabilities = field(default_factory=ExtensionCapabilities)
