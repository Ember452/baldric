"""Streaming code-fence convergence (Task 4, spec 2026-11-08 §6 流式收敛).

Probe conclusion (2026-11-09): Textual's incremental Markdown already renders
an unclosed fence as a real, styled ``MarkdownFence`` while streaming — the
"plain text flips to rich at the closing fence" step the spec worried about
does not exist in the current ``TranscriptMarkdownStream`` architecture. The
streaming/finalized CSS states (``-streaming`` / ``-finalized``) already tune
the fence chrome per phase. This test documents that behaviour as a
regression guard instead of new code.
"""

from __future__ import annotations

import pytest

from baldric.runtime.rendering.themes import BALDRIC_DARK_THEME
from baldric.runtime.tui.app import BaldricTuiApp
from baldric.runtime.tui.state import ChatItem
from baldric.runtime.tui.widgets.core import StreamingTranscriptMessageWidget
from tests.helpers.tui_helpers import FakeSession


def _fence_count(widget: StreamingTranscriptMessageWidget) -> int:
    return len(list(widget.query("MarkdownFence")))


@pytest.mark.anyio
async def test_streaming_code_fence_renders_and_converges() -> None:
    app = BaldricTuiApp(FakeSession())

    async with app.run_test(size=(120, 30)) as pilot:
        widget = StreamingTranscriptMessageWidget(
            ChatItem(role="assistant", text=""), theme=BALDRIC_DARK_THEME
        )
        await app.query_one("#transcript").mount(widget)
        await pilot.pause()

        # An unclosed fence already renders as a styled MarkdownFence mid-stream.
        await widget.append_fragment("Intro paragraph.\n\n```python\nx = 1\n")
        await pilot.pause()
        await pilot.pause()
        assert _fence_count(widget) == 1

        # Closing the fence and finalizing keeps the block converged.
        await widget.append_fragment("y = 2\n```\n\nAfter the fence.")
        await widget.finalize()
        await pilot.pause()
        assert _fence_count(widget) == 1
        paragraphs = [str(p.render()) for p in widget.query("MarkdownParagraph")]
        assert any("After the fence." in text for text in paragraphs)
