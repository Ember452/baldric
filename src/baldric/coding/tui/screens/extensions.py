"""Searchable read-only inventory of loaded extensions and diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView, Static

from baldric.coding.context.resources import ResourceDiagnostic
from baldric.coding.extensions.runtime import ExtensionRuntime
from baldric.coding.tui.config import TuiTheme

type BindingEntry = Binding | tuple[str, str] | tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class ExtensionInventoryItem:
    """One searchable extension or diagnostic row."""

    name: str
    detail: str
    search_text: str


class ExtensionsScreen(ModalScreen[None]):
    """Searchable read-only inventory of extensions and diagnostics."""

    BINDINGS: ClassVar[list[BindingEntry]] = [Binding("escape", "cancel", "Close")]

    def __init__(self, runtime: ExtensionRuntime, *, theme: TuiTheme) -> None:
        super().__init__()
        del theme
        info = tuple(runtime.extension_info)
        diagnostics = tuple(
            diagnostic
            for diagnostic in runtime.diagnostics
            if isinstance(diagnostic, ResourceDiagnostic) and diagnostic.kind == "extension"
        )
        rows = [
            ExtensionInventoryItem(
                name=extension.name,
                detail=f"{extension.scope} · {extension.status}\n{extension.path or extension.name}",
                search_text=(
                    f"{extension.name} {extension.scope} {extension.status} {extension.path or ''}"
                ).lower(),
            )
            for extension in info
        ]
        rows.extend(
            ExtensionInventoryItem(
                name=diagnostic.name or (diagnostic.path.name if diagnostic.path else "Diagnostic"),
                detail=f"{diagnostic.severity} · {diagnostic.message}"
                + (f"\n{diagnostic.path}" if diagnostic.path else ""),
                search_text=diagnostic.format().lower(),
            )
            for diagnostic in diagnostics
        )
        self.rows = tuple(rows)
        self.visible_rows = self.rows

    def compose(self) -> ComposeResult:
        with Vertical(id="extensions-screen"):
            yield Static("Extensions", id="extensions-title")
            yield Input(placeholder="Search extensions", id="extensions-search")
            yield ListView(id="extensions-list")
            yield Static("Escape closes", id="extensions-help")

    def on_mount(self) -> None:
        self.query_one("#extensions-search", Input).focus()
        self._refresh_rows("")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "extensions-search":
            event.stop()
            self._refresh_rows(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _refresh_rows(self, query: str) -> None:
        needle = query.strip().lower()
        self.visible_rows = tuple(row for row in self.rows if needle in row.search_text)
        listing = self.query_one("#extensions-list", ListView)
        listing.clear()
        if self.visible_rows:
            listing.extend(
                ListItem(Label(f"{row.name}\n{row.detail}", markup=False)) for row in self.visible_rows
            )
            help_text = "Escape closes"
        else:
            empty = "No extensions loaded" if not self.rows and not needle else "No matching extensions"
            listing.append(ListItem(Label(empty, markup=False), disabled=True))
            help_text = f"{empty} · Escape closes"
        self.query_one("#extensions-help", Static).update(help_text)
