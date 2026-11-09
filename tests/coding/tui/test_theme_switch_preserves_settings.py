"""P1 regression: switching theme must not reset approval_mode / editor_command.

BaldricTuiApp._replace_tui_settings used to rebuild TuiSettings by hand and
dropped approval_mode and editor_command, silently resetting tool-approval to
"auto" and persisting that on every theme switch. dataclasses.replace preserves
all unrelated fields.
"""

from __future__ import annotations

from baldric_coding.tui.app import BaldricTuiApp
from baldric_coding.tui.config import TuiSettings
from tests.helpers.tui_helpers import FakeSession


def test_theme_switch_preserves_approval_and_editor() -> None:
    app = BaldricTuiApp(
        FakeSession(),
        tui_settings=TuiSettings(approval_mode="ask", editor_command="code -w"),
    )
    assert app.tui_settings.approval_mode == "ask"
    assert app.tui_settings.editor_command == "code -w"

    app._replace_tui_settings(theme="baldric-light")

    assert app.tui_settings.theme == "baldric-light"
    assert app.tui_settings.approval_mode == "ask"
    assert app.tui_settings.editor_command == "code -w"


def test_theme_switch_default_approval_still_works() -> None:
    app = BaldricTuiApp(FakeSession(), tui_settings=TuiSettings())
    app._replace_tui_settings(theme="high-contrast")
    assert app.tui_settings.approval_mode == "auto"
    assert app.tui_settings.editor_command is None
