"""The TUI must consume every coding-session event through a dispatcher.

The TUI replaced three independent ``isinstance`` chains with explicit
registries. This guard is what keeps a newly added session event from silently
bypassing the frontend until someone notices it is missing on screen: an event
type that is neither projected by ``TuiEventAdapter``, handled by a DOM handler,
nor explained in ``INTENTIONAL_NOOP`` fails here.
"""

from __future__ import annotations

from baldric.runtime.frontends.tui.adapter import INTENTIONAL_NOOP, TuiEventAdapter
from baldric.runtime.frontends.tui.app import DOM_EVENT_HANDLERS, BaldricTuiApp
from baldric.runtime.frontends.tui.state import TuiState
from tests.guards.event_union import coding_session_event_types


def test_every_coding_session_event_has_a_tui_handler() -> None:
    event_types = coding_session_event_types()
    projected = TuiEventAdapter(TuiState()).dispatched_event_types()
    dom_handled = frozenset(DOM_EVENT_HANDLERS)
    missing = event_types - projected - dom_handled - frozenset(INTENTIONAL_NOOP)
    assert missing == frozenset(), (
        "new coding-session event types need a TuiEventAdapter projection handler, a "
        "DOM handler in DOM_EVENT_HANDLERS, or an explained INTENTIONAL_NOOP entry: "
        f"{sorted(event_type.__name__ for event_type in missing)}"
    )


def test_intentional_noop_entries_are_session_events_with_reasons() -> None:
    event_types = coding_session_event_types()
    for event_type, reason in INTENTIONAL_NOOP.items():
        assert event_type in event_types, f"{event_type.__name__} is no longer a session event"
        assert reason.strip(), f"{event_type.__name__} needs a documented reason"
    assert not frozenset(INTENTIONAL_NOOP) & frozenset(DOM_EVENT_HANDLERS)


def test_dom_handler_names_resolve_to_app_methods() -> None:
    for handler_name in DOM_EVENT_HANDLERS.values():
        assert callable(getattr(BaldricTuiApp, handler_name, None)), (
            f"DOM_EVENT_HANDLERS names a missing BaldricTuiApp method: {handler_name}"
        )


def test_union_extraction_sees_agent_and_session_events() -> None:
    event_types = coding_session_event_types()
    names = {event_type.__name__ for event_type in event_types}
    assert {"AgentStartEvent", "SessionInfoChangedEvent", "AutoRetryEndEvent"} <= names
    # Each dispatcher must be non-empty independently; a regression that empties
    # one registry would otherwise pass the union coverage check above.
    assert TuiEventAdapter(TuiState()).dispatched_event_types()
    assert frozenset(DOM_EVENT_HANDLERS)
