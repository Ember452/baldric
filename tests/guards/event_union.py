"""AST extraction of the concrete event types in a PEP 695 union alias.

The event unions are nested ``type`` aliases (``CodingSessionEvent`` ->
``AgentEvent | SessionOwnEvent``) whose values are evaluated lazily, so the
runtime ``typing`` helpers cannot see through them. Walking the source keeps
this guard independent of evaluation order and makes a new union member visible
before any frontend imports it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import baldric.agent.events as agent_events
import baldric.runtime.events as coding_events

ROOT = Path(__file__).resolve().parents[2]
EVENT_SOURCES = (
    ROOT / "src" / "baldric" / "agent" / "events.py",
    ROOT / "src" / "baldric" / "runtime" / "events.py",
)


def _alias_definitions(path: Path) -> tuple[dict[str, ast.expr], set[str]]:
    aliases: dict[str, ast.expr] = {}
    classes: set[str] = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.ClassDef):
            classes.add(node.name)
        elif isinstance(node, ast.TypeAlias):
            aliases[node.name.id] = node.value
    return aliases, classes


def union_member_names(alias_name: str, *, sources: tuple[Path, ...] = EVENT_SOURCES) -> frozenset[str]:
    """Return every class name reachable from *alias_name* through type aliases."""
    aliases: dict[str, ast.expr] = {}
    classes: set[str] = set()
    for source in sources:
        source_aliases, source_classes = _alias_definitions(source)
        aliases.update(source_aliases)
        classes.update(source_classes)
    if alias_name not in aliases:
        raise LookupError(f"unknown type alias: {alias_name}")

    pending = [alias_name]
    seen: set[str] = set()
    members: set[str] = set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        for child in ast.walk(aliases[name]):
            if not isinstance(child, ast.Name):
                continue
            if child.id in aliases:
                pending.append(child.id)
            elif child.id in classes:
                members.add(child.id)
    return frozenset(members)


def coding_session_event_types() -> frozenset[type[object]]:
    """Return every concrete event class in the ``CodingSessionEvent`` union."""
    modules = (agent_events, coding_events)
    resolved: set[type[object]] = set()
    for name in union_member_names("CodingSessionEvent"):
        matches = [getattr(module, name) for module in modules if hasattr(module, name)]
        if len(matches) != 1:
            raise LookupError(f"{name} must be defined by exactly one event module")
        resolved.add(matches[0])
    return frozenset(resolved)
