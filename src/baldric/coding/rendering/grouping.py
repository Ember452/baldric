"""Tool-run summaries shared by the TUI and print modes.

A batch of consecutive tool calls reads better with a count head than as a
wall of identical rows: ``read ×3 · bash ×2`` preserves first-seen order so
the summary mirrors what actually ran, instead of sorting by name.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

SUMMARY_MIN_ROWS = 3


def format_tool_run_summary(tool_names: Iterable[str]) -> str:
    """Return a ``name ×count`` summary preserving first-seen tool order."""
    counts = Counter(tool_names)
    return " · ".join(f"{name} ×{count}" for name, count in counts.items())


def should_summarize(row_count: int) -> bool:
    """Return whether a batch of *row_count* rows earns a summary head."""
    return row_count >= SUMMARY_MIN_ROWS
