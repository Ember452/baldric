"""Session state, persistence, and presentation.

The persisted session wire shape (entries/tree/jsonl) lives in
``baldric.protocol.session``. This package owns the application-side pieces: the
in-memory ``SessionState`` projection and the file-backed storage (I/O).
"""

from __future__ import annotations

from baldric.coding.session.memory import SessionState
from baldric.coding.session.storage import (
    InMemorySessionStorage,
    JsonlSessionStorage,
    SessionStorage,
)

__all__ = [
    "InMemorySessionStorage",
    "JsonlSessionStorage",
    "SessionState",
    "SessionStorage",
]
