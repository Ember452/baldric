"""A tiny stdio MCP server used by integration tests: one `echo` tool."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("fixture")


@mcp.tool()
def echo(text: str) -> str:
    """Echo the text back."""
    return text


if __name__ == "__main__":
    mcp.run()
