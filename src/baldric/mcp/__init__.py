"""MCP client core: configuration, connection supervision, tool adaptation.

Protocol work is delegated to the official `mcp` SDK; this package holds only
Baldric's product layer. It must not import `baldric.agent`, `baldric.ai`, or
`baldric.coding` (see scripts/check_import_graph.py).
"""

__all__: list[str] = []
