"""Session core: the persisted-session codec and (later) orchestration.

The JSONL codec lives here because it is behaviour (serialize, migrate, validate)
rather than a wire shape; the shape models stay in ``baldric.protocol.session``.
"""

from __future__ import annotations

from baldric.runtime.core.session.jsonl import (
    SessionJsonlError,
    SessionVersionError,
    entries_from_json_lines,
    entries_from_transcript,
    entry_from_json_line,
    entry_to_json_line,
)

__all__ = [
    "SessionJsonlError",
    "SessionVersionError",
    "entries_from_json_lines",
    "entries_from_transcript",
    "entry_from_json_line",
    "entry_to_json_line",
]
