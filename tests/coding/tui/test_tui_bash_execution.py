"""A resumed transcript still shows terminal-command output.

Terminal commands used to persist as user messages, so a reload showed them
without any TUI support. They are now `bashExecution` messages (pi's shape), and
the transcript loader renders the same text for them.
"""

from __future__ import annotations

from baldric.coding.tui.state import TuiState
from baldric.protocol.messages import BashExecutionMessage


def test_a_loaded_bash_execution_renders_as_a_user_item() -> None:
    state = TuiState()

    state.load_messages([BashExecutionMessage(command="printf hello", output="hello", exit_code=0)])

    assert [item.role for item in state.items] == ["user"]
    assert "Terminal command executed by the user." in (state.items[0].text or "")
    assert "printf hello" in (state.items[0].text or "")


def test_an_excluded_execution_is_still_visible_in_the_transcript() -> None:
    state = TuiState()

    state.load_messages([BashExecutionMessage(command="secret", output="hidden", exclude_from_context=True)])

    assert len(state.items) == 1
