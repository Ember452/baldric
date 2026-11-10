"""Minimal Textual app for Baldric coding sessions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Literal, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import (
    Input,
    Label,
    ListItem,
    ListView,
    Static,
)

from baldric.runtime.context.skills.skills import Skill
from baldric.runtime.tui.config import (
    TuiTheme,
)

if TYPE_CHECKING:
    pass

from baldric.runtime.tui.screens.command_output import CommandOutputScreen

type BindingEntry = Binding | tuple[str, str] | tuple[str, str, str]


class SkillPickerSearchInput(Input):
    """Search input that keeps skill-picker navigation local."""

    BINDINGS: ClassVar[list[BindingEntry]] = [
        Binding("escape", "cancel", "Cancel", show=False, priority=True),
        Binding("up", "cursor_up", "Up", show=False, priority=True),
        Binding("down", "cursor_down", "Down", show=False, priority=True),
    ]

    def _picker(self) -> SkillPickerScreen:
        return cast(SkillPickerScreen, self.screen)

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
        elif event.key == "escape":
            event.stop()
            event.prevent_default()
            self.action_cancel()
        elif event.key == "f1":
            event.stop()
            event.prevent_default()
            self.action_show_description()
        elif event.key == "ctrl+enter":
            event.stop()
            event.prevent_default()
            self.action_show_in_transcript()

    def action_cursor_up(self) -> None:
        self._picker().action_cursor_up()

    def action_cursor_down(self) -> None:
        self._picker().action_cursor_down()

    def action_cancel(self) -> None:
        self._picker().action_cancel()

    def action_show_description(self) -> None:
        self._picker().action_show_description()

    def action_show_in_transcript(self) -> None:
        self._picker().action_show_in_transcript()


@dataclass(frozen=True, slots=True)
class SkillPickerResult:
    """A skill selection and the requested inspection action."""

    skill: Skill
    action: Literal["insert", "transcript"]


class SkillPickerScreen(ModalScreen[SkillPickerResult | None]):
    """Searchable modal containing every loaded skill."""

    BINDINGS: ClassVar[list[BindingEntry]] = [
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("up", "cursor_up", "Up", show=False, priority=True),
        Binding("down", "cursor_down", "Down", show=False, priority=True),
        Binding("enter", "select_cursor", "Insert", show=False, priority=True),
        Binding("f1", "show_description", "Description", show=False, priority=True),
        Binding("ctrl+enter", "show_in_transcript", "Transcript", show=False, priority=True),
    ]

    def __init__(self, skills: Sequence[Skill], *, theme: TuiTheme) -> None:
        super().__init__()
        self.skills = tuple(sorted(skills, key=lambda skill: skill.name.casefold()))
        self.visible_skills = self.skills
        self.theme = theme

    def compose(self) -> ComposeResult:
        with Vertical(id="skill-picker"):
            yield Static("Skills", id="skill-picker-title")
            yield SkillPickerSearchInput(placeholder="Search skills", id="skill-picker-search")
            yield ListView(id="skill-picker-list")
            yield Static("", id="skill-picker-help")

    def on_mount(self) -> None:
        self.query_one("#skill-picker-search", Input).focus()
        self._refresh_skill_list("")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "skill-picker-search":
            event.stop()
            self._refresh_skill_list(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "skill-picker-search":
            event.stop()
            self._select_visible_skill()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        event.stop()
        self._select_visible_skill()

    def action_cursor_up(self) -> None:
        skill_list = self.query_one("#skill-picker-list", ListView)
        if skill_list.index is not None:
            skill_list.index = max(0, skill_list.index - 1)

    def action_cursor_down(self) -> None:
        skill_list = self.query_one("#skill-picker-list", ListView)
        if skill_list.index is not None:
            skill_list.index = min(len(self.visible_skills) - 1, skill_list.index + 1)

    def action_select_cursor(self) -> None:
        skill = self._selected_skill()
        if skill is not None:
            self.dismiss(SkillPickerResult(skill, "insert"))

    def action_show_description(self) -> None:
        skill = self._selected_skill()
        if skill is not None:
            self.app.push_screen(
                CommandOutputScreen(
                    f"Skill description: {skill.name}",
                    skill.description or "No description",
                    theme=self.theme,
                )
            )

    def action_show_in_transcript(self) -> None:
        skill = self._selected_skill()
        if skill is not None:
            self.dismiss(SkillPickerResult(skill, "transcript"))

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _selected_skill(self) -> Skill | None:
        index = self.query_one("#skill-picker-list", ListView).index
        if index is None or not self.visible_skills:
            return None
        return self.visible_skills[index]

    def _select_visible_skill(self) -> None:
        self.action_select_cursor()

    def _refresh_skill_list(self, search: str) -> None:
        query = search.casefold().strip()
        self.visible_skills = tuple(
            skill
            for skill in self.skills
            if not query or query in skill.name.casefold() or query in (skill.description or "").casefold()
        )
        skill_list = self.query_one("#skill-picker-list", ListView)
        skill_list.clear()
        skill_list.extend(
            ListItem(
                Horizontal(
                    Label(skill.name, classes="skill-picker-name", markup=False),
                    Label(
                        skill.description or "No description",
                        classes="skill-picker-description",
                        markup=False,
                    ),
                    classes="skill-picker-row",
                )
            )
            for skill in self.visible_skills
        )
        skill_list.index = 0 if self.visible_skills else None
        if not self.skills:
            help_text = "No skills loaded - Escape closes"
        elif not self.visible_skills:
            help_text = "No matching skills - Escape closes"
        else:
            help_text = "Enter inserts - F1 describes - Ctrl+Enter shows full skill"
        self.query_one("#skill-picker-help", Static).update(help_text)
