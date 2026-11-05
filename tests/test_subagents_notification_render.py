"""Tests for the subagent completion cards: glyphs, stats, previews, escaping."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from baldric_agent.tools import AgentToolResult
from baldric_coding.extensions.api import CustomMessageView, MessageRenderOptions
from baldric_coding.extensions.builtins.subagents.notification_render import (
    COLLAPSED_PREVIEW_CHARS,
    EXPANDED_RESULT_LINES,
    render_agent_result,
    render_notification,
    stat_parts,
)


def _details(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "status": "completed",
        "description": "run the suite",
        "result_preview": "3 tests passed",
        "turn_count": 3,
        "max_turns": 8,
        "tool_uses": 5,
        "total_tokens": 12_345,
        "duration_ms": 4_500,
    }
    base.update(overrides)
    return base


def _notification(details: Mapping[str, Any] | None) -> CustomMessageView:
    return CustomMessageView(
        custom_type="subagent-notification", content="<task-notification/>", details=details
    )


def test_a_notification_without_structured_details_declines_to_render() -> None:
    assert render_notification(_notification(None), MessageRenderOptions()) is None
    assert render_notification(_notification("<raw/>"), MessageRenderOptions()) is None


def test_a_group_notification_stacks_its_extra_runs() -> None:
    view = _notification(_details(others=[_details(description="second"), "not-a-dict"]))

    rendered = render_notification(view, MessageRenderOptions())

    assert rendered is not None
    lines = rendered.splitlines()
    assert "run the suite" in lines[0]
    assert "second" in rendered
    assert len(lines) >= 4, "each block contributes its line plus a stats line"


def test_each_status_gets_its_own_glyph_and_wording() -> None:
    cases = {
        "completed": ("[green]✓[/green]", "completed"),
        "error": ("[red]✗[/red]", "error"),
        "aborted": ("[red]✗[/red]", "aborted"),
        "cancelled": ("[dim]∅[/dim]", "cancelled"),
        "steered": ("[yellow]✓[/yellow]", "completed (steered)"),
    }

    for status, (glyph, text) in cases.items():
        rendered = render_notification(
            _notification(_details(status=status, result_preview="x")), MessageRenderOptions()
        )
        assert rendered is not None
        assert glyph in rendered, status
        assert text in rendered, status


def test_user_stops_are_dim_and_failures_are_red() -> None:
    stopped = render_notification(
        _notification(_details(status="cancelled", result_preview="halted")),
        MessageRenderOptions(),
    )
    failed = render_notification(
        _notification(_details(status="error", result_preview="boom")), MessageRenderOptions()
    )

    assert "[dim]⎿  halted[/dim]" in (stopped or "")
    assert "[red]⎿  boom[/red]" in (failed or "")


def test_collapsed_preview_cuts_at_a_word_and_marks_the_ellipsis() -> None:
    long = "alpha " * 40 + "beta"
    rendered = render_notification(_notification(_details(result_preview=long)), MessageRenderOptions())

    assert rendered is not None
    assert "⎿" in rendered
    assert "…[/dim]" in rendered, "the cut is marked, inside the style"
    assert "beta" not in rendered
    preview = rendered.split("⎿  ", 1)[1].removesuffix("[/dim]")
    assert len(preview) <= COLLAPSED_PREVIEW_CHARS + 1, "the collapsed body honours the cap"
    assert "alpha" in preview


def test_multiline_preview_is_marked_as_truncated_when_collapsed() -> None:
    rendered = render_notification(
        _notification(_details(result_preview="first\nsecond")), MessageRenderOptions()
    )

    assert rendered is not None
    assert "⎿  first…[/dim]" in rendered
    assert "second" not in rendered


def test_expanded_view_caps_lines_and_reports_the_transcript() -> None:
    preview = "\n".join(f"line {index}" for index in range(EXPANDED_RESULT_LINES + 7))
    details = _details(result_preview=preview, output_file="C:/tmp/t.jsonl")

    rendered = render_notification(_notification(details), MessageRenderOptions(expanded=True))

    assert rendered is not None
    assert f"line {EXPANDED_RESULT_LINES - 1}" in rendered
    assert f"line {EXPANDED_RESULT_LINES}" not in rendered
    assert "7 more lines — get_subagent_result for full output" in rendered
    assert "transcript: C:/tmp/t.jsonl" in rendered


def test_collapsed_view_hides_the_transcript_path() -> None:
    rendered = render_notification(
        _notification(_details(output_file="/tmp/t.jsonl")), MessageRenderOptions()
    )

    assert "transcript:" not in (rendered or "")


def test_model_controlled_text_cannot_inject_markup() -> None:
    """Descriptions and previews come from the run, so their brackets escape."""
    rendered = render_notification(
        _notification(_details(description="[red]fake[/red]", result_preview="[/dim] escape attempt")),
        MessageRenderOptions(),
    )

    assert rendered is not None
    # Escaped markup keeps the text but loses the tag: a backslash before every
    # bracket the run supplied, so it cannot open or close a style run.
    assert r"\[red]fake\[/red]" in rendered
    assert r"\[/dim] escape attempt" in rendered
    assert "[bold]\\[red]" in rendered, "the injected tag sits inside the bold run, not as a tag"


def test_stat_parts_composes_the_shared_vocabulary() -> None:
    parts = stat_parts(_details())

    assert parts == ["3 turns (max 8)", "5 tool uses", "12.3k tokens", "4.5s"]


def test_stat_parts_omits_absent_and_zero_fields() -> None:
    assert stat_parts({}) == []
    assert stat_parts({"turn_count": 2}) == ["2 turns"], "no (max N) without a limit"
    assert stat_parts({"turn_count": 1, "tool_uses": 1}) == ["1 turn", "1 tool use"]
    assert stat_parts({"total_tokens": 900}) == ["900 tokens"]


def test_stat_parts_ignores_wrongly_typed_values() -> None:
    assert stat_parts({"turn_count": "3", "tool_uses": True, "duration_ms": None}) == []


def test_duration_thresholds_never_print_sixty_seconds_or_zero_minutes() -> None:
    assert stat_parts({"duration_ms": 50_900}) == ["50.9s"]
    assert stat_parts({"duration_ms": 59_960}) == ["1m 0s"]
    assert stat_parts({"duration_ms": 3_720_000}) == ["1h 2m"]


def test_foreground_result_renders_the_compact_card() -> None:
    result = AgentToolResult(details=_details(description="not repeated"))

    rendered = render_agent_result(result, expanded=False)

    assert rendered is not None
    assert rendered.startswith("[green]✓[/green] [dim]")
    assert "run the suite" not in rendered, "the invocation line already carries it"
    assert "3 turns (max 8)" in rendered


def test_background_spawn_gets_a_one_line_confirmation() -> None:
    result = AgentToolResult(details=_details(status="background", agent_id="agent-7", queued=True))

    collapsed = render_agent_result(result, expanded=False)
    expanded = render_agent_result(
        AgentToolResult(details=_details(status="background", agent_id="agent-7", output_file="/t.jsonl")),
        expanded=True,
    )

    assert collapsed is not None and "Queued in background (agent-7)" in collapsed
    assert expanded is not None
    assert "transcript: /t.jsonl" in expanded
    assert expanded.count("\n") == 1


def test_a_result_without_details_or_status_falls_back() -> None:
    assert render_agent_result(AgentToolResult(details=None), expanded=False) is None
    assert render_agent_result(AgentToolResult(details={}), expanded=False) is None
    assert render_agent_result(AgentToolResult(details="not a mapping"), expanded=False) is None
