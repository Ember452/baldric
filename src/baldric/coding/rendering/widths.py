"""Authoritative terminal-width helpers for Baldric rendering.

Every consumer that slices or budgets display text by *columns* goes through
this module, so CJK double-width characters and emoji count the way the
terminal will actually render them (rich's cell math: ``宽`` is 2 columns,
``a宽b`` is 4). Char-count budgets are a lie for double-width text — the same
2,000 characters can be 2,000 or 4,000 columns depending on content — and the
shared rendering layer serves print mode, the Textual TUI, and the scrollback
frontend with one terminal, so one width definition has to win.
"""

from __future__ import annotations

from functools import lru_cache

from rich.cells import cell_len as _cell_len

ELLIPSIS = "…"


def cell_width(text: str) -> int:
    """Return the terminal column width of *text*."""
    return _cell_len(text)


def truncate_to_cells(text: str, max_cells: int, *, ellipsis: str = ELLIPSIS) -> str:
    """Return *text* cut to at most *max_cells* terminal columns.

    The cut never splits a wide character, and the ellipsis is accounted for
    inside the budget, so the result always renders within *max_cells*
    columns. *text* is returned unchanged when it already fits. Callers pass
    a single line: the budget has no meaning for embedded newlines, and a
    newline in *text* is cut like any other character.
    """
    if max_cells <= 0:
        return ""
    if _cell_len(text) <= max_cells:
        return text
    budget = max_cells - _cell_len(ellipsis)
    if budget < 0:
        return ""
    kept: list[str] = []
    used = 0
    for char in text:
        width = _char_width(char)
        if used + width > budget:
            break
        kept.append(char)
        used += width
    return "".join(kept) + ellipsis


@lru_cache(maxsize=4096)
def _char_width(char: str) -> int:
    return _cell_len(char)
