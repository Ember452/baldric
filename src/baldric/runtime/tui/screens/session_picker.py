"""Minimal Textual app for Baldric coding sessions."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Literal, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Input,
    OptionList,
    Static,
)

from baldric.runtime.tui.config import (
    TuiTheme,
)

if TYPE_CHECKING:
    from baldric.runtime.tui.app import BaldricTuiApp

from baldric.runtime.tui.screens.support import (
    SessionCompletionRecord,
    _filter_session_records,
    _session_picker_label,
)

type BindingEntry = Binding | tuple[str, str] | tuple[str, str, str]


class SessionPickerSearchInput(Input):
    """Search input that keeps session-picker navigation local to the picker."""

    BINDINGS: ClassVar[list[BindingEntry]] = [
        Binding("escape", "cancel", "Cancel", show=False, priority=True),
        Binding("up", "cursor_up", "Up", show=False, priority=True),
        Binding("down", "cursor_down", "Down", show=False, priority=True),
        Binding("f2", "show_archived", "Archived", show=False, priority=True),
    ]

    def _picker(self) -> SessionPickerScreen:
        return cast(SessionPickerScreen, self.screen)

    async def _on_key(self, event: Key) -> None:
        """Route the archive shortcut before Textual's default input handling."""
        if event.key in {"ctrl+enter", "f2"} and isinstance(self.screen, SessionPickerScreen):
            event.stop()
            event.prevent_default()
            if event.key == "f2":
                self.screen.action_show_archived()
            else:
                self.screen.action_archive_cursor()
            return
        await super()._on_key(event)

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
        elif event.key in {"left", "right"} and isinstance(self.screen, SessionPickerScreen):
            event.stop()
            event.prevent_default()
            if event.key == "left":
                self.screen.action_focus_projects()
            else:
                self.screen.action_focus_sessions()
        elif event.key == "ctrl+enter" and isinstance(self.screen, SessionPickerScreen):
            event.stop()
            event.prevent_default()
            self.screen.action_archive_cursor()
        elif event.key == "escape":
            event.stop()
            event.prevent_default()
            self.action_cancel()

    def action_cursor_up(self) -> None:
        """Move the session picker selection up."""
        self._picker().action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move the session picker selection down."""
        self._picker().action_cursor_down()

    def action_cancel(self) -> None:
        """Close the session picker."""
        self._picker().action_cancel()


class SessionPickerScreen(ModalScreen[str | None]):
    """Project-and-session navigator for indexed sessions."""

    BINDINGS: ClassVar[list[BindingEntry]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("left", "focus_projects", "Projects", show=False),
        Binding("right", "focus_sessions", "Sessions", show=False),
        Binding("enter", "select_cursor", "Select", show=False),
        Binding("ctrl+enter", "archive_cursor", "Archive", show=False, priority=True),
        Binding("f2", "show_archived", "Archived", show=False, priority=True),
    ]

    CSS = """
    #session-picker {
        width: 110;
        max-width: 94%;
        height: auto;
        max-height: 85%;
    }

    #session-picker-tabs {
        height: 3;
    }

    #session-picker-tabs Button {
        width: 1fr;
        border: none;
    }

    #session-picker-tabs Button.-active {
        background: $baldric-highlight-background;
        color: $baldric-highlight-text;
        text-style: bold;
    }

    #session-picker-columns {
        height: auto;
        border: tall $baldric-border;
        background: $baldric-transcript-background;
    }

    .session-picker-column {
        height: auto;
        background: $baldric-transcript-background;
    }

    #session-picker-project-column {
        width: 34;
        border-right: tall $baldric-border;
    }

    #session-picker-session-column {
        width: 1fr;
    }

    .session-picker-column-title {
        height: 1;
        padding: 0 1;
        color: $baldric-muted-text;
        text-style: bold;
    }

    .-active-column > .session-picker-column-title {
        color: $baldric-accent;
    }

    #session-picker-project-list,
    #session-picker-list {
        height: auto;
        max-height: 16;
        border: none;
        background: $baldric-transcript-background;
    }

    #session-picker-list {
        padding: 0 1;
    }
    """

    def __init__(
        self,
        records: Sequence[SessionCompletionRecord],
        *,
        archived_records: Sequence[SessionCompletionRecord] = (),
        local_cwd: Path,
        theme: TuiTheme,
        loading_other_projects: bool = False,
        current_project_loaded: bool = True,
    ) -> None:
        super().__init__()
        self.records = tuple(records)
        self.archived_records = tuple(archived_records)
        self.showing_archived = False
        self.local_cwd = local_cwd.resolve()
        self.theme = theme
        self.search_value = ""
        self.active_column: Literal["projects", "sessions"] = "sessions"
        self.hidden_cwds: set[Path] = set()
        self.records_by_project = self._group_records_by_project()
        self.project_cwds = tuple(self.records_by_project)
        self.selected_project_index = 0
        self.visible_records: tuple[SessionCompletionRecord, ...] = ()
        self.loading_other_projects = loading_other_projects
        self.current_project_loaded = current_project_loaded

    def compose(self) -> ComposeResult:
        """Compose project and session columns under one search field."""
        with Vertical(id="session-picker"):
            yield Static("Sessions", id="session-picker-title")
            with Horizontal(id="session-picker-tabs"):
                yield Button("Active", id="session-picker-active-tab")
                yield Button("Archived", id="session-picker-archived-tab")
            yield SessionPickerSearchInput(
                placeholder="Search sessions in selected project",
                id="session-picker-search",
            )
            with Horizontal(id="session-picker-columns"):
                with Vertical(
                    id="session-picker-project-column",
                    classes="session-picker-column",
                ):
                    yield Static("Projects", classes="session-picker-column-title")
                    yield OptionList(id="session-picker-project-list", markup=False, compact=True)
                with Vertical(
                    id="session-picker-session-column",
                    classes="session-picker-column -active-column",
                ):
                    yield Static(
                        "",
                        id="session-picker-session-title",
                        classes="session-picker-column-title",
                    )
                    yield OptionList(id="session-picker-list", markup=False, compact=True)
            yield Static("", id="session-picker-help")

    def on_mount(self) -> None:
        """Start in the current project's recent-session column."""
        self.query_one("#session-picker-search", Input).focus()
        self._refresh_tabs()
        self._refresh_project_list()
        self._refresh_session_list()
        self._update_help()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "session-picker-active-tab":
            self._set_archive_view(False)
        elif event.button.id == "session-picker-archived-tab":
            self._set_archive_view(True)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter sessions in the selected project."""
        if event.input.id != "session-picker-search":
            return
        event.stop()
        self.search_value = event.value
        self._refresh_session_list()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "session-picker-search":
            return
        event.stop()
        self.action_select_cursor()

    def on_key(self, event: Key) -> None:
        """Route navigation while keeping typing focus in the search field."""
        actions = {
            "up": self.action_cursor_up,
            "down": self.action_cursor_down,
            "left": self.action_focus_projects,
            "right": self.action_focus_sessions,
            "enter": self.action_select_cursor,
            "delete": self.action_archive_cursor,
        }
        action = actions.get(event.key)
        if action is not None:
            event.stop()
            action()

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """Show sessions for the highlighted project immediately."""
        if event.option_list.id != "session-picker-project-list":
            return
        index = event.option_index
        if index == self.selected_project_index:
            return
        self.selected_project_index = index
        self._refresh_session_list()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        if event.option_list.id == "session-picker-project-list":
            self.selected_project_index = event.option_index
            self._refresh_session_list()
            if self.showing_archived:
                self.action_unarchive_cursor()
            else:
                self.action_focus_sessions()
            return
        if self.showing_archived:
            self.action_unarchive_cursor()
        else:
            self._select_visible_record()

    def action_cursor_up(self) -> None:
        self._active_list().action_cursor_up()

    def action_cursor_down(self) -> None:
        self._active_list().action_cursor_down()

    def action_focus_projects(self) -> None:
        self._set_active_column("projects")

    def action_focus_sessions(self) -> None:
        self._set_active_column("sessions")

    def action_select_cursor(self) -> None:
        if self.showing_archived:
            self.action_unarchive_cursor()
        elif self.active_column == "projects":
            self.action_focus_sessions()
        else:
            self._select_visible_record()

    def action_show_active(self) -> None:
        self._set_archive_view(False)

    def action_show_archived(self) -> None:
        self._set_archive_view(not self.showing_archived)

    def _set_archive_view(self, show_archived: bool) -> None:
        if self.showing_archived == show_archived:
            return
        selected_cwd = self.project_cwds[self.selected_project_index] if self.project_cwds else None
        self.showing_archived = show_archived
        self.records_by_project = self._group_records_by_project()
        self.project_cwds = tuple(self.records_by_project)
        if selected_cwd in self.project_cwds:
            self.selected_project_index = self.project_cwds.index(selected_cwd)
        else:
            self.selected_project_index = 0
        self._refresh_tabs()
        self._refresh_project_list()
        self._refresh_session_list()

    def action_archive_cursor(self) -> None:
        """Archive or unarchive the highlighted session or project."""
        app = cast("BaldricTuiApp", self.app)
        if not self.project_cwds:
            return
        if self.active_column == "projects":
            cwd = self.project_cwds[self.selected_project_index]
            worker = (
                app._unarchive_session_project(cwd, self)
                if self.showing_archived
                else app._archive_session_project(cwd, self)
            )
            app.run_worker(worker, exclusive=False)
            return
        index = self.query_one("#session-picker-list", OptionList).highlighted
        if index is not None and index < len(self.visible_records):
            record = self.visible_records[index]
            worker = (
                app._unarchive_session_record(record, self)
                if self.showing_archived
                else app._archive_session_record(record, self)
            )
            app.run_worker(worker, exclusive=False)

    def action_unarchive_cursor(self) -> None:
        self.action_archive_cursor()

    async def _remove_records(self, cwd: Path, session_id: str | None = None) -> None:
        """Move newly archived metadata out of the active picker."""
        if self.app.screen is not self:
            return
        resolved_cwd = Path(cwd).resolve()
        if session_id is None:
            moved = tuple(record for record in self.records if Path(record.cwd).resolve() == resolved_cwd)
            self.records = tuple(
                record for record in self.records if Path(record.cwd).resolve() != resolved_cwd
            )
            self.archived_records = (*self.archived_records, *moved)
            self.hidden_cwds.add(resolved_cwd)
        else:
            record = self._record_by_id(session_id)
            self.records = tuple(item for item in self.records if item.id != session_id)
            self.archived_records = (*self.archived_records, record)
            if not any(Path(item.cwd).resolve() == resolved_cwd for item in self.records):
                self.hidden_cwds.add(resolved_cwd)
        self._rebuild_visible_records()

    async def _restore_records(self, cwd: Path, session_id: str | None = None) -> None:
        """Move restored metadata from the archived picker into the active list."""
        if self.app.screen is not self:
            return
        resolved_cwd = Path(cwd).resolve()
        if session_id is None:
            restored = tuple(
                record for record in self.archived_records if Path(record.cwd).resolve() == resolved_cwd
            )
            self.records = (*self.records, *restored)
            self.archived_records = tuple(
                record for record in self.archived_records if Path(record.cwd).resolve() != resolved_cwd
            )
        else:
            self.records = (*self.records, self._record_by_id(session_id))
            self.archived_records = tuple(
                record for record in self.archived_records if record.id != session_id
            )
        self.hidden_cwds.discard(resolved_cwd)
        self._rebuild_visible_records()

    def _record_by_id(self, session_id: str) -> SessionCompletionRecord:
        return next(record for record in (*self.records, *self.archived_records) if record.id == session_id)

    def _rebuild_visible_records(self) -> None:
        self.records_by_project = self._group_records_by_project()
        self.project_cwds = tuple(self.records_by_project)
        if self.project_cwds:
            self.selected_project_index = min(self.selected_project_index, len(self.project_cwds) - 1)
        else:
            self.selected_project_index = 0
        self._refresh_project_list()
        self._refresh_session_list()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def update_records(
        self,
        records: Sequence[SessionCompletionRecord],
        *,
        archived_records: Sequence[SessionCompletionRecord] | None = None,
        loading_other_projects: bool = False,
    ) -> None:
        """Replace records after background loading while preserving navigation."""
        selected_cwd = self.project_cwds[self.selected_project_index] if self.project_cwds else None
        session_list = self.query_one("#session-picker-list", OptionList)
        selected_session_id = None
        if session_list.highlighted is not None and session_list.highlighted < len(self.visible_records):
            selected_session_id = self.visible_records[session_list.highlighted].id

        self.records = tuple(records)
        if archived_records is not None:
            self.archived_records = tuple(archived_records)
        self.records_by_project = self._group_records_by_project()
        self.project_cwds = tuple(self.records_by_project)
        try:
            self.selected_project_index = self.project_cwds.index(selected_cwd)
        except ValueError:
            self.selected_project_index = 0
        self.loading_other_projects = loading_other_projects
        self.current_project_loaded = True
        self._refresh_project_list()
        self._refresh_session_list()

        if selected_session_id is not None:
            for index, record in enumerate(self.visible_records):
                if record.id == selected_session_id:
                    session_list.highlighted = index
                    break

    def finish_loading(self) -> None:
        """Remove the loading state when a background refresh fails."""
        self.loading_other_projects = False
        self._update_help()

    def _active_list(self) -> OptionList:
        selector = (
            "#session-picker-project-list" if self.active_column == "projects" else "#session-picker-list"
        )
        return self.query_one(selector, OptionList)

    def _set_active_column(self, column: Literal["projects", "sessions"]) -> None:
        self.active_column = column
        projects = self.query_one("#session-picker-project-column", Vertical)
        sessions = self.query_one("#session-picker-session-column", Vertical)
        projects.set_class(column == "projects", "-active-column")
        sessions.set_class(column == "sessions", "-active-column")
        self._update_help()

    def _select_visible_record(self) -> None:
        index = self.query_one("#session-picker-list", OptionList).highlighted
        if index is not None and index < len(self.visible_records):
            self.dismiss(self.visible_records[index].id)

    def _group_records_by_project(
        self,
    ) -> dict[Path, tuple[SessionCompletionRecord, ...]]:
        """Group the selected tab's records once for linear picker refreshes."""
        source = self.archived_records if self.showing_archived else self.records
        grouped: dict[Path, list[SessionCompletionRecord]] = {self.local_cwd: []}
        for record in source:
            cwd = Path(record.cwd).resolve()
            if not self.showing_archived and cwd in self.hidden_cwds:
                continue
            grouped.setdefault(cwd, []).append(record)
        return {cwd: tuple(records) for cwd, records in grouped.items()}

    def _refresh_tabs(self) -> None:
        active = self.query_one("#session-picker-active-tab", Button)
        archived = self.query_one("#session-picker-archived-tab", Button)
        active.set_class(not self.showing_archived, "-active")
        archived.set_class(self.showing_archived, "-active")
        self.query_one("#session-picker-search", Input).placeholder = (
            "Search archived sessions in selected project"
            if self.showing_archived
            else "Search sessions in selected project"
        )

    def _refresh_project_list(self) -> None:
        project_list = self.query_one("#session-picker-project-list", OptionList)
        items: list[str] = []
        for cwd in self.project_cwds:
            marker = "● " if cwd == self.local_cwd else "  "
            folder_name = cwd.name or str(cwd)
            items.append(f"{marker}{folder_name}")
        project_list.set_options(items)
        project_list.highlighted = self.selected_project_index if self.project_cwds else None

    def _refresh_session_list(self) -> None:
        label = "Archived sessions" if self.showing_archived else "Recent sessions"
        if not self.project_cwds:
            self.visible_records = ()
            self.query_one("#session-picker-session-title", Static).update(label)
        else:
            selected_cwd = self.project_cwds[self.selected_project_index]
            self.query_one("#session-picker-session-title", Static).update(f"{label} — {selected_cwd}")
            project_records = self.records_by_project[selected_cwd]
            self.visible_records = _filter_session_records(project_records, self.search_value)
        session_list = self.query_one("#session-picker-list", OptionList)
        session_list.set_options(_session_picker_label(record) for record in self.visible_records)
        session_list.highlighted = 0 if self.visible_records else None
        self._update_help()

    def _update_help(self) -> None:
        if self.loading_other_projects and not self.current_project_loaded:
            text = "Loading sessions… - Escape closes"
        elif self.loading_other_projects:
            text = "Loading other projects… - Current sessions are ready - Escape closes"
        elif not self.project_cwds:
            text = "No active sessions or projects - Escape closes"
        elif not self.visible_records and self.active_column == "sessions":
            text = "No matching sessions - Left selects a project - Escape closes"
        elif self.showing_archived and self.active_column == "projects":
            text = "Up/Down selects project - Enter unarchives - F2 shows active - Escape closes"
        elif self.showing_archived:
            text = "Left selects project - Enter unarchives - F2 shows active - Escape closes"
        elif self.active_column == "projects":
            text = (
                "Up/Down selects project - Right opens sessions - "
                "Ctrl+Enter archives - F2 shows archived - Escape closes"
            )
        else:
            text = (
                "Left selects project - Up/Down navigates - Enter resumes - "
                "Ctrl+Enter archives - F2 shows archived - Escape closes"
            )
        self.query_one("#session-picker-help", Static).update(text)
