"""Small text helpers shared by the TUI app and its extracted mixins."""

from __future__ import annotations

__all__ = ["text_end_location"]


def text_end_location(text: str) -> tuple[int, int]:
    """Return the TextArea cursor location at the end of text."""
    line, _, column_text = text.rpartition("\n")
    return (line.count("\n") + 1 if line else 0, len(column_text))
