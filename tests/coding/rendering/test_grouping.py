"""Tests for tool-run count summaries."""

from rich.console import Console

from baldric.coding.rendering.grouping import (
    format_tool_run_summary,
    should_summarize,
)
from baldric.coding.rendering.themes import BALDRIC_DARK_THEME
from baldric.coding.tui.state import ChatItem
from baldric.coding.tui.widgets.core import _render_transcript_tool_batch


def test_summary_preserves_first_seen_order_and_counts() -> None:
    assert (
        format_tool_run_summary(["read", "bash", "read", "bash", "read", "write"])
        == "read ×3 · bash ×2 · write ×1"
    )


def test_summary_of_empty_run_is_empty() -> None:
    assert format_tool_run_summary([]) == ""


def test_should_summarize_threshold() -> None:
    assert not should_summarize(0)
    assert not should_summarize(2)
    assert should_summarize(3)


def _batch_item(tool_names: list[str]) -> ChatItem:
    rows = [
        ChatItem(role="tool", text=f"→ {name} target-{index}", tool_name=name)
        for index, name in enumerate(tool_names)
    ]
    return ChatItem(
        role="tool",
        text=f"→ {tool_names[0]} target-0",
        tool_name=tool_names[0],
        tool_batch_items=rows,
    )


def test_collapsed_batch_of_three_plus_gains_a_summary_head() -> None:
    item = _batch_item(["read", "bash", "read"])

    console = Console(record=True, width=80, color_system=None)
    console.print(
        _render_transcript_tool_batch(
            item,
            body_style="",
            theme=BALDRIC_DARK_THEME,
            expanded=False,
        )
    )

    text = console.export_text()
    assert "read ×2 · bash ×1" in text
    assert "→ read target-0" in text


def test_expanded_batch_has_no_summary_head() -> None:
    item = _batch_item(["read", "bash", "read"])

    console = Console(record=True, width=80, color_system=None)
    console.print(
        _render_transcript_tool_batch(
            item,
            body_style="",
            theme=BALDRIC_DARK_THEME,
            expanded=True,
        )
    )

    text = console.export_text()
    assert "×" not in text


def test_two_row_batch_has_no_summary_head() -> None:
    item = _batch_item(["read", "bash"])

    console = Console(record=True, width=80, color_system=None)
    console.print(
        _render_transcript_tool_batch(
            item,
            body_style="",
            theme=BALDRIC_DARK_THEME,
            expanded=False,
        )
    )

    text = console.export_text()
    assert "×" not in text
