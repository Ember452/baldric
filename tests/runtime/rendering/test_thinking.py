"""Tests for the collapsed-thinking summary line."""

from baldric.runtime.rendering.thinking import (
    HIDDEN_THINKING_HINT,
    format_hidden_thinking_summary,
)
from baldric.runtime.session.compaction.context_window import estimate_text_tokens


def test_single_block_reports_estimated_tokens_without_leaking_content() -> None:
    summary = format_hidden_thinking_summary(["secret plan"])

    assert summary == f"Thought: ~{estimate_text_tokens('secret plan')} tokens · Ctrl+T to show thinking"
    assert "secret" not in summary


def test_multi_block_run_counts_blocks() -> None:
    blocks = ["first plan", "second plan"]
    expected_tokens = sum(estimate_text_tokens(block) for block in blocks)

    summary = format_hidden_thinking_summary(blocks)

    assert summary == f"Thought: ~{expected_tokens} tokens, 2 blocks · Ctrl+T to show thinking"
    assert "plan" not in summary


def test_empty_run_falls_back_to_the_hint() -> None:
    assert format_hidden_thinking_summary([]) == f"Thought: {HIDDEN_THINKING_HINT}"


def test_cjk_thinking_token_estimate_stays_bounded() -> None:
    summary = format_hidden_thinking_summary(["宽" * 200])

    assert "tokens" in summary
    assert "宽" not in summary
