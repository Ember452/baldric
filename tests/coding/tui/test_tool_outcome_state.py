"""Tests for explicit tool outcome/duration recording in TuiState.

Before this, the render layer guessed success from `startswith("✓")` and the
completion duration was thrown away with `started_at = None`. The state now
records both explicitly at `record_tool_result` time.
"""

from __future__ import annotations

import time

from baldric_coding.tui.state import TuiState
from baldric_protocol.messages import TextContent
from baldric_protocol.tools import AgentToolResult


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
