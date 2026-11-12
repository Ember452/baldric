"""Minimal Textual app for Baldric coding sessions."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from rich.text import Text

from baldric.runtime.frontends.tui.config import (
    TuiTheme,
    TuiThemeName,
)
from baldric.runtime.providers.catalog import (
    ProviderCatalogEntry,
)
from baldric.runtime.session.session import (
    ModelChoice,
    SessionTreeChoice,
)

if TYPE_CHECKING:
    pass


def _login_provider_label(provider: ProviderCatalogEntry) -> str:
    return f"{provider.display_name} — {provider.name}"


def _filter_session_records(
    records: Sequence[SessionCompletionRecord],
    query: str,
) -> tuple[SessionCompletionRecord, ...]:
    normalized = query.strip().casefold()
    if not normalized:
        return tuple(records)
    return tuple(
        record
        for record in records
        if normalized in (record.title or "").casefold() or normalized in record.model.casefold()
    )


def _theme_picker_label(theme_name: TuiThemeName, *, current_theme: TuiThemeName) -> str:
    marker = "✓" if theme_name == current_theme else " "
    return f"{marker} {theme_name}"


def _session_updated_at_label(timestamp: float) -> str:
    """Return a compact relative age label for a session (e.g. ``2h ago``)."""
    delta = (datetime.now() - datetime.fromtimestamp(timestamp)).total_seconds()
    minutes = int(delta // 60)
    if minutes < 1:
        return "now"
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days}d ago"
    return datetime.fromtimestamp(timestamp).strftime("%b %d")


def _tree_choice_index(choices: Sequence[SessionTreeChoice], entry_id: str | None) -> int:
    if entry_id is not None:
        for index, choice in enumerate(choices):
            if choice.entry_id == entry_id:
                return index
    for index, choice in enumerate(choices):
        if choice.active:
            return index
    return 0


def _session_picker_label(record: SessionCompletionRecord) -> str:
    # The project column provides directory context. Keep the model last so it
    # truncates before the relative age and title.
    parts = [_session_updated_at_label(record.updated_at)]
    title = _named_session_title(record.title)
    if title is not None:
        parts.append(title)
    if record.model:
        parts.append(record.model)
    return "  ".join(parts)


def _filter_model_choices(choices: Sequence[ModelChoice], query: str) -> tuple[ModelChoice, ...]:
    normalized = query.strip().lower()
    if not normalized:
        return tuple(choices)
    return tuple(
        choice
        for choice in choices
        if normalized in choice.provider_name.lower() or normalized in choice.model.lower()
    )


def _active_tree_choice_index(choices: Sequence[SessionTreeChoice]) -> int:
    return _tree_choice_index(choices, None)


def _model_picker_label(
    choice: ModelChoice,
    *,
    current_model: str,
    current_provider: str,
    scoped: bool = False,
    unavailable: bool = False,
) -> str:
    marker = "* " if (choice.provider_name == current_provider and choice.model == current_model) else "  "
    suffix = (" [scoped]" if scoped else "") + (" [unavailable]" if unavailable else "")
    return f"{marker}{choice.provider_name}:{choice.model}{suffix}"


def _filter_login_providers(
    providers: Sequence[ProviderCatalogEntry],
    query: str,
) -> tuple[ProviderCatalogEntry, ...]:
    normalized = query.strip().casefold()
    if not normalized:
        return tuple(providers)
    return tuple(
        provider
        for provider in providers
        if normalized in provider.name.casefold() or normalized in provider.display_name.casefold()
    )


def _tree_picker_label(
    choice: SessionTreeChoice,
    *,
    theme: TuiTheme,
    highlighted: bool = False,
    show_label_timestamp: bool = False,
) -> Text:
    marker = "* " if choice.active else "  "
    label = choice.label
    indent_width = len(label) - len(label.lstrip(" "))
    indent = label[:indent_width]
    body = label[indent_width:]
    author, separator, rest = body.partition(":")
    text = Text(f"{marker}{indent}")
    if choice.bookmark_label is not None:
        bookmark_color = theme.highlight_text if highlighted else theme.success
        text.append(f"[{choice.bookmark_label}] ", style=bookmark_color)
        if show_label_timestamp and choice.label_timestamp is not None:
            timestamp = datetime.fromtimestamp(choice.label_timestamp).strftime("%Y-%m-%d %H:%M")
            timestamp_color = theme.highlight_text if highlighted else theme.muted_text
            text.append(f"{timestamp} ", style=timestamp_color)
    if separator:
        author_color = theme.highlight_text if highlighted else theme.accent
        text.append(author, style=author_color)
        text.append(f"{separator}{rest}")
    else:
        text.append(body)
    return text


def _named_session_title(title: str | None) -> str | None:
    if title is None:
        return None
    stripped = title.strip()
    if not stripped or stripped.lower() == "untitled session":
        return None
    return stripped


class SessionCompletionRecord(Protocol):
    """Session metadata needed to render resume picker completions."""

    id: str
    title: str | None
    model: str
    cwd: Path
    updated_at: float


@runtime_checkable
class CursorListScreen(Protocol):
    """A modal list screen the app may drive with arrow keys.

    The app binds Up/Down with priority for prompt-completion navigation, so
    ``action_completion_next/previous`` forward to any active screen that
    exposes cursor actions. Implementing these actions is the whole contract:
    a new list modal gets arrow-key support without any registration.
    """

    def action_cursor_up(self) -> None: ...

    def action_cursor_down(self) -> None: ...


@runtime_checkable
class SelectableListScreen(Protocol):
    """A modal list screen whose highlighted entry Enter may accept.

    The app binds Enter with priority for prompt-completion acceptance, so
    ``action_accept_completion`` forwards to any active screen that exposes a
    select action. Screens needing different Enter behavior (for example a
    mode toggle) are special-cased before this check in the app.
    """

    def action_select_cursor(self) -> None: ...
