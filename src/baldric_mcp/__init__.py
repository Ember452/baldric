"""MCP client core: configuration, connection supervision, tool adaptation.

Protocol work is delegated to the official `mcp` SDK; this package holds only
Baldric's product layer. It must not import `baldric_agent`, `baldric_ai`, or
`baldric_coding` (see scripts/check_import_graph.py).
"""

__all__: list[str] = []
