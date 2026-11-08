"""Compatibility shim: JSONL serialization now lives in
``baldric_protocol.session.jsonl``.

Kept during the protocol extraction so existing ``from baldric_agent.session.jsonl``
imports keep working. Remove once every importer points at the protocol package.
"""

from __future__ import annotations

from baldric_protocol.session.jsonl import (
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
