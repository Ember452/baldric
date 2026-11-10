"""Exact-type event dispatch for frontends that consume coding-session events."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

type EventHandler = Callable[[Any], Any]


class EventDispatcher:
    """Route each event to the handlers registered for its exact concrete type.

    Registration is explicit and exact: ``type(event)`` is looked up in the
    registry, never a base class or a string discriminator, so adding an event
    means adding a registration instead of extending an ``isinstance`` chain.

    ``dispatch`` runs every handler registered for the event type in
    registration order and returns their results. A synchronous consumer
    ignores the results; an asynchronous consumer awaits the awaitable ones, so
    the same registry serves sync projection and async widget updates. Handlers
    may therefore be sync or ``async`` callables.

    ``on_unhandled`` is the fallback for an event type with no registration. It
    fires only when the registry cannot answer for the event, which makes it a
    production safety net rather than a normal code path: the TUI app uses it to
    refresh chrome when a new session event type reaches the frontend before a
    handler lands, and its tests assert that no ``CodingSessionEvent`` type in
    the app's registry reaches it. A silently swallowed event type is worse than
    a redundant chrome refresh.
    """

    def __init__(self, *, on_unhandled: EventHandler | None = None) -> None:
        self._handlers: dict[type[object], list[EventHandler]] = {}
        self._on_unhandled = on_unhandled

    def register(self, event_type: type[object], handler: EventHandler) -> None:
        """Append *handler* for exactly *event_type*, preserving registration order."""
        self._handlers.setdefault(event_type, []).append(handler)

    def handles(self, event_type: type[object]) -> bool:
        """Return whether *event_type* has at least one registered handler."""
        return event_type in self._handlers

    def registered_types(self) -> frozenset[type[object]]:
        """Return every event type with at least one registered handler."""
        return frozenset(self._handlers)

    def dispatch(self, event: object) -> list[object]:
        """Run the handlers for ``type(event)``, or ``on_unhandled`` when there are none.

        Returns each handler's return value in call order so an async consumer
        can await them; a sync consumer ignores the returned list.
        """
        handlers = self._handlers.get(type(event))
        if handlers is None:
            return [] if self._on_unhandled is None else [self._on_unhandled(event)]
        return [handler(event) for handler in handlers]
