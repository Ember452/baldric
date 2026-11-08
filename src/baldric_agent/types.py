"""Compatibility shim: JSON types now live in ``baldric_protocol.types``.

Kept during the protocol extraction so existing ``from baldric_agent.types``
imports keep working. Remove once every importer points at the protocol package.
"""

from __future__ import annotations

from baldric_protocol.types import JSONObject, JSONPrimitive, JSONValue

__all__ = ["JSONObject", "JSONPrimitive", "JSONValue"]
