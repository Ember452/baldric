"""Extension-component reconciliation mixed into ``BaldricTuiApp``.

The extension UI subsystem: widgets an extension asks the app to show (slots,
main views, sidebar sections) are reconciled against what the extension runtime
currently declares, with failure quarantine so one bad widget cannot poison the
frame. This lived inline in ``tui/app.py``; it moved here as a mixin
(``ExtensionComponentsMixin``) together with the small handle/bridge classes it
owns, so the app file keeps shrinking. The methods read app state through
``self`` exactly as before, so behaviour is unchanged; ``self`` is typed ``Any``
for the same MRO reason as ``tui/pickers.py``.
"""

from __future__ import annotations

import asyncio
import traceback
from collections.abc import Callable, Coroutine, Sequence
from contextlib import AbstractContextManager, suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Literal, TypeVar

from rich.text import Text
from textual.containers import Container, Vertical
from textual.css.query import NoMatches
from textual.events import Key
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Static

from baldric_agent.types import JSONValue
from baldric_coding.extensions.api import (
    KeyInterceptor,
    MainViewFactory,
    MainViewHandle,
    Placement,
    SidebarContent,
    SlotWidgetContent,
    SlotWidgetFactory,
)
from baldric_coding.tui.screens.extension import (
    ExtensionConfirmScreen,
    ExtensionInputScreen,
    ExtensionSelectScreen,
)
from baldric_coding.tui.widgets import (
    TranscriptView,
    _custom_markup_to_text,
    _sidebar_separator,
)

if TYPE_CHECKING:
    from baldric_coding.session.session import CodingSession
    from baldric_coding.tui.app import BaldricTuiApp
    from baldric_coding.tui.config import TuiTheme

_DialogResult = TypeVar("_DialogResult")

__all__ = [
    "ExtensionComponentsMixin",
    "_DeadMainViewHandle",
    "_MainViewHandle",
    "_SidebarContribution",
    "_TuiExtensionUiBridge",
]


@dataclass(frozen=True, slots=True)
class _SidebarContribution:
    """One extension-owned sidebar section retained for theme rebuilds."""

    title: str
    content: SidebarContent


class _TuiExtensionUiBridge:
    """Route extension UI requests to the running Textual app."""

    _SEVERITIES: ClassVar[dict[str, Literal["information", "warning", "error"]]] = {
        "info": "information",
        "warning": "warning",
        "error": "error",
    }

    def __init__(self, app: BaldricTuiApp) -> None:
        self._app = app

    @property
    def has_ui(self) -> bool:
        """Return True: an interactive TUI is attached."""
        return True

    def notify(self, message: str, level: str = "info") -> None:
        """Show an extension notification through the app's dedupe path."""
        self._app._notify(message, severity=self._SEVERITIES.get(level, "information"))

    def suspend(self) -> AbstractContextManager[None]:
        """Pause the Textual app so an external program can use the terminal."""
        return self._app.suspend()

    async def select(
        self,
        title: str,
        options: Sequence[str],
        *,
        timeout: float | None = None,
    ) -> str | None:
        """Show a modal picker; return the choice, or None on cancel/timeout."""
        theme = self._app.tui_settings.resolved_theme
        screen: ModalScreen[str | None] = ExtensionSelectScreen(title, options, theme=theme)
        return await self._run_dialog(screen, default=None, timeout=timeout)

    async def confirm(
        self,
        title: str,
        message: str,
        *,
        timeout: float | None = None,
    ) -> bool:
        """Show a modal confirmation; True only if confirmed."""
        theme = self._app.tui_settings.resolved_theme
        screen: ModalScreen[bool] = ExtensionConfirmScreen(title, message, theme=theme)
        return await self._run_dialog(screen, default=False, timeout=timeout)

    async def input(
        self,
        title: str,
        placeholder: str = "",
        *,
        timeout: float | None = None,
    ) -> str | None:
        """Show a modal text prompt; return the text, or None on cancel/timeout."""
        theme = self._app.tui_settings.resolved_theme
        screen: ModalScreen[str | None] = ExtensionInputScreen(title, placeholder, theme=theme)
        return await self._run_dialog(screen, default=None, timeout=timeout)

    # -- component seam -- pass-through to the app ----------------------------

    @property
    def supports_components(self) -> bool:
        """Return True: a Textual TUI can host extension widgets."""
        return True

    @property
    def theme(self) -> TuiTheme:
        """Return the live TUI theme handed to widget factories."""
        return self._app.tui_settings.resolved_theme

    def get_prompt_text(self) -> str:
        """Return the current prompt-editor text (Pi's getEditorText).

        Interceptors do not need this — the host passes the prompt text as
        their second argument; it exists for reads outside the key path.
        """
        return self._app._current_prompt_text()

    def request_render(self) -> None:
        """Re-render mounted extension widgets (analog of Pi's requestRender)."""
        self._app._refresh_extension_components()

    def set_slot_widget(
        self,
        key: str,
        content: SlotWidgetContent | None,
        *,
        placement: Placement = "above_prompt",
    ) -> None:
        """Mount or remove an extension slot widget by key (factory or lines)."""
        self._app._set_extension_slot_widget(key, content, placement)

    def open_main_view(self, factory: MainViewFactory) -> MainViewHandle:
        """Open a full main-area extension view (display-toggled, not modal)."""
        return self._app._open_extension_main_view(factory)

    def register_key_interceptor(self, handler: KeyInterceptor) -> Callable[[], None]:
        """Register a pre-dispatch key hook; return an unsubscribe callable.

        Ports Pi's ``onTerminalInput``. The handler is consulted in
        ``BaldricTuiApp.on_event`` before Textual's app-level priority bindings and
        before the focused widget receives the key, so it can own navigation
        keys (``up``/``down``/``tab``/…) that baldric otherwise binds with
        ``priority=True``. Because it fires for EVERY main-screen key regardless
        of which widget holds focus, the handler MUST self-gate (e.g. on the
        prompt text and its own state) and return ``True`` only for keys it
        actually consumes. It is never consulted while a modal screen (dialog,
        picker, command palette) is on top.
        """
        return self._app._register_extension_key_interceptor(handler)

    @property
    def supports_sidebar(self) -> bool:
        """Return whether the configured TUI sidebar can host sections."""
        return self._app.tui_settings.sidebar_position != "off"

    def set_sidebar_section(
        self,
        extension_name: str,
        key: str,
        *,
        title: str,
        content: SidebarContent,
    ) -> None:
        """Add or replace one host-framed extension sidebar section."""
        self._app._set_extension_sidebar_section(
            extension_name,
            key,
            title=title,
            content=content,
        )

    def remove_sidebar_section(self, extension_name: str, key: str) -> None:
        """Remove one extension-owned sidebar section."""
        self._app._remove_extension_sidebar_section(extension_name, key)

    def clear_components(self) -> None:
        """Tear down all extension-owned UI (runtime-driven: /reload, rebind)."""
        self._app._clear_extension_components()

    async def _run_dialog(
        self,
        screen: ModalScreen[_DialogResult],
        *,
        default: _DialogResult,
        timeout: float | None,
    ) -> _DialogResult:
        """Push a modal and await its dismissal via a callback-resolved future.

        Uses ``push_screen(screen, callback)`` + an ``asyncio.Future`` rather
        than ``push_screen_wait`` (which requires a Textual worker context);
        this pattern works from any coroutine on the app's event loop,
        including a task spawned by a sync ``/command`` handler. On ``timeout``
        (seconds) the dialog auto-dismisses and the no-op ``default`` returns.
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future[_DialogResult] = loop.create_future()

        def _resolve(result: _DialogResult | None) -> None:
            # Textual passes None when a screen is dismissed with no value;
            # map that (and any explicit cancel) to the no-op default.
            if not future.done():
                future.set_result(default if result is None else result)

        self._app.push_screen(screen, _resolve)
        if timeout is None:
            return await future
        try:
            return await asyncio.wait_for(future, timeout)
        except TimeoutError:
            # `Screen.dismiss` only works while the dialog is the top screen.
            # Known limitation: if another screen was pushed on top before the
            # timeout fired, the stale dialog stays on the stack (its future
            # result is discarded by `_resolve` racing `future.done()`) until
            # the covering screen closes and the user dismisses it manually.
            if screen.is_current:
                with suppress(Exception):
                    screen.dismiss(default)
            return default


class _MainViewHandle:
    """Host-side handle to an open extension main view.

    ``close(result)`` is idempotent and routes back to the app, which unmounts
    the widget and restores the main transcript; it also resolves ``wait()``
    with ``result`` (Pi's ``done(result)``). Every other teardown path the host
    owns — session rebind, quarantine, being superseded by a later
    ``open_main_view`` — resolves ``wait()`` with ``None`` via
    :meth:`_resolve`, so an awaiting extension task never hangs.
    """

    def __init__(self, app: BaldricTuiApp, result: asyncio.Future[object | None]) -> None:
        self._app = app
        self._open = True
        self.widget: Widget | None = None
        # Created on the app's event loop at open time; resolved exactly once by
        # the first teardown (close/clear/quarantine/supersede) to wake wait().
        self._result = result

    def close(self, result: object | None = None) -> None:
        """Close the view, resolving ``wait()`` with ``result`` (safe to repeat)."""
        if not self._open:
            return
        self._open = False
        self._resolve(result)
        self._app._close_extension_main_view(self)

    def _resolve(self, result: object | None) -> None:
        """Resolve the pending ``wait()`` future once; later calls are no-ops."""
        if not self._result.done():
            self._result.set_result(result)

    async def wait(self) -> object | None:
        """Await teardown and return the ``close`` result (``None`` if cleared)."""
        return await self._result

    @property
    def is_open(self) -> bool:
        """Return whether the view is still open."""
        return self._open


class _DeadMainViewHandle:
    """A no-op main-view handle returned when a view could not be opened."""

    def close(self, result: object | None = None) -> None:
        """Do nothing: there is no view to close (``result`` is ignored)."""

    async def wait(self) -> object | None:
        """Return None immediately: a dead handle never opens a view."""
        return None

    @property
    def is_open(self) -> bool:
        """Return False: a dead handle is never open."""
        return False


class ExtensionComponentsMixin:
    """Extension slot/sidebar/main-view reconciliation for ``BaldricTuiApp``."""

    # State these methods own. Declared here with the app's authoritative types so
    # the mixin's assignments do not narrow the annotations in ``BaldricTuiApp``.
    _sidebar_visibility_override: bool | None
    _extension_main_view: _MainViewHandle | None
    _extension_main_view_mounted: Widget | None

    def _connect_extension_runtime(self: Any, session: CodingSession) -> None:
        """Give the extension runtime a UI bridge and an idle-run entry point."""
        runtime = getattr(session, "extension_runtime", None)
        if runtime is None:
            return
        # Force-clear any extension widgets before installing the new bridge.
        # This runs once, at construction; later teardowns (/reload, resume,
        # new) come through the installed bridge's clear_components(), driven
        # by the runtime, so extension widgets and key interceptors never
        # survive a world they were mounted in.
        self._clear_extension_components()
        runtime.set_ui_bridge(_TuiExtensionUiBridge(self))
        runtime.set_turn_requested_callback(self._on_extension_turn_requested)
        # Let the transcript render custom messages via registered renderers.
        self.state.custom_renderer = runtime.render_custom_message
        # Let tool calls render through their tool's render_call, if any.
        self.state.tool_call_renderer = runtime.render_tool_call
        # And tool results through their tool's render_result, if any.
        self.state.tool_result_renderer = runtime.render_tool_result

    def _on_extension_turn_requested(
        self: Any,
        content: str,
        custom_type: str | None = None,
        details: dict[str, JSONValue] | None = None,
    ) -> None:
        """Deliver an extension message through the serialized prompt path."""
        self.call_later(self._deliver_extension_message, content, custom_type, details)

    async def _deliver_extension_message(
        self: Any,
        content: str,
        custom_type: str | None = None,
        details: dict[str, JSONValue] | None = None,
    ) -> None:
        if self.session.is_running or self._prompt_worker is not None:
            # A run started while the delivery was in flight; drain with it.
            queue_follow_up = getattr(self.session, "queue_follow_up_message", None)
            if callable(queue_follow_up):
                queue_follow_up(content, custom_type=custom_type, details=details)
            return
        await self._submit_prompt(content, source="extension", custom_type=custom_type, details=details)

    def _register_extension_key_interceptor(self: Any, handler: KeyInterceptor) -> Callable[[], None]:
        """Register a pre-dispatch key interceptor; return an unsubscribe fn."""
        self._extension_key_interceptors.append(handler)

        def unsubscribe() -> None:
            with suppress(ValueError):
                self._extension_key_interceptors.remove(handler)

        return unsubscribe

    def _run_extension_key_interceptors(self: Any, event: Key, text: str) -> bool:
        """Consult interceptors; return True if one consumed the key.

        Each call is guarded: a raising interceptor is diagnosed once and
        treated as "not consumed", so a broken interceptor degrades to normal
        typing rather than a dead prompt.
        """
        for interceptor in tuple(self._extension_key_interceptors):
            try:
                if interceptor(event, text):
                    return True
            except Exception as exc:  # noqa: BLE001 - isolation boundary
                # Notify like the other failure classes so a broken interceptor
                # is not silently invisible, and dedup per-interceptor so a
                # second faulty handler still gets diagnosed.
                self._record_extension_component_failure(
                    f"key_interceptor:{id(interceptor)}", exc, notify=True
                )
        return False

    def _schedule_extension_swap(self: Any, coro: Coroutine[object, object, None]) -> None:
        """Run a slot/main-view reconcile coroutine on the app loop.

        The task is retained until it finishes so it cannot be garbage-collected
        mid-flight (asyncio only holds a weak reference). If there is no running
        loop (only possible outside a live TUI), the coroutine is closed rather
        than left un-awaited.
        """
        try:
            task = asyncio.ensure_future(coro)
        except RuntimeError:  # no running loop — not a live TUI
            coro.close()
            return
        self._extension_swap_tasks.add(task)
        task.add_done_callback(self._extension_swap_tasks.discard)

    @staticmethod
    def _string_slot_widget(lines: Sequence[str]) -> Static:
        """Build a slot ``Static`` from display lines (Rich markup, safe fallback).

        Joins ``lines`` with newlines and parses them as Rich markup; if the
        markup is malformed the literal text is shown instead, mirroring the
        custom-message renderer's guard so a bad string never crashes the TUI.
        """
        content = "\n".join(lines)
        return Static(_custom_markup_to_text(content))

    def _set_extension_slot_widget(
        self: Any,
        key: str,
        content: SlotWidgetContent | None,
        placement: Placement,
    ) -> None:
        """Mount an extension widget into a prompt-adjacent slot, or unmount it.

        ``content`` is a ``factory(theme)`` callable, a list of display lines
        the host renders into a ``Static``, or ``None`` to unmount. The string
        form is normalized into a factory here so the reconcile/quarantine/
        replace machinery below is untouched.

        The intended widget is recorded synchronously so mid-swap reads (clear,
        quarantine, refresh) see what *should* occupy the slot; the actual
        mount/unmount runs on a serialized continuation so a deferred remove()
        of a same-id widget fully drains before the replacement mounts (else the
        DOM briefly holds two widgets with one id -> ``DuplicateIds``).
        """
        factory: SlotWidgetFactory | None
        if content is None:
            factory = None
        elif callable(content):
            # Check callable() first: a Sequence[str] test must never swallow a
            # factory (and a factory is not a Sequence).
            factory = content
        else:
            # A plain list of display lines: build the widget host-side so the
            # extension needs no Textual import. A bare str is treated as one
            # line (never split into characters).
            lines = [content] if isinstance(content, str) else list(content)
            factory = lambda _theme: self._string_slot_widget(lines)  # noqa: E731
        new_widget: Widget | None = None
        if factory is not None:
            try:
                new_widget = factory(self.tui_settings.resolved_theme)
            except Exception as exc:  # noqa: BLE001 - isolation boundary
                self._record_extension_component_failure(f"slot:{key}", exc, notify=True)
                return
        slot_id = "above-prompt-slot" if placement == "above_prompt" else "below-prompt-slot"
        if new_widget is None:
            self._extension_slot_widgets.pop(key, None)
            self._extension_slot_slot_ids.pop(key, None)
        else:
            self._extension_slot_widgets[key] = new_widget
            self._extension_slot_slot_ids[key] = slot_id
        self._schedule_extension_swap(self._reconcile_slot(key))

    async def _reconcile_slot(self: Any, key: str) -> None:
        """Make the mounted slot widget match the intended target (serialized).

        Reads the *live* target each time (not a snapshot), so a burst of set
        calls collapses to "last writer wins": the first continuation removes the
        stale mount, later ones find the target already satisfied and no-op.
        """
        lock = self._extension_slot_locks.setdefault(key, asyncio.Lock())
        async with lock:
            target = self._extension_slot_widgets.get(key)
            mounted = self._extension_slot_mounted.get(key)
            if mounted is not None and mounted is not target:
                with suppress(Exception):
                    await mounted.remove()
                if self._extension_slot_mounted.get(key) is mounted:
                    self._extension_slot_mounted.pop(key, None)
            # Re-read after the await; the target may have changed meanwhile.
            target = self._extension_slot_widgets.get(key)
            if target is None or self._extension_slot_mounted.get(key) is target:
                return
            slot_id = self._extension_slot_slot_ids.get(key, "below-prompt-slot")
            try:
                self.query_one(f"#{slot_id}", Container).mount(target)
            except Exception as exc:  # noqa: BLE001 - isolation boundary
                if self._extension_slot_widgets.get(key) is target:
                    self._extension_slot_widgets.pop(key, None)
                    self._extension_slot_slot_ids.pop(key, None)
                self._record_extension_component_failure(f"slot:{key}", exc, notify=True)
                return
            self._extension_slot_mounted[key] = target

    def _build_extension_sidebar_widget(
        self: Any,
        owner: tuple[str, str],
        contribution: _SidebarContribution,
        *,
        theme: TuiTheme,
    ) -> Widget | None:
        """Build one host-framed sidebar section, isolating its body factory."""
        content = contribution.content
        try:
            if callable(content):
                body = content(theme)
            else:
                lines = [content] if isinstance(content, str) else list(content)
                body = self._string_slot_widget(lines)
            if not isinstance(body, Widget):
                raise TypeError("sidebar factory must return a Textual Widget")
            header = Text(contribution.title, style=f"bold {theme.prompt_text}")
            return Vertical(
                Static(_sidebar_separator(theme=theme), classes="sidebar-separator"),
                Static(header, classes="extension-sidebar-title"),
                Container(body, classes="extension-sidebar-body"),
                classes="extension-sidebar-section",
            )
        except Exception as exc:  # noqa: BLE001 - isolation boundary
            extension_name, key = owner
            self._record_extension_component_failure(
                f"sidebar:{extension_name}:{key}",
                exc,
                notify=True,
                extension_name=extension_name,
            )
            return None

    def _set_extension_sidebar_section(
        self: Any,
        extension_name: str,
        key: str,
        *,
        title: str,
        content: SidebarContent,
    ) -> None:
        """Add or update a sidebar contribution while preserving key order."""
        if self.tui_settings.sidebar_position == "off":
            return
        owner = (extension_name, key)
        normalized_content: SidebarContent
        if callable(content):
            normalized_content = content
        elif isinstance(content, str):
            normalized_content = (content,)
        else:
            normalized_content = tuple(content)
        contribution = _SidebarContribution(title=title, content=normalized_content)
        theme = self.tui_settings.resolved_theme
        previous = self._extension_sidebar_contributions.get(owner)
        if previous == contribution and self._extension_sidebar_theme == theme:
            return
        mounted = self._extension_sidebar_mounted.get(owner)
        target = self._extension_sidebar_widgets.get(owner)
        if (
            previous is not None
            and not callable(previous.content)
            and not callable(normalized_content)
            and mounted is not None
            and mounted is target
            and self._extension_sidebar_theme == theme
        ):
            try:
                header = Text(title, style=f"bold {theme.prompt_text}")
                mounted.query_one(".extension-sidebar-title", Static).update(header)
                body = mounted.query_one(".extension-sidebar-body", Container).query_one(Static)
                body.update(_custom_markup_to_text("\n".join(normalized_content)))
            except Exception as exc:  # noqa: BLE001 - isolation boundary
                self._record_extension_component_failure(
                    f"sidebar:{extension_name}:{key}",
                    exc,
                    notify=True,
                    extension_name=extension_name,
                )
                return
            self._extension_sidebar_contributions[owner] = contribution
            return
        widget = self._build_extension_sidebar_widget(owner, contribution, theme=theme)
        if widget is None:
            return
        self._extension_sidebar_contributions[owner] = contribution
        self._extension_sidebar_widgets[owner] = widget
        self._extension_sidebar_theme = theme
        self._schedule_extension_swap(self._reconcile_sidebar())

    def _remove_extension_sidebar_section(self: Any, extension_name: str, key: str) -> None:
        """Forget and unmount one extension-owned sidebar contribution."""
        owner = (extension_name, key)
        if owner not in self._extension_sidebar_contributions:
            return
        self._extension_sidebar_contributions.pop(owner, None)
        self._extension_sidebar_widgets.pop(owner, None)
        self._schedule_extension_swap(self._reconcile_sidebar())

    def _rebuild_extension_sidebar_sections(self: Any, *, theme: TuiTheme) -> None:
        """Recreate sidebar factories for a changed live theme."""
        if self.tui_settings.sidebar_position == "off":
            return
        changed = False
        for owner, contribution in tuple(self._extension_sidebar_contributions.items()):
            widget = self._build_extension_sidebar_widget(owner, contribution, theme=theme)
            if widget is not None:
                self._extension_sidebar_widgets[owner] = widget
                changed = True
        self._extension_sidebar_theme = theme
        if changed:
            self._schedule_extension_swap(self._reconcile_sidebar())

    async def _reconcile_sidebar(self: Any) -> None:
        """Mount sidebar sections in registration order after removals drain."""
        async with self._extension_sidebar_lock:
            target_items = tuple(self._extension_sidebar_widgets.items())
            mounted_items = tuple(self._extension_sidebar_mounted.items())
            if mounted_items == target_items:
                return
            try:
                slot = self.query_one("#sidebar-extension-sections", Container)
            except NoMatches:
                return
            # Remove only stale roots. An unchanged Textual widget cannot be
            # removed and mounted again: removal prunes its composed children.
            # Keeping unchanged roots also avoids rerunning unrelated factories.
            for owner, mounted in mounted_items:
                if self._extension_sidebar_widgets.get(owner) is mounted:
                    continue
                with suppress(Exception):
                    await mounted.remove()
                if self._extension_sidebar_mounted.get(owner) is mounted:
                    self._extension_sidebar_mounted.pop(owner, None)
            # Re-read after awaits: rapid updates collapse to the latest target.
            target_items = tuple(self._extension_sidebar_widgets.items())
            for index, (owner, target) in enumerate(target_items):
                if self._extension_sidebar_mounted.get(owner) is target:
                    continue
                later_mounted = next(
                    (
                        self._extension_sidebar_mounted.get(later_owner)
                        for later_owner, _ in target_items[index + 1 :]
                        if self._extension_sidebar_mounted.get(later_owner) is not None
                    ),
                    None,
                )
                try:
                    await slot.mount(target, before=later_mounted)
                except Exception as exc:  # noqa: BLE001 - isolation boundary
                    extension_name, key = owner
                    if self._extension_sidebar_widgets.get(owner) is target:
                        self._extension_sidebar_widgets.pop(owner, None)
                        self._extension_sidebar_contributions.pop(owner, None)
                    self._record_extension_component_failure(
                        f"sidebar:{extension_name}:{key}",
                        exc,
                        notify=True,
                        extension_name=extension_name,
                    )
                    continue
                self._extension_sidebar_mounted[owner] = target
            self._extension_sidebar_mounted = {
                owner: target
                for owner, target in target_items
                if self._extension_sidebar_mounted.get(owner) is target
            }

    def _open_extension_main_view(self: Any, factory: MainViewFactory) -> MainViewHandle:
        """Open a display-toggled main-area view mounting ``factory(handle, theme)``.

        Prompt focus is intentionally left where it is (the extension widget can
        focus its own composer), so a registered key interceptor keeps firing
        while the prompt is focused and can close the view on Esc.

        The handle is returned synchronously (the factory needs it and callers
        store it at once), but the mount is sequenced after any previous view's
        remove() drains, so switching views never collides on the shared main
        slot. ``is_open`` reports the *intended* state: the new handle is open
        the instant it is returned even though its widget mounts a tick later.
        """
        handle = _MainViewHandle(self, asyncio.get_event_loop().create_future())
        try:
            widget = factory(handle, self.tui_settings.resolved_theme)
        except Exception as exc:  # noqa: BLE001 - isolation boundary
            self._record_extension_component_failure("main_view", exc, notify=True)
            # Nothing awaits this handle (the extension gets the dead one), but
            # resolve it anyway so no future leaks unresolved.
            handle._resolve(None)
            return _DeadMainViewHandle()
        handle.widget = widget
        previous = self._extension_main_view
        if previous is not None and previous is not handle:
            # Superseded (last writer wins): its close() becomes a no-op so a
            # stale Esc/unmount can't tear down the view that replaced it, and
            # its pending wait() resolves with None.
            self._release_main_view_handle(previous)
        self._extension_main_view = handle
        self._schedule_extension_swap(self._reconcile_main_view())
        return handle

    async def _reconcile_main_view(self: Any) -> None:
        """Make the mounted main view match the intended handle (serialized)."""
        async with self._extension_main_view_lock:
            target = self._extension_main_view
            target_widget = target.widget if target is not None else None
            mounted = self._extension_main_view_mounted
            if mounted is not None and mounted is not target_widget:
                with suppress(Exception):
                    await mounted.remove()
                if self._extension_main_view_mounted is mounted:
                    self._extension_main_view_mounted = None
            # Re-read after the await.
            target = self._extension_main_view
            target_widget = target.widget if target is not None else None
            if target_widget is not None and self._extension_main_view_mounted is not target_widget:
                try:
                    slot = self.query_one("#main-slot", Container)
                    slot.mount(target_widget)
                except Exception as exc:  # noqa: BLE001 - isolation boundary
                    if self._extension_main_view is target:
                        self._extension_main_view = None
                    self._release_main_view_handle(target)
                    self._record_extension_component_failure("main_view", exc, notify=True)
                    self._restore_main_transcript()
                    return
                self._extension_main_view_mounted = target_widget
                with suppress(NoMatches):
                    self.query_one("#transcript", TranscriptView).display = False
                slot.display = True
            elif self._extension_main_view is None and self._extension_main_view_mounted is None:
                # A close (target cleared) with nothing left to show.
                self._restore_main_transcript()

    def _close_extension_main_view(self: Any, handle: _MainViewHandle) -> None:
        """Unmount a main view and restore the main transcript (sequenced)."""
        if self._extension_main_view is not handle:
            return
        self._extension_main_view = None
        self._schedule_extension_swap(self._reconcile_main_view())

    def _refresh_extension_components(self: Any) -> None:
        """Re-render all mounted extension widgets (analog of requestRender)."""
        for widget in (
            *self._extension_slot_widgets.values(),
            *self._extension_sidebar_widgets.values(),
        ):
            with suppress(Exception):
                widget.refresh()
        handle = self._extension_main_view
        if handle is not None and handle.widget is not None:
            with suppress(Exception):
                handle.widget.refresh()

    def _clear_extension_components(self: Any) -> None:
        """Force-clear every tracked extension widget, view, and interceptor.

        The runtime drives this through the UI bridge on `/reload` and session
        rebinds (resume/new); it also runs on app teardown, so a leaked
        extension widget never survives a session switch. Intent is cleared
        synchronously — mid-swap reads and in-flight continuations then see
        empty state — while the actual unmounts run on the same serialized
        per-key reconciles as ordinary swaps, so a clear followed immediately
        by a re-mount of a same-id widget (a session_start handler re-mounting
        after a rebind) can never hold two widgets with one id
        (``DuplicateIds``).
        """
        slot_keys = {*self._extension_slot_widgets, *self._extension_slot_mounted}
        self._extension_slot_widgets.clear()
        self._extension_slot_slot_ids.clear()
        for key in slot_keys:
            self._schedule_extension_swap(self._reconcile_slot(key))
        self._extension_sidebar_contributions.clear()
        self._extension_sidebar_widgets.clear()
        self._extension_sidebar_theme = None
        self._schedule_extension_swap(self._reconcile_sidebar())
        handle = self._extension_main_view
        self._extension_main_view = None
        self._release_main_view_handle(handle)
        self._schedule_extension_swap(self._reconcile_main_view())
        self._extension_key_interceptors.clear()
        # A recurring failure context must notify again in the new world.
        self._extension_component_failures_reported.clear()

    def _tracked_extension_widgets(self: Any) -> tuple[Widget, ...]:
        """Return every extension widget the host currently tracks (intended or mounted)."""
        widgets: list[Widget] = []
        seen: set[int] = set()
        for widget in (
            *self._extension_slot_widgets.values(),
            *self._extension_slot_mounted.values(),
            *self._extension_sidebar_widgets.values(),
            *self._extension_sidebar_mounted.values(),
        ):
            if id(widget) not in seen:
                seen.add(id(widget))
                widgets.append(widget)
        handle = self._extension_main_view
        main_widgets = (
            handle.widget if handle is not None else None,
            self._extension_main_view_mounted,
        )
        for main_widget in main_widgets:
            if main_widget is not None and id(main_widget) not in seen:
                seen.add(id(main_widget))
                widgets.append(main_widget)
        return tuple(widgets)

    def _extension_root_for(self: Any, widget: Widget, tracked: tuple[Widget, ...]) -> Widget | None:
        """Return the tracked extension root that owns ``widget``, if any."""
        node: Widget | None = widget
        while node is not None:
            for root in tracked:
                if node is root:
                    return root
            node = node.parent if isinstance(node.parent, Widget) else None
        return None

    def _quarantine_extension_widget(self: Any, error: BaseException) -> bool:
        """Remove the tracked extension widget implicated in ``error``.

        Returns True when a culprit was found and torn down (so the app can
        swallow the exception and stay alive), False otherwise (so core bugs
        still surface). Textual runs ``render`` on the compositor's own reflow
        loop, so a child's render/compose/on_mount crash cannot be caught at the
        mount site; walking the traceback for a frame owned by a tracked widget
        is the only handle we get.
        """
        tracked = self._tracked_extension_widgets()
        if not tracked:
            return False
        tb = error.__traceback__
        culprit: Widget | None = None
        while tb is not None:
            candidate = tb.tb_frame.f_locals.get("self")
            if isinstance(candidate, Widget):
                root = self._extension_root_for(candidate, tracked)
                if root is not None:
                    culprit = root
                    break
            tb = tb.tb_next
        if culprit is None:
            return False
        # Suppress the ghost first: a widget that crashed in on_mount never
        # finished mounting, so remove() cannot fully prune it, but hiding and
        # disabling it makes it inert and invisible. A render-crash widget
        # removes cleanly. Either way the app keeps running.
        with suppress(Exception):
            culprit.display = False
        with suppress(Exception):
            culprit.disabled = True
        sidebar_owner: tuple[str, str] | None = None
        if (
            self._extension_main_view is not None and self._extension_main_view.widget is culprit
        ) or self._extension_main_view_mounted is culprit:
            if self._extension_main_view_mounted is culprit:
                self._extension_main_view_mounted = None
            handle = self._extension_main_view
            self._extension_main_view = None
            self._release_main_view_handle(handle)
            with suppress(Exception):
                culprit.remove()
            self._restore_main_transcript()
        else:
            sidebar_owner = next(
                (
                    owner
                    for owner, widget in (
                        *self._extension_sidebar_widgets.items(),
                        *self._extension_sidebar_mounted.items(),
                    )
                    if widget is culprit
                ),
                None,
            )
            if sidebar_owner is not None:
                self._extension_sidebar_widgets.pop(sidebar_owner, None)
                self._extension_sidebar_mounted.pop(sidebar_owner, None)
                self._extension_sidebar_contributions.pop(sidebar_owner, None)
            else:
                for tracker in (self._extension_slot_widgets, self._extension_slot_mounted):
                    key = next((k for k, w in tracker.items() if w is culprit), None)
                    if key is not None:
                        tracker.pop(key, None)
            with suppress(Exception):
                culprit.remove()
        extension_name = sidebar_owner[0] if sidebar_owner else None
        context = (
            f"sidebar:{sidebar_owner[0]}:{sidebar_owner[1]}" if sidebar_owner else f"render:{id(culprit)}"
        )
        self._record_extension_component_failure(
            context,
            error,
            notify=True,
            extension_name=extension_name,
        )
        return True

    def _record_extension_component_failure(
        self: Any,
        context: str,
        error: BaseException,
        *,
        notify: bool = False,
        extension_name: str | None = None,
    ) -> None:
        """Diagnose an extension-component failure once per context.

        The notification carries a short exception summary so the failure is
        identifiable at a glance; the full traceback goes to the app log for a
        post-mortem (the two together are what let us pin the deferred-remove
        ``DuplicateIds`` race).
        """
        # Always log the traceback, even on a duplicate context, so a repeating
        # failure leaves a full trail.
        with suppress(Exception):
            self.log.error(
                f"Extension component failed ({context}):\n"
                + "".join(traceback.format_exception(type(error), error, error.__traceback__))
            )
        if context in self._extension_component_failures_reported:
            return
        self._extension_component_failures_reported.add(context)
        if extension_name is not None:
            runtime = getattr(self.session, "extension_runtime", None)
            if runtime is not None:
                runtime.record_ui_failure(extension_name, context, error)
        if notify:
            summary = f"{type(error).__name__}: {error}"
            if len(summary) > 120:
                summary = summary[:117] + "..."
            self._notify(
                f"An extension component failed ({context}) and was removed ({summary}).",
                severity="error",
            )

    def _apply_sidebar_position(self: Any) -> None:
        """Apply the configured (or off-setting fallback) sidebar position."""
        pos = self.tui_settings.sidebar_position
        # A configured ``off`` has no prior visible position, so an explicit
        # session-only show uses the normal right-hand placement.
        show_right = pos == "right" or (pos == "off" and self._sidebar_visibility_override is True)
        self.set_class(show_right, "-sidebar-right")

    def _toggle_sidebar_visibility(self: Any) -> None:
        """Toggle sidebar visibility without changing durable TUI settings."""
        currently_visible = not self.has_class("-hide-sidebar")
        self._sidebar_visibility_override = not currently_visible
        self._apply_sidebar_position()
        self._update_responsive_layout(self.size.width, self.size.height)
        state = "shown" if self._sidebar_visibility_override else "hidden"
        self._notify(f"Sidebar {state} for this session.")
