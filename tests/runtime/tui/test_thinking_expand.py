"""Click-to-expand for collapsed thinking runs (Task 5, spec 2026-11-08 §6).

A hidden thinking run collapses to one summary row; clicking that row expands
the run in place. Expansion state lives on TuiState (keyed by the run's first
item id) so redraws keep it, and the global Ctrl+T toggle takes precedence —
with thinking shown globally there are no collapsed rows to click.
"""

from __future__ import annotations

import pytest

from baldric.runtime.frontends.tui.app import BaldricTuiApp
from baldric.runtime.frontends.tui.state import ChatItem, TuiState
from tests.helpers.tui_helpers import FakeSession


def test_toggle_thinking_expansion_marks_the_run() -> None:
    state = TuiState()
    first = ChatItem(role="thinking", text="hidden thought")
    state.items.append(first)
    second = ChatItem(role="thinking", text="more thought")
    state.items.append(second)

    state.toggle_thinking_expansion(id(first))

    assert id(first) in state.expanded_thinking_ids
    assert id(second) not in state.expanded_thinking_ids


@pytest.mark.anyio
async def test_clicking_a_collapsed_thinking_run_expands_it() -> None:
    from baldric.runtime.frontends.tui.widgets.core import HiddenThinkingWidget

    app = BaldricTuiApp(FakeSession())
    state = app.state
    state.add_item("user", "question")
    state.add_item("thinking", "hidden reasoning one")
    state.add_item("thinking", "hidden reasoning two")
    state.add_item("assistant", "the answer")

    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        collapsed = list(app.query(HiddenThinkingWidget))
        assert len(collapsed) == 1
        assert state.show_thinking is False

        await pilot.click(collapsed[0])
        await pilot.pause()

        expanded = [
            w
            for w in app.query("TranscriptMessageWidget")
            if w.item.role == "thinking" and w.item.text.startswith("hidden reasoning")
        ]
        assert len(expanded) >= 1
        assert any("hidden reasoning one" in str(w.item.text) for w in expanded)


@pytest.mark.anyio
async def test_expansion_survives_a_state_redraw() -> None:
    from baldric.runtime.frontends.tui.widgets.core import HiddenThinkingWidget

    app = BaldricTuiApp(FakeSession())
    state = app.state
    state.add_item("thinking", "hidden reasoning")
    state.add_item("assistant", "answer")
    state.toggle_thinking_expansion(id(state.items[0]))

    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        assert len(list(app.query(HiddenThinkingWidget))) == 0

        # A fresh redraw (new item arrives) must keep the run expanded.
        state.add_item("assistant", "another answer")
        app._refresh()
        await pilot.pause()

        assert len(list(app.query(HiddenThinkingWidget))) == 0
