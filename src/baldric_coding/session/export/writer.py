"""Session export file writing and format selection."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from baldric_agent.session import SessionEntry
from baldric_coding.session.export.html import render_session_html
from baldric_coding.session.export.jsonl import _session_jsonl_text


class SessionExportError(ValueError):
    """Raised when a session cannot be exported."""


def default_session_export_path(session_path: Path) -> Path:
    """Return the default HTML export path for a JSONL session file."""
    return session_path.with_suffix(".html")


def default_session_export_artifact_path(
    session_path: Path,
    *,
    destination_dir: Path,
    format: str = "html",
) -> Path:
    """Return the default user-facing export artifact path."""
    suffix = _export_suffix(format)
    return destination_dir / f"{session_path.stem}{suffix}"


def export_session_jsonl(entries: Sequence[SessionEntry], output_path: Path) -> Path:
    """Write session entries to a JSONL export and return its path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_session_jsonl_text(entries), encoding="utf-8")
    return output_path


def export_session_html(
    entries: Sequence[SessionEntry],
    output_path: Path,
    *,
    title: str = "Baldric Session Export",
    source: str | None = None,
    system_prompt: str | None = None,
) -> Path:
    """Write a self-contained HTML session export and return its path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_session_html(
            entries,
            title=title,
            source=source,
            system_prompt=system_prompt,
        ),
        encoding="utf-8",
    )
    return output_path


def export_session_artifact(
    entries: Sequence[SessionEntry],
    output_path: Path,
    *,
    title: str = "Baldric Session Export",
    source: str | None = None,
    format: str | None = None,
    system_prompt: str | None = None,
) -> Path:
    """Write a session export in the requested or inferred format."""
    export_format = normalize_export_format(format or output_path.suffix.removeprefix("."))
    if export_format == "jsonl":
        return export_session_jsonl(entries, output_path)
    return export_session_html(
        entries,
        output_path,
        title=title,
        source=source,
        system_prompt=system_prompt,
    )


def normalize_export_format(value: str | None) -> str:
    """Normalize a session export format name."""
    normalized = (value or "html").strip().lower().removeprefix(".")
    if normalized in {"htm", "html"}:
        return "html"
    if normalized == "jsonl":
        return "jsonl"
    raise SessionExportError(f"Unsupported export format: {value}")


def _export_suffix(format: str) -> str:
    return ".jsonl" if normalize_export_format(format) == "jsonl" else ".html"
