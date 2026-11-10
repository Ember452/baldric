"""Minimal Textual app for Baldric coding sessions."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import (
    Input,
    Label,
    ListItem,
    ListView,
    Static,
)

from baldric.coding.tui.config import (
    TuiTheme,
)

if TYPE_CHECKING:
    pass


type BindingEntry = Binding | tuple[str, str] | tuple[str, str, str]


class ExtensionSelectScreen(ModalScreen[str | None]):
    """Modal option picker backing `context.ui.select`.

    Binding/key wiring mirrors `SessionPickerScreen`. The app binds Up/Down/
    Enter with priority for prompt completions but forwards them to any active
    screen exposing cursor actions (`CursorListScreen`/`SelectableListScreen`
    in `screens/support.py`), so no per-screen registration is needed.
    """

    BINDINGS: ClassVar[list[BindingEntry]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("enter", "select_cursor", "Select", show=False),
    ]

    def __init__(
        self,
        title: str,
        options: Sequence[str],
        *,
        theme: TuiTheme,
    ) -> None:
        super().__init__()
        self.title_text = title
        self.options = tuple(options)
        self.theme = theme

    def compose(self) -> ComposeResult:
        """Compose the option picker."""
        with Vertical(id="extension-select"):
            yield Static(self.title_text, id="extension-select-title", markup=False)
            yield ListView(
                *[ListItem(Label(option, markup=False)) for option in self.options],
                id="extension-select-list",
            )
            yield Static("Enter selects - Escape cancels", id="extension-select-help")

    def on_mount(self) -> None:
        """Focus the option list for keyboard navigation."""
        option_list = self.query_one("#extension-select-list", ListView)
        option_list.index = 0
        option_list.focus()

    def on_key(self, event: Key) -> None:
        """Route arrow and enter keys to the option list."""
        if event.key == "up":
            event.stop()
            self.action_cursor_up()
        elif event.key == "down":
            event.stop()
            self.action_cursor_down()
        elif event.key == "enter":
            event.stop()
            self.action_select_cursor()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Dismiss with the chosen option."""
        self.dismiss(self.options[event.index])

    def action_cursor_up(self) -> None:
        """Move to the previous option."""
        self.query_one("#extension-select-list", ListView).action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move to the next option."""
        self.query_one("#extension-select-list", ListView).action_cursor_down()

    def action_select_cursor(self) -> None:
        """Select the highlighted option."""
        self.query_one("#extension-select-list", ListView).action_select_cursor()

    def action_cancel(self) -> None:
        """Close without choosing an option."""
        self.dismiss(None)


class ExtensionConfirmScreen(ModalScreen[bool]):
    """Modal yes/no confirmation backing `context.ui.confirm`.

    Binding/key wiring mirrors `SessionPickerScreen`; see
    `ExtensionSelectScreen` for the app-level Up/Down allowlist requirement.
    """

    BINDINGS: ClassVar[list[BindingEntry]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("enter", "select_cursor", "Select", show=False),
    ]

    def __init__(self, title: str, message: str, *, theme: TuiTheme) -> None:
        super().__init__()
        self.title_text = title
        self.message = message
        self.theme = theme

    def compose(self) -> ComposeResult:
        """Compose the confirmation dialog."""
        with Vertical(id="extension-confirm"):
            yield Static(self.title_text, id="extension-confirm-title", markup=False)
            yield Static(self.message, id="extension-confirm-message", markup=False)
            yield ListView(
                ListItem(Label("Yes", markup=False)),
                ListItem(Label("No", markup=False)),
                id="extension-confirm-list",
            )
            yield Static("Enter selects - Escape cancels", id="extension-confirm-help")

    def on_mount(self) -> None:
        """Focus the choice list."""
        choice_list = self.query_one("#extension-confirm-list", ListView)
        choice_list.index = 0
        choice_list.focus()

    def on_key(self, event: Key) -> None:
        """Route arrow and enter keys to the choice list."""
        if event.key == "up":
            event.stop()
            self.action_cursor_up()
        elif event.key == "down":
            event.stop()
            self.action_cursor_down()
        elif event.key == "enter":
            event.stop()
            self.action_select_cursor()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Dismiss with the confirmation result (Yes is index 0)."""
        self.dismiss(event.index == 0)

    def action_cursor_up(self) -> None:
        """Move to the previous choice."""
        self.query_one("#extension-confirm-list", ListView).action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move to the next choice."""
        self.query_one("#extension-confirm-list", ListView).action_cursor_down()

    def action_select_cursor(self) -> None:
        """Select the highlighted choice."""
        self.query_one("#extension-confirm-list", ListView).action_select_cursor()

    def action_cancel(self) -> None:
        """Close, declining the confirmation."""
        self.dismiss(False)


class ExtensionInputScreen(ModalScreen[str | None]):
    """Modal single-line text prompt backing `context.ui.input`."""

    BINDINGS: ClassVar[list[BindingEntry]] = [Binding("escape", "cancel", "Cancel")]

    def __init__(
        self,
        title: str,
        placeholder: str = "",
        *,
        theme: TuiTheme,
        value: str = "",
    ) -> None:
        super().__init__()
        self.title_text = title
        self.placeholder = placeholder
        self.theme = theme
        self.value = value

    def compose(self) -> ComposeResult:
        """Compose the text prompt."""
        with Vertical(id="extension-input"):
            yield Static(self.title_text, id="extension-input-title", markup=False)
            yield Input(
                value=self.value,
                placeholder=self.placeholder,
                id="extension-input-field",
            )
            yield Static("Enter submits - Escape cancels", id="extension-input-help")

    def on_mount(self) -> None:
        """Focus the text field."""
        self.query_one("#extension-input-field", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Dismiss with the entered text."""
        if event.input.id != "extension-input-field":
            return
        event.stop()
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        """Close without submitting text."""
        self.dismiss(None)
