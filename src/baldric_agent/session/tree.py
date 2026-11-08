"""Compatibility shim: session tree helpers now live in
``baldric_protocol.session.tree``.

Kept during the protocol extraction so existing ``from baldric_agent.session.tree``
imports keep working. Remove once every importer points at the protocol package.
"""

from __future__ import annotations

from baldric_protocol.session.tree import SessionTreeError, entries_by_id, path_to_entry

__all__ = ["SessionTreeError", "entries_by_id", "path_to_entry"]
