"""Session-record helpers shared by the TUI app and its pickers.

These helpers build the resume/archive picker data from a ``CodingSession``.
They lived in ``tui/app.py``; they moved here so the extracted picker mixin and
the remaining app code can both import them without a cycle
(``pickers -> session_records`` and ``app -> session_records``).
"""

from __future__ import annotations

from pathlib import Path

from baldric.runtime.frontends.tui.autocomplete import CompletionOption
from baldric.runtime.frontends.tui.screens.support import SessionCompletionRecord
from baldric.runtime.session.session import CodingSession

__all__ = [
    "session_records",
    "local_session_records",
    "archived_session_records",
    "session_options",
    "short_path",
]


def short_path(path: Path) -> str:
    home = Path.home()
    try:
        relative = path.relative_to(home)
        return "~" if relative == Path(".") else f"~/{relative}"
    except ValueError:
        return str(path)


def _session_option(record: SessionCompletionRecord) -> CompletionOption:
    description_parts = [record.title if record.title else "Untitled session"]
    if record.model:
        description_parts.append(record.model)
    description_parts.append(short_path(record.cwd))
    return CompletionOption(value=record.id, description=" - ".join(description_parts))


def session_records(session: CodingSession) -> tuple[SessionCompletionRecord, ...]:
    """Return indexed sessions for resume, current directory first.

    Sessions from the session's working directory are listed newest-first,
    followed by sessions from every other directory (also newest-first), so a
    session from another project is visible in the picker without leaving it.
    """
    manager = getattr(session, "session_manager", None)
    if manager is None:
        return ()
    try:
        records = list(manager.list_sessions())
    except TypeError:
        # Older managers only accept an explicit cwd argument.
        records = list(manager.list_sessions(session.cwd))
    local_cwd = Path(session.cwd).resolve()
    local = [record for record in records if Path(record.cwd).resolve() == local_cwd]
    other = [record for record in records if Path(record.cwd).resolve() != local_cwd]
    return tuple(local) + tuple(other)


def local_session_records(session: CodingSession) -> tuple[SessionCompletionRecord, ...]:
    """Return only the current project's indexed sessions."""
    manager = getattr(session, "session_manager", None)
    if manager is None:
        return ()
    try:
        records = manager.list_sessions(session.cwd)
    except TypeError:
        records = manager.list_sessions()
    local_cwd = Path(session.cwd).resolve()
    return tuple(record for record in records if Path(record.cwd).resolve() == local_cwd)


def archived_session_records(session: CodingSession) -> tuple[SessionCompletionRecord, ...]:
    """Return archived session metadata for the picker's archived tab."""
    manager = getattr(session, "session_manager", None)
    list_archived = getattr(manager, "list_archived_sessions", None)
    if not callable(list_archived):
        return ()
    return tuple(list_archived())


def session_options(session: CodingSession) -> tuple[CompletionOption, ...]:
    return tuple(_session_option(record) for record in session_records(session))
