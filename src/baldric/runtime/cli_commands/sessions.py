"""`baldric sessions` — list indexed sessions."""

from __future__ import annotations

import typer

from baldric.runtime.session.manager import CodingSessionRecord


def render_session_list(records: list[CodingSessionRecord]) -> None:
    """Render indexed sessions for the CLI."""
    if not records:
        typer.echo("No sessions found.")
        return

    for record in records:
        title = record.title or "Untitled"
        typer.echo(f"{record.id}\t{title}\t{record.model}\t{record.cwd}")


__all__ = ["render_session_list"]
