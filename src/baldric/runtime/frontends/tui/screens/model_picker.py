"""Minimal Textual app for Baldric coding sessions."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, ClassVar, Literal, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import (
    Input,
    OptionList,
    Static,
)
from textual.worker import Worker

from baldric.runtime.frontends.tui.config import (
    TuiTheme,
)
from baldric.runtime.session.session import (
    ModelChoice,
)

if TYPE_CHECKING:
    pass

from baldric.runtime.frontends.tui.screens.support import (
    _filter_model_choices,
    _model_picker_label,
)

type BindingEntry = Binding | tuple[str, str] | tuple[str, str, str]


class ModelPickerSearchInput(Input):
    """Search input that keeps model-picker control keys local to the picker."""

    BINDINGS: ClassVar[list[BindingEntry]] = [
        Binding("escape", "cancel", "Cancel", show=False, priority=True),
        Binding("tab", "toggle_mode", "Mode", show=False, priority=True),
        Binding("ctrl+i", "toggle_mode", "Mode", show=False, priority=True),
        Binding("up", "cursor_up", "Up", show=False, priority=True),
        Binding("down", "cursor_down", "Down", show=False, priority=True),
    ]

    def _picker(self) -> ModelPickerScreen:
        return cast(ModelPickerScreen, self.screen)

    def on_key(self, event: Key) -> None:
        """Route picker control keys before the input edits its text."""
        if event.key == "up":
            event.stop()
            event.prevent_default()
            self.action_cursor_up()
        elif event.key == "down":
            event.stop()
            event.prevent_default()
            self.action_cursor_down()
        elif event.key in {"tab", "ctrl+i"}:
            event.stop()
            event.prevent_default()
            self.action_toggle_mode()
        elif event.key == "escape":
            event.stop()
            event.prevent_default()
            self.action_cancel()

    def action_cursor_up(self) -> None:
        """Move the model picker selection up."""
        self._picker().action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move the model picker selection down."""
        self._picker().action_cursor_down()

    def action_toggle_mode(self) -> None:
        """Toggle between all and scoped picker modes."""
        self._picker().action_toggle_mode()

    def action_cancel(self) -> None:
        """Close the model picker."""
        self._picker().action_cancel()


class ModelPickerScreen(ModalScreen[ModelChoice | None]):
    """Model picker for the active TUI provider."""

    BINDINGS: ClassVar[list[BindingEntry]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("tab", "toggle_mode", "Mode", show=False, priority=True),
        Binding("ctrl+i", "toggle_mode", "Mode", show=False, priority=True),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("enter", "accept_model", "Select", show=False),
    ]

    def __init__(
        self,
        choices: Sequence[ModelChoice],
        *,
        scoped_choices: Sequence[ModelChoice],
        current_model: str,
        provider_name: str,
        theme: TuiTheme,
        on_toggle_scoped: Callable[[ModelChoice], Sequence[ModelChoice]] | None = None,
        picker_kind: Literal["model", "scoped"] = "model",
        initial_thinking_level: str | None = None,
    ) -> None:
        super().__init__()
        self.on_first_refresh: Callable[[], None] | None = None
        self.refresh_worker: Worker[None] | None = None
        self.initial_thinking_level = initial_thinking_level
        available = tuple(dict.fromkeys(choices))
        self.scoped_choices = tuple(dict.fromkeys(scoped_choices))
        self.unavailable_choices = frozenset(self.scoped_choices) - frozenset(available)
        self.choices = tuple(dict.fromkeys((*available, *self.scoped_choices)))
        self.visible_choices = self.choices
        self.current_model = current_model
        self.provider_name = provider_name
        self.theme = theme
        self.on_toggle_scoped = on_toggle_scoped
        self.picker_kind = picker_kind
        self.mode: Literal["all", "scoped"] = "all"
        self.search_value = ""

    def compose(self) -> ComposeResult:
        """Compose the model picker."""
        with Vertical(id="model-picker"):
            title = f"Model: {self.provider_name}" if self.picker_kind == "model" else "Scoped models"
            yield Static(title, id="model-picker-title")
            yield Static("", id="model-picker-tabs")
            yield ModelPickerSearchInput(placeholder="Search models", id="model-picker-search")
            yield OptionList(
                *(self._label_for_choice(choice) for choice in self.choices),
                id="model-picker-list",
                markup=False,
                compact=True,
            )
            yield Static("", id="model-picker-help")

    def on_mount(self) -> None:
        """Focus the search field."""
        search = self.query_one("#model-picker-search", Input)
        search.focus()
        # compose() already mounted the cached rows; only set selection/help.
        self._refresh_model_list(rebuild_rows=False)
        if self.on_first_refresh is not None:
            self.call_after_refresh(self.on_first_refresh)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter model choices as the search value changes."""
        if event.input.id != "model-picker-search":
            return
        event.stop()
        if self.search_value == event.value:
            return
        self.search_value = event.value
        self._refresh_model_list()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Select the highlighted model from the search field."""
        if event.input.id != "model-picker-search":
            return
        event.stop()
        self._select_visible_choice()

    def _reset_model_list_index(self) -> None:
        """Move selection to the current model or first visible row."""
        model_list = self.query_one("#model-picker-list", OptionList)
        if not self.visible_choices:
            model_list.highlighted = None
            return
        try:
            model_list.highlighted = self.visible_choices.index(
                ModelChoice(provider_name=self.provider_name, model=self.current_model)
            )
        except ValueError:
            model_list.highlighted = 0

    def on_key(self, event: Key) -> None:
        """Route model picker keys to the list."""
        if event.key == "up":
            event.stop()
            self.action_cursor_up()
        elif event.key == "down":
            event.stop()
            self.action_cursor_down()
        elif event.key == "enter":
            event.stop()
            self.action_accept_model()
        elif event.key in {"tab", "ctrl+i"}:
            event.stop()
            self.action_toggle_mode()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle the selected row."""
        event.stop()
        self._select_visible_choice()

    def action_cursor_up(self) -> None:
        """Move to the previous model."""
        self.query_one("#model-picker-list", OptionList).action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move to the next model."""
        self.query_one("#model-picker-list", OptionList).action_cursor_down()

    def action_accept_model(self) -> None:
        """Select the highlighted model."""
        self._select_visible_choice()

    def action_toggle_mode(self) -> None:
        """Toggle between all models and scoped models."""
        self.mode = "scoped" if self.mode == "all" else "all"
        self._refresh_model_list()

    def action_toggle_scoped(self) -> None:
        """Add or remove the highlighted model from scoped models."""
        if self.on_toggle_scoped is None or not self.visible_choices:
            return
        model_list = self.query_one("#model-picker-list", OptionList)
        index = model_list.highlighted
        if index is None:
            return
        choice = self.visible_choices[index]
        self.scoped_choices = tuple(dict.fromkeys(self.on_toggle_scoped(choice)))
        self._refresh_model_list()

    def action_cancel(self) -> None:
        """Close without selecting a model."""
        self.cancel_refresh()
        self.dismiss(None)

    def cancel_refresh(self) -> None:
        """Stop work owned by this picker when it is no longer visible."""
        if self.refresh_worker is not None and not self.refresh_worker.is_finished:
            self.refresh_worker.cancel()

    def on_unmount(self) -> None:
        """Also cancel when a caller removes the picker without dismissing it."""
        self.cancel_refresh()

    def update_choices(
        self,
        choices: Sequence[ModelChoice],
        scoped_choices: Sequence[ModelChoice],
    ) -> None:
        """Publish a refreshed catalog without replacing the open picker."""
        available = tuple(dict.fromkeys(choices))
        scoped = tuple(dict.fromkeys(scoped_choices))
        updated = tuple(dict.fromkeys((*available, *scoped)))
        unavailable = frozenset(scoped) - frozenset(available)
        if (
            scoped == self.scoped_choices
            and updated == self.choices
            and unavailable == self.unavailable_choices
        ):
            return
        self.scoped_choices = scoped
        self.unavailable_choices = unavailable
        self.choices = updated
        self._refresh_model_list()

    def _select_visible_choice(self) -> None:
        if not self.visible_choices:
            return
        model_list = self.query_one("#model-picker-list", OptionList)
        index = model_list.highlighted
        if index is None:
            return
        choice = self.visible_choices[index]
        if self.picker_kind == "scoped":
            self.action_toggle_scoped()
            return
        if choice in self.unavailable_choices:
            return
        self.cancel_refresh()
        self.dismiss(choice)

    def _label_for_choice(self, choice: ModelChoice) -> str:
        return _model_picker_label(
            choice,
            current_model=self.current_model,
            current_provider=self.provider_name,
            scoped=choice in self.scoped_choices,
            unavailable=choice in self.unavailable_choices,
        )

    def _refresh_model_list(self, *, rebuild_rows: bool = True) -> None:
        base_choices = self.scoped_choices if self.mode == "scoped" else self.choices
        self.visible_choices = _filter_model_choices(base_choices, self.search_value)
        if rebuild_rows:
            model_list = self.query_one("#model-picker-list", OptionList)
            model_list.clear_options()
            model_list.add_options(self._label_for_choice(choice) for choice in self.visible_choices)
        self._reset_model_list_index()
        scope_count = len(self.scoped_choices)
        tabs = self.query_one("#model-picker-tabs", Static)
        if self.picker_kind == "scoped":
            if self.mode == "all":
                tabs.update("Tabs: ● All models  ○ Scoped models")
                help_text = (
                    "all models: no matching models - Tab switches to scoped models"
                    if not self.visible_choices
                    else (
                        "All models - Enter toggles scoped model - Tab switches tabs - "
                        f"{scope_count} scoped - active model is unchanged"
                    )
                )
            else:
                tabs.update("Tabs: ○ All models  ● Scoped models")
                help_text = (
                    "scoped models: no scoped models - Tab switches to all models"
                    if not self.visible_choices
                    else "Scoped models - Enter removes scoped model - Tab switches tabs"
                )
        elif self.mode == "all":
            tabs.update("Tabs: ● All models  ○ Scoped models")
            help_text = (
                "all models: no matching models - Tab switches to scoped models"
                if not self.visible_choices
                else (f"All models - Enter selects active model - Tab switches tabs - {scope_count} scoped")
            )
        else:
            tabs.update("Tabs: ○ All models  ● Scoped models")
            help_text = (
                "scoped models: no matching models - Tab switches to all models"
                if not self.visible_choices
                else "Scoped models - Enter selects active model - Tab switches tabs"
            )
        self.query_one("#model-picker-help", Static).update(help_text)
