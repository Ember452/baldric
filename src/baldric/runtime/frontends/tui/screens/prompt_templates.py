"""Minimal Textual app for Baldric coding sessions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Literal

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Input,
    Label,
    ListItem,
    ListView,
    Static,
    TextArea,
)

from baldric.runtime.context.prompts import PromptTemplate

if TYPE_CHECKING:
    pass

from baldric.runtime.frontends.tui.screens.session_picker import SessionPickerSearchInput

type BindingEntry = Binding | tuple[str, str] | tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class PromptTemplatePickerResult:
    """Action selected from the prompt-template picker."""

    action: Literal["insert", "edit"]
    template: PromptTemplate


class PromptTemplatePickerScreen(ModalScreen[PromptTemplatePickerResult | None]):
    """Searchable picker for loaded prompt templates."""

    BINDINGS: ClassVar[list[BindingEntry]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("enter", "select_cursor", "Select", show=False),
        Binding("ctrl+e", "edit_cursor", "Edit", show=False, priority=True),
    ]

    def __init__(self, templates: Sequence[PromptTemplate]) -> None:
        super().__init__()
        self.templates = tuple(sorted(templates, key=lambda item: item.name.lower()))
        self.visible_templates = self.templates

    def compose(self) -> ComposeResult:
        with Vertical(id="prompt-template-picker"):
            yield Static("Prompt templates", id="prompt-template-picker-title")
            yield SessionPickerSearchInput(
                placeholder="Search prompt templates", id="prompt-template-picker-search"
            )
            yield ListView(id="prompt-template-picker-list")
            yield Static("", id="prompt-template-picker-help")

    def on_mount(self) -> None:
        self.query_one("#prompt-template-picker-search", Input).focus()
        self._refresh_list()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "prompt-template-picker-search":
            return
        event.stop()
        query = event.value.casefold()
        self.visible_templates = tuple(
            template
            for template in self.templates
            if query in template.name.casefold() or query in (template.description or "").casefold()
        )
        self._refresh_list()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "prompt-template-picker-search":
            event.stop()
            self.action_select_cursor()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        event.stop()
        self.action_select_cursor()

    def action_cursor_up(self) -> None:
        self.query_one("#prompt-template-picker-list", ListView).action_cursor_up()

    def action_cursor_down(self) -> None:
        self.query_one("#prompt-template-picker-list", ListView).action_cursor_down()

    def action_select_cursor(self) -> None:
        template = self._selected_template()
        if template is not None:
            self.dismiss(PromptTemplatePickerResult(action="insert", template=template))

    def action_edit_cursor(self) -> None:
        """Open the selected template in Baldric's prompt editor."""
        template = self._selected_template()
        if template is not None:
            self.dismiss(PromptTemplatePickerResult(action="edit", template=template))

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _selected_template(self) -> PromptTemplate | None:
        picker_list = self.query_one("#prompt-template-picker-list", ListView)
        index = picker_list.index
        if index is None or index >= len(self.visible_templates):
            return None
        return self.visible_templates[index]

    def _refresh_list(self) -> None:
        picker_list = self.query_one("#prompt-template-picker-list", ListView)
        picker_list.clear()
        picker_list.extend(
            ListItem(
                Label(
                    f"/{template.name} — {template.description or 'No description'}",
                    markup=False,
                )
            )
            for template in self.visible_templates
        )
        picker_list.index = 0 if self.visible_templates else None
        if self.visible_templates:
            help_text = "Enter inserts - Ctrl+E edits - Escape closes"
        elif self.templates:
            help_text = "No matching prompt templates - Escape closes"
        else:
            help_text = "No prompt templates loaded - Escape closes"
        self.query_one("#prompt-template-picker-help", Static).update(help_text)


class PromptTemplateEditorScreen(ModalScreen[str | None]):
    """Edit one prompt-template Markdown file inside the TUI."""

    BINDINGS: ClassVar[list[BindingEntry]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "save", "Save", show=False, priority=True),
    ]

    def __init__(self, template: PromptTemplate, source: str) -> None:
        super().__init__()
        self.template = template
        self.source = source

    def compose(self) -> ComposeResult:
        with Vertical(id="prompt-template-editor"):
            yield Static(f"Edit /{self.template.name}", id="prompt-template-editor-title")
            yield Static(str(self.template.path), id="prompt-template-editor-path")
            yield TextArea(self.source, id="prompt-template-editor-input")
            yield Static(
                "Ctrl+S saves - Escape returns without saving",
                id="prompt-template-editor-help",
            )

    def on_mount(self) -> None:
        self.query_one("#prompt-template-editor-input", TextArea).focus()

    def action_save(self) -> None:
        source = self.query_one("#prompt-template-editor-input", TextArea).text
        self.dismiss(source)

    def action_cancel(self) -> None:
        self.dismiss(None)
