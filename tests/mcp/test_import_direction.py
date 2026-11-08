"""``baldric_mcp`` must be importable on its own; direction is guarded elsewhere."""

from __future__ import annotations

import importlib


def test_baldric_mcp_imports() -> None:
    module = importlib.import_module("baldric_mcp")

    assert module.__all__ == []
