"""Per-tool preview budgets for collapsed tool rows.

One constant for every tool was wrong: a bash log wants the tail, a read wants
the head, and an edit patch must never be cut (the patch is the thing the user
needs to review). Values copied from pi:
  pi-main/packages/coding-agent/src/core/tools/bash.ts   (BASH_PREVIEW_LINES = 5)
  pi-main/packages/coding-agent/src/core/tools/renderers/read.ts (10 unexpanded)
  pi-main/packages/coding-agent/src/core/tools/renderer.ts (CODE_PREVIEW_LINES = 10)
"""

from __future__ import annotations

BASH_PREVIEW_LINES = 5
READ_PREVIEW_LINES = 10
DEFAULT_PREVIEW_LINES = 10
TERMINAL_COMMAND_PREVIEW_LINES = 120

_NO_TRUNCATION_TOOLS = frozenset({"edit", "write"})
_PREVIEW_BY_TOOL = {"bash": BASH_PREVIEW_LINES, "read": READ_PREVIEW_LINES}


def preview_budget(tool_name: str) -> int | None:
    """Return the collapsed preview line budget, or None to show everything."""
    if tool_name == "__terminal__":
        return TERMINAL_COMMAND_PREVIEW_LINES
    if tool_name in _NO_TRUNCATION_TOOLS:
        return None
    return _PREVIEW_BY_TOOL.get(tool_name, DEFAULT_PREVIEW_LINES)
