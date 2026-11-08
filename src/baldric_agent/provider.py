"""Compatibility shim: the provider contract now lives in ``baldric_protocol.provider``.

Kept during the protocol extraction so existing ``from baldric_agent.provider``
imports keep working. Remove once every importer points at the protocol package.
"""

from __future__ import annotations

from baldric_protocol.provider import CancellationToken, ModelProvider

__all__ = ["CancellationToken", "ModelProvider"]
