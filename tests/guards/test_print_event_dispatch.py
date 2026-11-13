"""The print renderers must declare every coding-session event they consume.

The TUI is guarded by ``tests/guards/test_tui_event_dispatch.py`` because it
dispatches through registries. The non-interactive renderers still dispatch with
``isinstance`` chains, so a newly added session event would silently render
nothing. Each renderer declares ``RENDERED_EVENT_TYPES`` (the session event
classes its ``isinstance`` branches inspect) and ``INTENTIONAL_NOOP`` (every
remaining session event, with a reason it is deliberately not handled).

``INTENTIONAL_NOOP`` means "no dedicated branch", not "dropped": in JSON mode
every event a renderer receives is still serialized. Message classes are payloads
unwrapped from an event, not session events, so they never appear here.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import ModuleType

import pytest

from baldric.runtime.rendering import json as json_renderer
from baldric.runtime.rendering import plain as plain_renderer
from baldric.runtime.rendering import transcript as transcript_renderer
from tests.guards.event_union import coding_session_event_types

RENDERERS: tuple[ModuleType, ...] = (plain_renderer, json_renderer, transcript_renderer)


def _module_label(module: ModuleType) -> str:
    return module.__name__.rsplit(".", 1)[-1]


def _type_name(event_type: object) -> str:
    return getattr(event_type, "__name__", repr(event_type))


def _module_source(module: ModuleType) -> str:
    assert module.__file__ is not None, f"{module.__name__} has no source file"
    return Path(module.__file__).read_text(encoding="utf-8")


def _isinstance_argument_names(module: ModuleType) -> frozenset[str]:
    """Return every class name used as an ``isinstance()`` argument in *module*.

    Walks the whole second argument so a PEP 604 union (``A | B``) and a tuple
    (``(A, B)``) both yield their members; the renderers may use either form.
    """
    names: set[str] = set()
    for node in ast.walk(ast.parse(_module_source(module))):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id != "isinstance" or len(node.args) < 2:
            continue
        for candidate in ast.walk(node.args[1]):
            if isinstance(candidate, ast.Name):
                names.add(candidate.id)
            elif isinstance(candidate, ast.Attribute):
                names.add(candidate.attr)
    return frozenset(names)


@pytest.mark.parametrize("module", RENDERERS, ids=_module_label)
def test_rendered_and_noop_partition_the_session_union(module: ModuleType) -> None:
    event_types = coding_session_event_types()
    rendered = module.RENDERED_EVENT_TYPES
    noop = frozenset(module.INTENTIONAL_NOOP)
    label = _module_label(module)
    assert isinstance(rendered, frozenset), f"{label}.RENDERED_EVENT_TYPES must be a frozenset"
    assert isinstance(module.INTENTIONAL_NOOP, dict), f"{label}.INTENTIONAL_NOOP must be a dict"
    assert rendered & noop == frozenset(), f"{label} declares event types as both rendered and noop"
    assert rendered | noop == event_types, (
        f"{label} must render or explain every coding-session event; "
        f"uncovered: {sorted(_type_name(t) for t in event_types - rendered - noop)}, "
        f"not session events: {sorted(_type_name(t) for t in (rendered | noop) - event_types)}"
    )


def test_intentional_noop_entries_are_session_events_with_reasons() -> None:
    event_types = coding_session_event_types()
    for module in RENDERERS:
        label = _module_label(module)
        for event_type, reason in module.INTENTIONAL_NOOP.items():
            assert event_type in event_types, (
                f"{label}.INTENTIONAL_NOOP lists {_type_name(event_type)}, "
                "which is not a coding-session event"
            )
            assert isinstance(reason, str) and reason.strip(), (
                f"{label}.INTENTIONAL_NOOP needs a reason for {_type_name(event_type)}"
            )


@pytest.mark.parametrize("module", RENDERERS, ids=_module_label)
def test_rendered_event_types_actually_appear_in_an_isinstance(module: ModuleType) -> None:
    label = _module_label(module)
    isinstance_names = _isinstance_argument_names(module)
    for event_type in module.RENDERED_EVENT_TYPES:
        assert getattr(module, event_type.__name__, None) is event_type, (
            f"{label}.RENDERED_EVENT_TYPES lists {event_type.__name__}, "
            "but the module does not reference that class directly"
        )
        assert event_type.__name__ in isinstance_names, (
            f"{label}.RENDERED_EVENT_TYPES claims isinstance() coverage for "
            f"{event_type.__name__}, but the module never dispatches it"
        )


@pytest.mark.parametrize("module", RENDERERS, ids=_module_label)
def test_isinstance_dispatched_session_events_are_declared_rendered(module: ModuleType) -> None:
    event_types = coding_session_event_types()
    label = _module_label(module)
    dispatched: set[type[object]] = set()
    for name in _isinstance_argument_names(module):
        candidate = getattr(module, name, None)
        if isinstance(candidate, type) and candidate in event_types:
            dispatched.add(candidate)
    undeclared = dispatched - module.RENDERED_EVENT_TYPES
    assert not undeclared, (
        f"{label} dispatches session events it does not declare as rendered: "
        f"{sorted(t.__name__ for t in undeclared)}"
    )


def test_each_renderer_declares_its_core_rendered_types() -> None:
    event_types = coding_session_event_types()
    assert event_types, "the CodingSessionEvent union extraction produced no event types"
    for module in RENDERERS:
        label = _module_label(module)
        assert module.RENDERED_EVENT_TYPES, f"{label} declares no rendered event types"
        assert module.INTENTIONAL_NOOP, f"{label} declares no explained noops"
    for module in (plain_renderer, json_renderer):
        names = {event_type.__name__ for event_type in module.RENDERED_EVENT_TYPES}
        assert "MessageEndEvent" in names, f"{_module_label(module)} must inspect MessageEndEvent"
    transcript_names = {event_type.__name__ for event_type in transcript_renderer.RENDERED_EVENT_TYPES}
    assert {"MessageEndEvent", "MessageUpdateEvent", "ToolExecutionStartEvent"} <= transcript_names
