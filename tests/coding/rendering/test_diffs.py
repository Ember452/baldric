"""Tests for the structured diff renderer."""

import pyte
from rich.console import Console

from baldric_coding.rendering.diffs import (
    _changed_word_ranges,
    parse_unified_patch,
    render_patch,
)
from baldric_coding.rendering.themes import BALDRIC_DARK_THEME


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
