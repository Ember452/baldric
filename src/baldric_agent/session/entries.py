"""Compatibility shim: session entry models now live in
``baldric_protocol.session.entries``.

Kept during the protocol extraction so existing ``from baldric_agent.session.entries``
imports keep working. Remove once every importer points at the protocol package.
"""

from __future__ import annotations

from baldric_protocol.session.entries import (
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
    current_timestamp,
    new_entry_id,
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
    "current_timestamp",
    "new_entry_id",
]
