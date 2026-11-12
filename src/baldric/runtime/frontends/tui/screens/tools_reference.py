"""Minimal Textual app for Baldric coding sessions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, ClassVar, cast

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

from baldric.protocol.tools import AgentTool
from baldric.runtime.frontends.tui.config import (
    TuiTheme,
)

if TYPE_CHECKING:
    pass

from baldric.runtime.frontends.tui.screens.command_output import CommandOutputScreen

type BindingEntry = Binding | tuple[str, str] | tuple[str, str, str]


class ToolsReferenceSearchInput(Input):
    """Search input that keeps tool-reference navigation local."""

    BINDINGS: ClassVar[list[BindingEntry]] = [
        Binding("escape", "cancel", "Cancel", show=False, priority=True),
        Binding("up", "cursor_up", "Up", show=False, priority=True),
        Binding("down", "cursor_down", "Down", show=False, priority=True),
        Binding("enter", "open_selected", "Open", show=False, priority=True),
    ]

    def _reference(self) -> ToolsReferenceScreen:
        return cast(ToolsReferenceScreen, self.screen)

    def on_key(self, event: Key) -> None:
        """Route navigation without changing the search text."""
        if event.key == "up":
            event.stop()
            event.prevent_default()
            self._reference().action_cursor_up()
        elif event.key == "down":
            event.stop()
            event.prevent_default()
            self._reference().action_cursor_down()
        elif event.key == "escape":
            event.stop()
            event.prevent_default()
            self._reference().action_cancel()
        elif event.key == "enter":
            event.stop()
            event.prevent_default()
            self._reference().action_open_selected()

    def action_open_selected(self) -> None:
        self._reference().action_open_selected()


class ToolsReferenceScreen(ModalScreen[None]):
    """Searchable tool table with navigable description details."""

    BINDINGS: ClassVar[list[BindingEntry]] = [
        Binding("escape", "cancel", "Close"),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("enter", "open_selected", "Open", show=False),
    ]

    def __init__(
        self,
        tools: Sequence[AgentTool],
        *,
        extension_sources: Mapping[str, str],
        theme: TuiTheme,
    ) -> None:
        super().__init__()
        self.extension_sources = dict(extension_sources)
        self.tools = self._order_tools(tools)
        self.visible_tools = self.tools
        self.theme = theme

    def compose(self) -> ComposeResult:
        """Compose the tool reference."""
        with Vertical(id="tools-reference"):
            yield Static("Available tools", id="tools-reference-title")
            yield ToolsReferenceSearchInput(placeholder="Search tools", id="tools-reference-search")
            yield Static(
                self._table_row("Tool", "Origin", "Description"),
                id="tools-reference-header",
            )
            yield ListView(id="tools-reference-list")
            yield Static("Enter opens description - Escape closes", id="tools-reference-help")

    def on_mount(self) -> None:
        """Populate the list and focus search on open."""
        self._refresh_tools("")
        self.query_one("#tools-reference-search", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "tools-reference-search":
            event.stop()
            self._refresh_tools(event.value)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Open the selected tool's full description."""
        event.stop()
        self._open_tool(event.index)

    def action_cursor_up(self) -> None:
        self.query_one("#tools-reference-list", ListView).action_cursor_up()

    def action_cursor_down(self) -> None:
        self.query_one("#tools-reference-list", ListView).action_cursor_down()

    def action_open_selected(self) -> None:
        tool_list = self.query_one("#tools-reference-list", ListView)
        if tool_list.index is not None:
            self._open_tool(tool_list.index)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _open_tool(self, index: int) -> None:
        if index >= len(self.visible_tools):
            return
        tool = self.visible_tools[index]
        self.app.push_screen(
            CommandOutputScreen(
                f"{tool.name} — {self._source_label(tool)}",
                tool.description or "No description",
                theme=self.theme,
            )
        )

    def _refresh_tools(self, query: str) -> None:
        needle = query.casefold().strip()
        self.visible_tools = tuple(
            tool
            for tool in self.tools
            if not needle
            or needle in tool.name.casefold()
            or needle in tool.label.casefold()
            or needle in tool.description.casefold()
            or needle in self._source_label(tool).casefold()
        )
        tool_list = self.query_one("#tools-reference-list", ListView)
        tool_list.clear()
        if not self.visible_tools:
            message = "No tools available." if not self.tools else "No tools match your search."
            tool_list.append(ListItem(Label(message, markup=False), disabled=True))
            return
        tool_list.extend(
            [
                ListItem(
                    Label(
                        self._table_row(
                            tool.name,
                            self._source_label(tool),
                            f"{len(tool.description)} chars",
                        ),
                        markup=False,
                    )
                )
                for tool in self.visible_tools
            ]
        )
        tool_list.index = 0

    def _order_tools(self, tools: Sequence[AgentTool]) -> tuple[AgentTool, ...]:
        tools_by_name = {tool.name: tool for tool in tools}
        builtins = sorted(
            (tool for tool in tools if tool.name not in self.extension_sources),
            key=lambda tool: tool.name.casefold(),
        )
        extension_tools: list[AgentTool] = []
        seen_extensions: set[str] = set()
        for extension in self.extension_sources.values():
            if extension in seen_extensions:
                continue
            seen_extensions.add(extension)
            extension_tools.extend(
                tools_by_name[tool_name]
                for tool_name, source in self.extension_sources.items()
                if source == extension and tool_name in tools_by_name
            )
        return tuple([*builtins, *extension_tools])

    def _table_row(self, name: str, source: str, description: str) -> str:
        name_width = max((len(tool.name) for tool in self.tools), default=len("Tool"))
        source_width = max(
            (len(self._source_label(tool)) for tool in self.tools),
            default=len("Origin"),
        )
        return (
            f"{name:<{max(name_width, len('Tool'))}}  "
            f"{source:<{max(source_width, len('Origin'))}}  {description}"
        )

    def _source_label(self, tool: AgentTool) -> str:
        extension = self.extension_sources.get(tool.name)
        return extension if extension is not None else "Built in"
