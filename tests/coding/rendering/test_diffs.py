"""Tests for the structured diff renderer."""

import pyte
from rich.color import Color as RichColor
from rich.console import Console

from baldric_coding.rendering.diffs import (
    _changed_word_ranges,
    parse_unified_patch,
    render_patch,
)
from baldric_coding.rendering.themes import BALDRIC_DARK_THEME, BALDRIC_LIGHT_THEME


def _sgr_bg(hex_color: str) -> str:
    red, green, blue = RichColor.parse(hex_color).get_truecolor()
    return f"48;2;{red};{green};{blue}"


def _sgr_fg(hex_color: str) -> str:
    red, green, blue = RichColor.parse(hex_color).get_truecolor()
    return f"38;2;{red};{green};{blue}"


def _feed(screen: pyte.Screen, ansi_text: str) -> None:
    """Feed rendered ANSI into the pyte screen.

    Terminals translate a bare LF into CR+LF via the tty driver (ONLCR);
    pyte does not, so golden tests feed CRLF explicitly.
    """
    pyte.ByteStream(screen).feed(ansi_text.replace("\n", "\r\n").encode("utf-8"))


SAMPLE_PATCH = """--- src/app.py
+++ src/app.py
@@ -1,4 +1,4 @@
 import os
-FLAG = 1
+FLAG = 2
 
 def main():
"""


def test_parse_resolves_hunk_line_numbers() -> None:
    files = parse_unified_patch(SAMPLE_PATCH)

    assert len(files) == 1
    file = files[0]
    assert file.path == "src/app.py"
    kinds = [(line.kind, line.old_number, line.new_number) for line in file.lines]
    assert kinds == [
        ("hunk", None, None),
        ("context", 1, 1),
        ("remove", 2, None),
        ("add", None, 2),
        ("context", 3, 3),
        ("context", 4, 4),
    ]
    assert file.lines[2].text == "FLAG = 1"
    assert file.lines[3].text == "FLAG = 2"


def test_parse_handles_multiple_files_and_newline_marker() -> None:
    patch = """--- a/one.txt
+++ b/one.txt
@@ -1 +1 @@
-old
+new
\\ No newline at end of file
--- a/two.txt
+++ b/two.txt
@@ -1 +1 @@
 keep
"""
    files = parse_unified_patch(patch)

    assert [file.path for file in files] == ["a/one.txt", "a/two.txt"]
    assert files[0].lines[-1].kind == "meta"
    assert files[1].lines[-1].kind == "context"


def test_word_ranges_mark_only_the_changed_token() -> None:
    old_ranges, new_ranges = _changed_word_ranges("FLAG = 1", "FLAG = 2")

    assert old_ranges == [(7, 8)]
    assert new_ranges == [(7, 8)]


def test_word_ranges_unchanged_lines_have_no_ranges() -> None:
    old_ranges, new_ranges = _changed_word_ranges("same line", "same line")

    assert old_ranges == []
    assert new_ranges == []


def test_render_patch_returns_none_for_unparseable_text() -> None:
    assert render_patch("just some text\nwithout diff headers", theme=BALDRIC_DARK_THEME) is None


def test_render_patch_includes_path_signs_and_numbers() -> None:
    console = Console(record=True, width=80, force_terminal=False, color_system=None)
    console.print(render_patch(SAMPLE_PATCH, theme=BALDRIC_DARK_THEME))

    text = console.export_text()
    assert "src/app.py" in text
    assert "-  FLAG = 1" in text or "FLAG = 1" in text
    assert "FLAG = 2" in text
    assert "@@ -1,4 +1,4 @@" in text
    # Line-number gutters are right-justified in a fixed column.
    assert any(len(line) > 4 and line[4] == " " for line in text.splitlines())


def test_pyte_screen_renders_diff_gutters_and_signs_cleanly() -> None:
    console = Console(record=True, width=80, force_terminal=True, color_system="truecolor")
    console.print(render_patch(SAMPLE_PATCH, theme=BALDRIC_DARK_THEME))
    screen = pyte.Screen(80, 10)
    _feed(screen, console.export_text(styles=True))

    displayed = "\n".join(screen.display)
    assert "\ufffd" not in displayed
    assert "- FLAG = 1" in displayed
    assert "+ FLAG = 2" in displayed
    assert "src/app.py" in displayed


def test_pyte_screen_renders_cjk_inside_diff_lines() -> None:
    patch = """--- docs/说明.md
+++ docs/说明.md
@@ -1 +1 @@
-旧的一行宽字符
+新的一行宽字符
"""
    console = Console(record=True, width=80, force_terminal=True, color_system="truecolor")
    console.print(render_patch(patch, theme=BALDRIC_DARK_THEME))
    screen = pyte.Screen(80, 6)
    _feed(screen, console.export_text(styles=True))

    displayed = "\n".join(screen.display)
    assert "\ufffd" not in displayed
    assert "旧的一行宽字符" in displayed
    assert "新的一行宽字符" in displayed


# --- Task 6: full-row backgrounds (opencode palette) ------------------------

_ADDED_BG_ANSI = "48;2;32;48;59"  # #20303b
_REMOVED_BG_ANSI = "48;2;55;34;44"  # #37222c


def test_added_line_gets_the_opencode_row_background() -> None:
    console = Console(record=True, width=80, force_terminal=True, color_system="truecolor")
    console.print(render_patch(SAMPLE_PATCH, theme=BALDRIC_DARK_THEME))

    assert _ADDED_BG_ANSI in console.export_text(styles=True)


def test_removed_line_gets_the_opencode_row_background() -> None:
    console = Console(record=True, width=80, force_terminal=True, color_system="truecolor")
    console.print(render_patch(SAMPLE_PATCH, theme=BALDRIC_DARK_THEME))

    assert _REMOVED_BG_ANSI in console.export_text(styles=True)


def test_context_rows_carry_no_add_or_remove_background() -> None:
    context_only = "--- a.txt\n+++ a.txt\n@@ -1,2 +1,2 @@\n keep\n also\n"
    console = Console(record=True, width=80, force_terminal=True, color_system="truecolor")
    console.print(render_patch(context_only, theme=BALDRIC_DARK_THEME))

    styles = console.export_text(styles=True)
    assert _ADDED_BG_ANSI not in styles
    assert _REMOVED_BG_ANSI not in styles


def test_leading_dashes_in_hunk_content_keep_their_row_background() -> None:
    # A removed line whose content begins with "--" renders as a content row,
    # not a file header; the count-based hunk detection must be untouched.
    patch = "--- a.txt\n+++ a.txt\n@@ -1,2 +1,2 @@\n---flag\n+--flag=2\n"
    console = Console(record=True, width=80, force_terminal=True, color_system="truecolor")
    console.print(render_patch(patch, theme=BALDRIC_DARK_THEME))
    styles = console.export_text(styles=True)
    assert _REMOVED_BG_ANSI in styles
    assert _ADDED_BG_ANSI in styles
    assert "--flag" in styles


def test_light_theme_diff_rows_use_a_light_background() -> None:
    # Without tokens a theme must still get backgrounds that suit its own
    # light/dark appearance; the dark opencode palette on a light theme paints
    # dark rows on a white transcript.
    console = Console(record=True, width=80, force_terminal=True, color_system="truecolor")
    console.print(render_patch(SAMPLE_PATCH, theme=BALDRIC_LIGHT_THEME))

    styles = console.export_text(styles=True)
    # The dark opencode backgrounds must not appear on the light theme.
    assert _ADDED_BG_ANSI not in styles
    assert _REMOVED_BG_ANSI not in styles
    # A light palette still colours the rows (opencode light.diff added bg).
    assert "48;2;213;229;213" in styles  # #d5e5d5


def test_word_emphasis_uses_the_highlight_colour() -> None:
    # spec §5.3: the changed token is bold AND the brighter diff.highlight
    # colour, not just bold, so it pops against the row background.
    console = Console(record=True, width=80, force_terminal=True, color_system="truecolor")
    console.print(render_patch(SAMPLE_PATCH, theme=BALDRIC_DARK_THEME))

    styles = console.export_text(styles=True)
    # SAMPLE_PATCH changes "1" to "2"; those tokens carry the highlight colours.
    assert f"1;{_sgr_fg('#b8db87')}" in styles  # added highlight
    assert f"1;{_sgr_fg('#e26a75')}" in styles  # removed highlight
