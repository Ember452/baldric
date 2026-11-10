"""TUI event dispatch: the shared registry and the events the UI consumes."""

from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console
from textual.widgets import Static

from baldric.coding.events import (
    AutoRetryEndEvent,
    AutoRetryStartEvent,
    CodingSessionEvent,
    SessionInfoChangedEvent,
    ThinkingLevelChangedEvent,
)
from baldric.coding.events_dispatch import EventDispatcher
from baldric.coding.tui.adapter import INTENTIONAL_NOOP, TuiEventAdapter
from baldric.coding.tui.app import BaldricTuiApp
from baldric.coding.tui.state import TuiState
from baldric.coding.tui.terminal_title import TerminalTitleController
from baldric.coding.tui.widgets import TranscriptMessageWidget
from tests.guards.event_union import coding_session_event_types
from tests.helpers.tui_helpers import FakeSession


class _BareEvent:
    """An event type no TUI dispatcher knows about."""


def _rendered_static(app: BaldricTuiApp, selector: str) -> str:
    console = Console(record=True, width=120, file=StringIO())
    console.print(app.query_one(selector, Static).content)
    return console.export_text()


def test_dispatcher_calls_every_handler_in_registration_order() -> None:
    calls: list[str] = []
    dispatcher = EventDispatcher()
    dispatcher.register(_BareEvent, lambda _: calls.append("first"))
    dispatcher.register(_BareEvent, lambda _: calls.append("second"))

    results = dispatcher.dispatch(_BareEvent())

    assert calls == ["first", "second"]
    assert len(results) == 2


def test_dispatcher_falls_back_only_when_no_handler_is_registered() -> None:
    handled: list[object] = []
    unhandled: list[object] = []
    dispatcher = EventDispatcher(on_unhandled=unhandled.append)
    dispatcher.register(_BareEvent, handled.append)
    unknown = object()

    dispatcher.dispatch(_BareEvent())
    dispatcher.dispatch(unknown)

    assert len(handled) == 1
    assert unhandled == [unknown]


def test_adapter_ignores_event_types_it_has_no_projection_for() -> None:
    state = TuiState()
    adapter = TuiEventAdapter(state)

    adapter.apply(_BareEvent())  # type: ignore[arg-type]

    assert state.running is False
    assert state.items == []


def test_dom_fallback_refreshes_chrome_for_an_unknown_event() -> None:
    app = BaldricTuiApp(FakeSession())
    refreshes: list[None] = []
    app._refresh_chrome = lambda **_: refreshes.append(None)  # type: ignore[method-assign]

    app._dom_dispatcher.dispatch(_BareEvent())

    assert len(refreshes) == 1


def test_no_coding_session_event_reaches_the_dom_unhandled_fallback() -> None:
    """Only the events listed in ``INTENTIONAL_NOOP`` may use the fallback."""
    app = BaldricTuiApp(FakeSession())

    unregistered = coding_session_event_types() - app._dom_dispatcher.registered_types()

    assert unregistered == frozenset(INTENTIONAL_NOOP)


@pytest.mark.anyio
async def test_session_info_changed_event_refreshes_the_session_title() -> None:
    session = FakeSession()
    app = BaldricTuiApp(session)
    writes: list[str] = []
    app._terminal_title = TerminalTitleController(enabled=True, writer=writes.append)

    async with app.run_test() as pilot:
        await pilot.pause()
        session._session_title = "named later"
        await app._apply_streaming_transcript_event(SessionInfoChangedEvent(name="named later"))
        await pilot.pause()

    assert "\x1b]0;τ | named later\x07" in writes


@pytest.mark.anyio
async def test_thinking_level_changed_event_refreshes_model_chrome() -> None:
    session = FakeSession()
    app = BaldricTuiApp(session)

    async with app.run_test() as pilot:
        await pilot.pause()
        assert "(medium)" in _rendered_static(app, "#compact-session-info")
        session.thinking_level = "high"
        session.state.thinking_level = "high"

        await app._apply_streaming_transcript_event(ThinkingLevelChangedEvent(level="high"))
        await pilot.pause()

        assert "(high)" in _rendered_static(app, "#compact-session-info")


@pytest.mark.anyio
async def test_auto_retry_end_settles_the_retry_status_row() -> None:
    app = BaldricTuiApp(FakeSession())

    async def stream(event: CodingSessionEvent) -> None:
        app.adapter.apply(event)
        await app._apply_streaming_transcript_event(event)

    async with app.run_test() as pilot:
        await pilot.pause()
        await stream(
            AutoRetryStartEvent(
                attempt=1,
                max_attempts=3,
                delay_ms=10,
                error_message="Retrying provider request after HTTP 503.",
            )
        )
        await pilot.pause()
        status_widgets = [
            widget for widget in app.query(TranscriptMessageWidget) if widget.item.role == "status"
        ]
        assert [widget.item.text for widget in status_widgets] == [
            "… Retrying provider request after HTTP 503."
        ]

        await stream(AutoRetryEndEvent(success=True, attempt=1))
        await pilot.pause()

        status_widgets = [
            widget for widget in app.query(TranscriptMessageWidget) if widget.item.role == "status"
        ]
        assert status_widgets == []
        assert app.state.items == []
