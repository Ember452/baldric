"""Textual TUI frontend for Baldric coding sessions."""

from __future__ import annotations

from baldric.runtime.tui.adapter import TuiEventAdapter
from baldric.runtime.tui.app import BaldricTuiApp, run_tui_app
from baldric.runtime.tui.autocomplete import CompletionOption
from baldric.runtime.tui.config import (
    BALDRIC_DARK_THEME,
    BALDRIC_LIGHT_THEME,
    BUILTIN_TUI_THEME_NAMES,
    HIGH_CONTRAST_THEME,
    TuiConfigError,
    TuiKeybindings,
    TuiRoleStyle,
    TuiSettings,
    TuiTheme,
    TuiThemeName,
    TurnNotificationMode,
    get_tui_theme,
    load_tui_settings,
    save_tui_settings,
    tui_settings_path,
)
from baldric.runtime.tui.state import ChatItem, TuiState
from baldric.runtime.tui.widgets import (
    CompactSessionInfo,
    SessionSidebar,
    StreamingTranscriptMessageWidget,
    TranscriptMessageWidget,
    TranscriptView,
    render_chat_item,
    render_compact_session_info,
    render_session_sidebar,
    transcript_item_selection_text,
)

__all__ = [
    "BUILTIN_TUI_THEME_NAMES",
    "ChatItem",
    "CompletionOption",
    "CompactSessionInfo",
    "BaldricTuiApp",
    "SessionSidebar",
    "BALDRIC_DARK_THEME",
    "BALDRIC_LIGHT_THEME",
    "StreamingTranscriptMessageWidget",
    "TranscriptMessageWidget",
    "TranscriptView",
    "TuiEventAdapter",
    "TuiConfigError",
    "HIGH_CONTRAST_THEME",
    "TuiKeybindings",
    "TuiRoleStyle",
    "TuiSettings",
    "TuiTheme",
    "TuiThemeName",
    "TurnNotificationMode",
    "TuiState",
    "get_tui_theme",
    "load_tui_settings",
    "render_chat_item",
    "render_compact_session_info",
    "render_session_sidebar",
    "run_tui_app",
    "save_tui_settings",
    "transcript_item_selection_text",
    "tui_settings_path",
]
