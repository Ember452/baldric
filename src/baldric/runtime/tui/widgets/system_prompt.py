"""Structured widgets for a sourced system prompt (moved from widgets/core.py)."""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.color import Color as TextualColor
from textual.containers import Vertical
from textual.widgets import Static

from baldric.runtime.context.system_prompt import SystemPromptSource
from baldric.runtime.rendering.themes import TuiTheme
from baldric.runtime.tui.widgets.markdown import (
    ThemedMarkdownWidget,
    _system_prompt_markdown,
)


class SystemPromptSectionWidget(Vertical):
    """One prompt source with a matching accent and faint background."""

    DEFAULT_CSS = """
    SystemPromptSectionWidget {
        width: 1fr;
        height: auto;
        margin: 0 0 1 0;
        padding: 1 1 0 1;
    }

    SystemPromptSectionWidget > .system-prompt-source-name,
    SystemPromptSectionWidget > .system-prompt-source-origin {
        width: 1fr;
        height: auto;
    }

    SystemPromptSectionWidget > .system-prompt-source-body {
        width: 1fr;
        height: auto;
        margin: 1 0 0 0;
        padding: 0;
    }

    SystemPromptSectionWidget > .system-prompt-source-body > MarkdownParagraph {
        margin: 0 0 1 0;
    }
    """

    def __init__(
        self,
        source: SystemPromptSource,
        *,
        index: int,
        theme: TuiTheme,
    ) -> None:
        self.source = source
        self.index = index
        self._theme = theme
        self.source_color = _system_prompt_source_color(source, theme=theme)
        super().__init__(classes=f"system-prompt-source system-prompt-source-{source.kind}")
        background = TextualColor.parse(theme.transcript_background).blend(
            TextualColor.parse(self.source_color),
            0.08,
        )
        self.styles.background = background
        self.styles.border_left = ("tall", self.source_color)

    def compose(self) -> Any:
        name = Text()
        name.append(f"{self.index:02d} · ", style=self._theme.muted_text)
        name.append(self.source.label, style=f"bold {self.source_color}")
        origin = Text("Source: ", style=self._theme.muted_text)
        origin.append(self.source.source, style=self.source_color)
        yield Static(name, classes="system-prompt-source-name")
        yield Static(origin, classes="system-prompt-source-origin")
        yield ThemedMarkdownWidget(
            _system_prompt_markdown(self.source.content.lstrip("\n")),
            theme=self._theme,
            classes="system-prompt-source-body",
        )


class SystemPromptSourcesWidget(Vertical):
    """Structured rendering for a sourced system prompt."""

    DEFAULT_CSS = """
    SystemPromptSourcesWidget {
        width: 1fr;
        height: auto;
    }

    SystemPromptSourcesWidget > .system-prompt-title {
        width: 1fr;
        height: auto;
        margin: 0 0 1 1;
    }
    """

    def __init__(self, sources: tuple[SystemPromptSource, ...], *, theme: TuiTheme) -> None:
        self.sources = sources
        self._theme = theme
        super().__init__()

    def compose(self) -> Any:
        yield Static(
            Text("/system", style=f"bold {self._theme.accent}"),
            classes="system-prompt-title",
        )
        for index, source in enumerate(self.sources, start=1):
            yield SystemPromptSectionWidget(source, index=index, theme=self._theme)


def _system_prompt_source_color(source: SystemPromptSource, *, theme: TuiTheme) -> str:
    """Choose a stable theme color for one prompt-source kind."""
    return {
        "default": theme.accent,
        "system": theme.role_styles["assistant"].border,
        "append": theme.role_styles["status"].border,
        "extension": theme.role_styles["tool"].border,
        "context": theme.role_styles["branch_summary"].border,
        "skill": theme.role_styles["skill"].border,
        "runtime": theme.muted_text,
    }[source.kind]
