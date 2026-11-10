"""Hover/selection consistency for list rows (Task 6, spec 2026-11-08 §6).

opencode models interactive rows with per-state colours ($selected, $hovered,
$focused). Baldric's selection palette ($baldric-highlight-background/text)
already styles keyboard-selected rows everywhere, and sidebar rows have used
the same pair for mouse hover since batch 1 — those sidebar rows have a
runtime hover test (test_tui_app.py, CJK/hover golden). This test pins the
matching picker-list rule at the CSS level.

Runtime hover on pushed modal screens cannot be exercised headlessly:
`Pilot.hover` resolves the compositor target on the main screen only and
returns False on modals, and a synthetic `MouseMove` bypasses the compositor
pipeline that drives `:hover`. The rule shares the exact mechanism proven by
the sidebar runtime test.
"""

from __future__ import annotations

from baldric.coding.tui.app import BaldricTuiApp


def test_app_css_gives_list_item_rows_a_hover_state() -> None:
    css = BaldricTuiApp.CSS
    assert "ListView > ListItem:hover" in css
    # The hover state uses the same selection palette as -highlight.
    assert css.count("$baldric-highlight-background") >= 4
    assert "$baldric-highlight-text" in css
