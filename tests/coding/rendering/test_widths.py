"""Unit and pyte golden tests for the shared width helpers."""

import pyte
import pytest
from rich.console import Console

from baldric.coding.rendering.widths import ELLIPSIS, cell_width, truncate_to_cells


def test_cell_width_counts_double_width_characters_as_two() -> None:
    assert cell_width("宽") == 2
    assert cell_width("a宽b") == 4
    assert cell_width("") == 0


@pytest.mark.parametrize(
    ("text", "budget", "expected"),
    [
        ("宽", 2, "宽"),
        ("宽", 1, "…"),  # a 1-column budget fits exactly the 1-column ellipsis
        ("abc", 5, "abc"),
        ("a宽b宽c", 4, "a宽…"),  # a wide char is never split in half
        ("a宽b宽c", 3, "a…"),
        ("abcdef", 0, ""),
        ("宽宽宽", 4, "宽…"),
    ],
)
def test_truncate_to_cells_honors_the_column_budget(text: str, budget: int, expected: str) -> None:
    result = truncate_to_cells(text, budget)
    assert result == expected
    assert cell_width(result) <= budget


def test_truncate_result_never_exceeds_the_budget_for_wide_text() -> None:
    text = "宽" * 500
    for budget in (1, 2, 3, 7, 16, 37, 100):
        result = truncate_to_cells(text, budget)
        assert cell_width(result) <= budget
        assert result.endswith(ELLIPSIS) or result == ""


def test_pyte_screen_shows_the_truncated_cjk_line_inside_the_budget() -> None:
    """Golden: the rendered line occupies within the budgeted columns."""
    budget = 20
    rendered = truncate_to_cells("宽" * 60 + " tail", budget)
    assert cell_width(rendered) <= budget

    console = Console(record=True, width=40, force_terminal=True, color_system="truecolor")
    console.print(rendered)
    screen = pyte.Screen(40, 3)
    pyte.ByteStream(screen).feed(console.export_text(styles=True).encode("utf-8"))

    line = screen.display[0].rstrip()
    assert line == rendered
    assert "\ufffd" not in screen.display[0]


def test_pyte_screen_shows_cjk_tool_preview_without_mojibake() -> None:
    """Golden: a CJK-heavy tool preview prints unscathed through the shared path."""
    from baldric.coding.tui.state import format_tool_result_block

    # "宽0" is 3 columns; 26 repetitions fit one 80-column screen line.
    content = "\n".join(f"宽{index}" * 26 for index in range(TOOL_ROWS))
    block = format_tool_result_block(name="read", ok=True, content=content)
    assert "[Preview only:" in block

    console = Console(record=True, width=80, force_terminal=True, color_system="truecolor")
    console.print(block)
    # 24 rows: the read budget shows ten lines and each CJK-heavy block line
    # spans roughly two terminal rows here, so the 20-row screen the old
    # 8-line budget fit would scroll the status line off the top.
    screen = pyte.Screen(80, 24)
    pyte.ByteStream(screen).feed(console.export_text(styles=True).encode("utf-8"))

    displayed = "\n".join(screen.display)
    assert "\ufffd" not in displayed
    assert "✓ read" in displayed
    assert "宽0宽0宽0宽0" in displayed


TOOL_ROWS = 12
