"""Bundled MCP client extension (thin glue over ``baldric_mcp``)."""

from __future__ import annotations

from .extension import API_VERSION, CAPABILITIES, setup

__all__ = ["API_VERSION", "CAPABILITIES", "setup"]
