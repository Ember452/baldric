"""Minimal Textual app for Baldric coding sessions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import (
    Label,
    ListItem,
    ListView,
    Static,
    TextArea,
)

from baldric.coding.session.session import (
    SessionTreeChoice,
)
from baldric.coding.tui.config import (
    TuiTheme,
)

if TYPE_CHECKING:
    pass

from baldric.coding.tui.screens.extension import ExtensionInputScreen
from baldric.coding.tui.screens.support import (
    _active_tree_choice_index,
    _tree_choice_index,
    _tree_picker_label,
)

type BindingEntry = Binding | tuple[str, str] | tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class TreePickerResult:
    """Tree-picker branch selection."""

    entry_id: str
    summarize: bool = False
    custom_instructions: str | None = None


class _TreePickerListItem(ListItem):
    """Tree entry that keeps inline label colors readable when highlighted."""

    def __init__(
        self,
        choice: SessionTreeChoice,
        *,
        theme: TuiTheme,
        show_label_timestamp: bool = False,
    ) -> None:
        self.choice = choice
        self.theme = theme
        self.show_label_timestamp = show_label_timestamp
        super().__init__(
            Label(
                _tree_picker_label(
                    choice,
                    theme=theme,
                    show_label_timestamp=show_label_timestamp,
                ),
                markup=False,
            )
        )

    def watch_highlighted(self, value: bool) -> None:
        """Recolor inline label spans when the list highlight changes."""
        super().watch_highlighted(value)
        self.query_one(Label).update(
            _tree_picker_label(
                self.choice,
                theme=self.theme,
                highlighted=value,
                show_label_timestamp=self.show_label_timestamp,
            )
        )


class TreePickerScreen(ModalScreen[TreePickerResult | None]):
    """Modal picker for branching from a previous session entry."""

    BINDINGS: ClassVar[list[BindingEntry]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("enter", "select_cursor", "Branch", show=False),
        Binding("s", "select_with_summary", "Summarize", show=False),
        Binding("c", "select_with_custom_summary", "Custom summary", show=False),
        Binding("ctrl+t", "toggle_tool_calls", "Tool calls", show=False),
        Binding("l", "edit_label", "Label", show=False),
        Binding("ctrl+f", "toggle_labeled_only", "Labeled", show=False),
        Binding("ctrl+l", "toggle_label_timestamps", "Label time", show=False),
    ]

    def __init__(
        self,
        choices: Sequence[SessionTreeChoice],
        *,
        theme: TuiTheme,
        on_label_change: Callable[[str, str | None], Awaitable[float]] | None = None,
    ) -> None:
        super().__init__()
        self.choices = tuple(choices)
        self.theme = theme
        self.on_label_change = on_label_change
        self.show_tool_calls = True
        self.labeled_only = False
        self.show_label_timestamps = False

    def compose(self) -> ComposeResult:
        """Compose the tree picker."""
        with Vertical(id="tree-picker"):
            yield Static("Session Tree", id="tree-picker-title")
            yield ListView(
                *self._list_items(),
                id="tree-picker-list",
            )
            yield Static(
                self._help_text(),
                id="tree-picker-help",
            )

    def on_mount(self) -> None:
        """Focus the tree list for keyboard navigation."""
        tree_list = self.query_one("#tree-picker-list", ListView)
        tree_list.index = _active_tree_choice_index(self.choices)
        tree_list.focus()

    def on_key(self, event: Key) -> None:
        """Route tree picker keys to the list."""
        if event.key == "up":
            event.stop()
            self.action_cursor_up()
        elif event.key == "down":
            event.stop()
            self.action_cursor_down()
        elif event.key == "enter":
            event.stop()
            self.action_select_cursor()
        elif event.key == "s":
            event.stop()
            self.action_select_with_summary()
        elif event.key == "c":
            event.stop()
            self.action_select_with_custom_summary()
        elif event.key == "ctrl+t":
            event.stop()
            self.action_toggle_tool_calls()
        elif event.key == "l":
            event.stop()
            self.action_edit_label()
        elif event.key == "ctrl+f":
            event.stop()
            self.action_toggle_labeled_only()
        elif event.key == "ctrl+l":
            event.stop()
            self.action_toggle_label_timestamps()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Dismiss with the selected entry id."""
        self.dismiss(TreePickerResult(entry_id=self._visible_choices()[event.index].entry_id))

    def action_cursor_up(self) -> None:
        """Move to the previous tree entry."""
        self.query_one("#tree-picker-list", ListView).action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move to the next tree entry."""
        self.query_one("#tree-picker-list", ListView).action_cursor_down()

    def action_select_cursor(self) -> None:
        """Branch from the highlighted entry without a summary."""
        self.query_one("#tree-picker-list", ListView).action_select_cursor()

    def action_select_with_summary(self) -> None:
        """Branch from the highlighted entry with a branch summary."""
        tree_list = self.query_one("#tree-picker-list", ListView)
        index = tree_list.index
        if index is None:
            return
        self.dismiss(TreePickerResult(entry_id=self._visible_choices()[index].entry_id, summarize=True))

    def action_select_with_custom_summary(self) -> None:
        """Branch from the highlighted entry with custom summary instructions."""
        tree_list = self.query_one("#tree-picker-list", ListView)
        index = tree_list.index
        if index is None:
            return
        self.app.push_screen(
            BranchSummaryInstructionsScreen(theme=self.theme),
            callback=lambda instructions: self._dismiss_with_custom_summary(index, instructions),
        )

    def _dismiss_with_custom_summary(self, index: int, instructions: str | None) -> None:
        if instructions is None:
            return
        visible_choices = self._visible_choices()
        if index >= len(visible_choices):
            return
        self.dismiss(
            TreePickerResult(
                entry_id=visible_choices[index].entry_id,
                summarize=True,
                custom_instructions=instructions,
            )
        )

    def action_toggle_tool_calls(self) -> None:
        """Toggle tool-call entries in the tree picker."""
        selected_entry_id = self._selected_entry_id()
        self.show_tool_calls = not self.show_tool_calls
        self.run_worker(self._refresh_choices(selected_entry_id=selected_entry_id))

    def action_toggle_labeled_only(self) -> None:
        """Toggle the Pi-style labeled-entry filter."""
        selected_entry_id = self._selected_entry_id()
        self.labeled_only = not self.labeled_only
        self.run_worker(self._refresh_choices(selected_entry_id=selected_entry_id))

    def action_toggle_label_timestamps(self) -> None:
        """Toggle display of the latest label-change timestamp."""
        selected_entry_id = self._selected_entry_id()
        self.show_label_timestamps = not self.show_label_timestamps
        self.run_worker(self._refresh_choices(selected_entry_id=selected_entry_id))

    def action_edit_label(self) -> None:
        """Open a prefilled editor; submitting an empty value clears the label."""
        selected = self._selected_choice()
        if selected is None:
            return
        self.app.push_screen(
            ExtensionInputScreen(
                "Label this session entry",
                "Empty clears the label",
                theme=self.theme,
                value=selected.bookmark_label or "",
            ),
            callback=lambda value: self._handle_label_input(selected.entry_id, value),
        )

    def _handle_label_input(self, entry_id: str, value: str | None) -> None:
        if value is None:
            return
        self.run_worker(self._apply_label(entry_id, value))

    async def _apply_label(self, entry_id: str, value: str) -> None:
        normalized = value.strip() or None
        try:
            if self.on_label_change is None:
                raise RuntimeError("Session labels are not available.")
            timestamp = await self.on_label_change(entry_id, normalized)
        except Exception as exc:  # noqa: BLE001 - keep the tree open and surface persistence errors
            self.app.notify(f"Error: {exc}", severity="error")
            return
        self.choices = tuple(
            replace(
                choice,
                bookmark_label=normalized,
                label_timestamp=timestamp if normalized is not None else None,
            )
            if choice.entry_id == entry_id
            else choice
            for choice in self.choices
        )
        await self._refresh_choices(selected_entry_id=entry_id)

    async def _refresh_choices(self, *, selected_entry_id: str | None = None) -> None:
        selected_entry_id = selected_entry_id or self._selected_entry_id()
        tree_list = self.query_one("#tree-picker-list", ListView)
        await tree_list.clear()
        await tree_list.extend(self._list_items())
        visible_choices = self._visible_choices()
        tree_list.index = _tree_choice_index(visible_choices, selected_entry_id) if visible_choices else None
        self.query_one("#tree-picker-help", Static).update(self._help_text())

    def _selected_entry_id(self) -> str | None:
        tree_list = self.query_one("#tree-picker-list", ListView)
        index = tree_list.index
        visible_choices = self._visible_choices()
        if index is None or index >= len(visible_choices):
            return None
        return visible_choices[index].entry_id

    def _selected_choice(self) -> SessionTreeChoice | None:
        entry_id = self._selected_entry_id()
        return next((choice for choice in self.choices if choice.entry_id == entry_id), None)

    def _visible_choices(self) -> tuple[SessionTreeChoice, ...]:
        return tuple(
            choice
            for choice in self.choices
            if (self.show_tool_calls or not choice.is_tool_call)
            and (not self.labeled_only or choice.bookmark_label is not None)
        )

    def _list_items(self) -> list[ListItem]:
        return [
            _TreePickerListItem(
                choice,
                theme=self.theme,
                show_label_timestamp=self.show_label_timestamps,
            )
            for choice in self._visible_choices()
        ]

    def _help_text(self) -> str:
        tool_call_state = "shown" if self.show_tool_calls else "hidden"
        labeled_state = "only" if self.labeled_only else "all"
        time_state = "shown" if self.show_label_timestamps else "hidden"
        return (
            "Enter branch · L label/clear · S summary · C custom · "
            f"Ctrl+T tool calls {tool_call_state} · Ctrl+F labels {labeled_state} · "
            f"Ctrl+L times {time_state} · Esc close"
        )

    def action_cancel(self) -> None:
        """Close the picker without selecting an entry."""
        self.dismiss(None)


class BranchSummaryInstructionsScreen(ModalScreen[str | None]):
    """Prompt for custom branch-summary instructions."""

    BINDINGS: ClassVar[list[BindingEntry]] = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, *, theme: TuiTheme) -> None:
        super().__init__()
        self.theme = theme

    def compose(self) -> ComposeResult:
        """Compose the custom-instructions prompt."""
        with Vertical(id="branch-summary-instructions"):
            yield Static(
                "Custom summarization instructions",
                id="branch-summary-instructions-title",
            )
            yield TextArea(id="branch-summary-instructions-input")
            yield Static(
                "Ctrl+Enter submits - Escape returns to tree",
                id="branch-summary-instructions-help",
            )

    def on_mount(self) -> None:
        """Focus the instruction editor."""
        self.query_one("#branch-summary-instructions-input", TextArea).focus()

    def on_key(self, event: Key) -> None:
        """Submit on Ctrl+Enter and cancel on Escape."""
        if event.key == "ctrl+enter":
            event.stop()
            self.action_submit()
        elif event.key == "escape":
            event.stop()
            self.action_cancel()

    def action_submit(self) -> None:
        """Submit custom instructions."""
        value = self.query_one("#branch-summary-instructions-input", TextArea).text.strip()
        self.dismiss(value or None)

    def action_cancel(self) -> None:
        """Cancel custom instructions."""
        self.dismiss(None)
