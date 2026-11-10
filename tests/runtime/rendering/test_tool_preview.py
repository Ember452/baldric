"""Tests for the per-tool collapsed preview budgets (Task 4).

One shared budget for every tool was wrong: a bash log wants the tail, a read
wants the head, and an edit patch must never be cut (the patch is the thing
the user reviews). Values come from pi:
  pi-main/packages/coding-agent/src/core/tools/bash.ts   (BASH_PREVIEW_LINES = 5)
  pi-main/packages/coding-agent/src/core/tools/renderers/read.ts (10 unexpanded)
  pi-main/packages/coding-agent/src/core/tools/renderer.ts (CODE_PREVIEW_LINES = 10)
"""

from __future__ import annotations

import pytest

from baldric.runtime.rendering.tool_preview import preview_budget


def test_bash_shows_five_lines() -> None:
    assert preview_budget("bash") == 5


def test_read_shows_ten_lines() -> None:
    assert preview_budget("read") == 10


def test_edit_and_write_are_not_truncated() -> None:
    assert preview_budget("edit") is None
    assert preview_budget("write") is None


def test_unknown_tool_falls_back_to_a_bounded_preview() -> None:
    assert preview_budget("some_new_tool") == 10
    assert preview_budget("") == 10


def test_terminal_command_output_keeps_its_own_large_budget() -> None:
    # BashExecutionMessage is distinct from a tool call; see state.py.
    assert preview_budget("__terminal__") == 120


@pytest.mark.parametrize(
    ("tool_name", "budget"),
    [("edit", None), ("write", None), ("bash", 5), ("read", 10), ("glob", 10)],
)
def test_budget_matches_pi_per_renderer_constants(tool_name: str, budget: int | None) -> None:
    assert preview_budget(tool_name) == budget
