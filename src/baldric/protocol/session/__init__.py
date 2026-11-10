"""Persisted session wire contract: entry shape, tree traversal, and JSONL format.

`memory` (SessionState projection) and `storage` (file I/O) deliberately live in
`baldric.runtime`, not here: the projection carries session-application semantics
and storage carries platform I/O, neither of which belongs in the pure contract.
"""

from __future__ import annotations

from baldric.protocol.session.entries import (
    CURRENT_SCHEMA_VERSION,
    SESSION_ENTRY_MODELS,
    BaseSessionEntry,
    BranchSummaryEntry,
    CompactionEntry,
    CustomEntry,
    CustomMessageEntry,
    LabelEntry,
    LeafEntry,
    MessageEntry,
    ModelChangeEntry,
    SessionEntry,
    SessionInfoEntry,
    ThinkingLevelChangeEntry,
)
from baldric.protocol.session.jsonl import (
    SessionJsonlError,
    SessionVersionError,
    entries_from_json_lines,
    entries_from_transcript,
    entry_from_json_line,
    entry_to_json_line,
)
from baldric.protocol.session.tree import (
    SessionTreeError,
    entries_by_id,
    path_to_entry,
)

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "SESSION_ENTRY_MODELS",
    "BaseSessionEntry",
    "BranchSummaryEntry",
    "CompactionEntry",
    "CustomEntry",
    "CustomMessageEntry",
    "LabelEntry",
    "LeafEntry",
    "MessageEntry",
    "ModelChangeEntry",
    "SessionEntry",
    "SessionInfoEntry",
    "ThinkingLevelChangeEntry",
    "SessionJsonlError",
    "SessionVersionError",
    "entries_from_json_lines",
    "entries_from_transcript",
    "entry_from_json_line",
    "entry_to_json_line",
    "SessionTreeError",
    "entries_by_id",
    "path_to_entry",
]
