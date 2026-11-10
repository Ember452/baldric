"""JSONL serialization for session exports."""

from __future__ import annotations

from collections.abc import Sequence

from baldric.protocol.session import SessionEntry


def _session_jsonl_text(entries: Sequence[SessionEntry]) -> str:
    """Serialize session entries to JSONL text (one JSON object per line)."""
    lines = [entry.model_dump_json() for entry in entries]
    return "\n".join(lines) + ("\n" if lines else "")
