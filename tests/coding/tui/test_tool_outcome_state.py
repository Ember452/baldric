"""Tests for explicit tool outcome/duration recording in TuiState.

Before this, the render layer guessed success from `startswith("✓")` and the
completion duration was thrown away with `started_at = None`. The state now
records both explicitly at `record_tool_result` time.
"""

from __future__ import annotations

import time

from baldric.coding.rendering.themes import BALDRIC_DARK_THEME
from baldric.coding.rendering.tool_state import tool_state_background
from baldric.coding.tui.state import ChatItem, TuiState
from baldric.coding.tui.widgets.core import (
    TranscriptMessageWidget,
    _chat_item_role_style,
    _tool_batch_row_invocation,
)
from baldric.protocol.messages import TextContent
from baldric.protocol.tools import AgentToolResult


def _result(text: str = "ok") -> AgentToolResult:
    return AgentToolResult(content=[TextContent(text=text)])


def test_record_tool_result_stamps_outcome_and_duration() -> None:
    state = TuiState()
    state.add_item("tool", "→ bash", tool_call_id="call-1", always_show_tool_result=True)
    item = state.find_tool_item("call-1")
    assert item is not None
    item.started_at = time.monotonic() - 4.2

    state.record_tool_result("call-1", "bash", _result(), False)

    assert item.tool_is_error is False
    assert item.tool_duration_seconds is not None
    assert item.tool_duration_seconds >= 4.0
    assert item.started_at is None


def test_record_tool_result_records_errors() -> None:
    state = TuiState()
    state.add_item("tool", "→ bash", tool_call_id="call-1", always_show_tool_result=True)

    state.record_tool_result("call-1", "bash", _result("boom"), True)

    item = state.find_tool_item("call-1")
    assert item is not None
    assert item.tool_is_error is True


def test_record_tool_result_without_start_stamps_outcome_only() -> None:
    # A restored row never had a start stamp; the outcome is still explicit.
    state = TuiState()
    state.add_item("tool", "→ read x", tool_call_id="call-1", always_show_tool_result=True)
    item = state.find_tool_item("call-1")
    assert item is not None
    assert item.started_at is None

    state.record_tool_result("call-1", "read", _result(), False)

    assert item.tool_is_error is False
    assert item.tool_duration_seconds is None


def test_orphan_result_stamps_error_without_duration() -> None:
    state = TuiState()

    state.record_tool_result("missing", "bash", _result("late"), True)

    item = state.find_tool_item("missing")
    assert item is not None
    assert item.tool_is_error is True
    # No prior call row means no timing source.
    assert item.tool_duration_seconds is None


# --- Task 3: render side — explicit outcome drives style and duration --------


def test_completed_tool_row_header_carries_duration() -> None:
    item = ChatItem(role="tool", text="→ bash $ ls", tool_name="bash")
    item.tool_result_text = "✓ bash"
    item.tool_duration_seconds = 4.2

    invocation = _tool_batch_row_invocation(item, expanded=False)

    assert invocation.endswith(" · 4.2s")
    assert "4.2s" not in item.text


def test_pending_tool_row_header_keeps_live_elapsed() -> None:
    import time as time_module

    item = ChatItem(
        role="tool", text="→ bash $ sleep", tool_name="bash", started_at=time_module.monotonic() - 2.0
    )

    invocation = _tool_batch_row_invocation(item, expanded=False)

    assert "(2s)" in invocation or "(2.0s)" in invocation


def test_explicit_outcome_selects_border_without_text_guessing() -> None:
    item = ChatItem(role="tool", text="→ bash", tool_name="bash")
    item.tool_result_text = "✓ bash"  # even a SUCCESS-prefixed text...
    item.tool_is_error = True  # ...with an explicit error outcome must lose.

    style = _chat_item_role_style(item, BALDRIC_DARK_THEME)

    assert style.border == BALDRIC_DARK_THEME.error


def test_explicit_success_outcome_selects_success_border() -> None:
    item = ChatItem(role="tool", text="→ bash", tool_name="bash")
    item.tool_result_text = "✗ bash"  # text prefix contradicts...
    item.tool_is_error = False  # ...the explicit outcome wins.

    style = _chat_item_role_style(item, BALDRIC_DARK_THEME)

    assert style.border == BALDRIC_DARK_THEME.success


def test_missing_outcome_falls_back_to_text_prefix() -> None:
    # Restored sessions carry no explicit outcome; the legacy heuristic stays.
    item = ChatItem(role="tool", text="→ bash", tool_name="bash")
    item.tool_result_text = "✗ bash"

    style = _chat_item_role_style(item, BALDRIC_DARK_THEME)

    assert style.border == BALDRIC_DARK_THEME.error


def test_tool_state_background_helper() -> None:
    assert tool_state_background(True, has_result=True) == "#410a13"
    assert tool_state_background(False, has_result=True) == "#144922"
    assert tool_state_background(None, has_result=True) is None
    assert tool_state_background(True, has_result=False) is None


def test_tool_row_body_carries_the_state_background() -> None:
    item = ChatItem(role="tool", text="→ bash", tool_name="bash")
    item.tool_result_text = "✓ bash"
    item.tool_is_error = False

    style = _chat_item_role_style(item, BALDRIC_DARK_THEME)

    assert style.body.endswith("on #144922")


def test_tool_row_widget_paints_the_state_background() -> None:
    item = ChatItem(role="tool", text="→ bash", tool_name="bash")
    item.tool_result_text = "✗ bash"
    item.tool_is_error = True

    widget = TranscriptMessageWidget(item, theme=BALDRIC_DARK_THEME, show_tool_results=False)

    assert widget.styles.background == __import__("textual.color", fromlist=["Color"]).Color.parse("#410a13")


def test_grouped_members_stamp_outcome_and_duration() -> None:
    state = TuiState()
    state.add_item("tool", "→ read a", tool_call_id="call-1", always_show_tool_result=True)
    state.add_item("tool", "→ read b", tool_call_id="call-2", always_show_tool_result=True)
    first = state.find_tool_item("call-1")
    second = state.find_tool_item("call-2")
    assert first is not None and second is not None
    for item, offset in ((first, 1.0), (second, 2.0)):
        target = item.grouped_tool_calls
        if target is not None:
            for member in target:
                if member.tool_call_id == item.tool_call_id:
                    member.started_at = time.monotonic() - offset
        else:
            item.started_at = time.monotonic() - offset

    state.record_tool_result("call-1", "read", _result(), False)
    state.record_tool_result("call-2", "read", _result("bad"), True)

    for item, is_error in ((first, False), (second, True)):
        members = item.grouped_tool_calls
        if members is not None:
            member = next(m for m in members if m.tool_call_id == item.tool_call_id)
            assert member.tool_is_error is is_error
            if is_error:
                assert member.tool_duration_seconds is not None
                assert member.tool_duration_seconds >= 1.5
        else:
            assert item.tool_is_error is is_error


def test_tool_row_style_without_body_foreground_omits_none() -> None:
    # The layered schema allows omitting roles.tool.body (empty string); the
    # state style must then be the bare background, never "None on <bg>".
    from baldric.coding.rendering.themes import TuiRoleStyle
    from baldric.coding.rendering.tool_state import tool_row_role_style

    base = TuiRoleStyle(border="#8a7a52", body="")
    style = tool_row_role_style(
        tool_is_error=False,
        tool_result_text="x",
        base=base,
        success_border="#519671",
        error_border="#d3565c",
    )
    assert style.body == "on #144922"
    assert "None" not in style.body

    style_err = tool_row_role_style(
        tool_is_error=True,
        tool_result_text="x",
        base=base,
        success_border="#519671",
        error_border="#d3565c",
    )
    assert style_err.body == "on #410a13"
