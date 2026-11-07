"""Collapsed-thinking summaries shared by the rendering layer.

A hidden thinking run collapses to one layout-stable line that says how much
thinking there was — estimated tokens and block count — without leaking the
thought's content (the toggle exists precisely to hide it), plus the hint
that reveals how to read it.
"""

from __future__ import annotations

from collections.abc import Iterable

from baldric_coding.session.compaction.context_window import estimate_text_tokens

THOUGHT_PREFIX = "Thought: "
HIDDEN_THINKING_HINT = "Ctrl+T to show thinking"


def format_hidden_thinking_summary(texts: Iterable[str]) -> str:
    """Return the one-line collapsed form for a run of hidden thinking blocks."""
    total_tokens = 0
    block_count = 0
    for text in texts:
        block_count += 1
        total_tokens += estimate_text_tokens(text)

    if block_count == 0:
        return f"{THOUGHT_PREFIX}{HIDDEN_THINKING_HINT}"
    count_part = f", {block_count} blocks" if block_count > 1 else ""
    return f"{THOUGHT_PREFIX}~{total_tokens} tokens{count_part} · {HIDDEN_THINKING_HINT}"
