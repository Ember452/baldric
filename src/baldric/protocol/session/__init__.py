"""Persisted session wire contract: entry shape and tree traversal.

`jsonl` (serialization + Baldric-v1 migration), `memory` (SessionState
projection), and `storage` (file I/O) deliberately live in `baldric.runtime`,
not here: jsonl is behaviour (parse/migrate/validate), the projection carries
session-application semantics, and storage carries platform I/O — none of which
belongs in the pure contract.
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
    "SessionTreeError",
    "entries_by_id",
    "path_to_entry",
]
