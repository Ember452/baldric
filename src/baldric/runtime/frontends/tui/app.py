"""Minimal Textual app for Baldric coding sessions."""

from __future__ import annotations

import asyncio
import gc
import os
import signal
import sys
import threading
import time
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import suppress
from dataclasses import replace
from inspect import isawaitable
from io import StringIO
from pathlib import Path
from typing import Any, ClassVar, Literal, cast

from rich.console import Console, Group
from rich.text import Text
from textual import constants as textual_constants
from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingsMap
from textual.containers import Container, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.events import Resize
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import (
    Static,
    TextArea,
)
from textual.worker import Worker

from baldric.agent.events import (
    AgentEndEvent,
    AgentStartEvent,
    MessageEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    ToolExecutionUpdateEvent,
)
from baldric.protocol.messages import (
    AgentMessage,
    AssistantMessage,
    CustomMessage,
    ThinkingContent,
    ToolCall,
    UserMessage,
)
from baldric.protocol.provider import CancellationToken, RequestHooks
from baldric.protocol.provider_events import (
    AssistantErrorEvent,
    AssistantMessageEvent,
    TextDeltaEvent,
    ThinkingDeltaEvent,
    ThinkingEndEvent,
)
from baldric.protocol.tools import AgentTool
from baldric.protocol.types import JSONValue
from baldric.runtime.commands.base import (
    CommandKind,
    CommandOutcome,
    MessageDisplay,
    PickerKind,
)
from baldric.runtime.commands.registry import (
    LOGIN_PROVIDER_ALIASES,
    CommandRegistry,
    create_default_command_registry,
    format_reload_summary,
)
from baldric.runtime.config.shell_config import load_shell_settings
from baldric.runtime.context.prompts import PromptTemplate
from baldric.runtime.context.resources import BaldricResourcePaths, ResourceDiagnostic
from baldric.runtime.context.system_prompt import SystemPromptInspection
from baldric.runtime.context.thinking import ThinkingLevel
from baldric.runtime.events import (
    AgentSettledEvent,
    AutoRetryEndEvent,
    AutoRetryStartEvent,
    CodingSessionEvent,
    CompactionEndEvent,
    CompactionStartEvent,
    ModelSelectEvent,
    QueueUpdateEvent,
    SessionAgentEndEvent,
    SessionInfoChangedEvent,
    ThinkingLevelChangedEvent,
)
from baldric.runtime.frontends.tui.adapter import EventDispatcher, TuiEventAdapter
from baldric.runtime.frontends.tui.autocomplete import (
    CompletionItem,
    CompletionKind,
    CompletionState,
    build_completion_state,
)
from baldric.runtime.frontends.tui.backends import (
    LocalBackendPickerScreen,
    LocalBackendScreen,
)
from baldric.runtime.frontends.tui.backends import (
    LocalChoiceConfirmScreen as LocalChoiceConfirmScreen,
)
from baldric.runtime.frontends.tui.backends import (
    LocalConfirmScreen as LocalConfirmScreen,
)
from baldric.runtime.frontends.tui.backends import (
    LocalSearchResultsScreen as LocalSearchResultsScreen,
)
from baldric.runtime.frontends.tui.config import (
    BALDRIC_DARK_THEME,
    TuiKeybindings,
    TuiSettings,
    TuiTheme,
    TuiThemeName,
    load_tui_settings,
    save_tui_settings,
)
from baldric.runtime.frontends.tui.editor import EditorError, run_external_editor
from baldric.runtime.frontends.tui.extension_components import (
    ExtensionComponentsMixin,
    _MainViewHandle,
    _SidebarContribution,
)
from baldric.runtime.frontends.tui.extension_components import (
    _TuiExtensionUiBridge as _TuiExtensionUiBridge,
)
from baldric.runtime.frontends.tui.login_providers import (
    NO_STORED_CREDENTIALS_MESSAGE,
    credential_store_has_entry,
)
from baldric.runtime.frontends.tui.pickers import PickerMixin
from baldric.runtime.frontends.tui.screens.approval import ApprovalScreen
from baldric.runtime.frontends.tui.screens.command_output import CommandOutputScreen
from baldric.runtime.frontends.tui.screens.extension import (
    ExtensionConfirmScreen as ExtensionConfirmScreen,
)
from baldric.runtime.frontends.tui.screens.extension import (
    ExtensionInputScreen as ExtensionInputScreen,
)
from baldric.runtime.frontends.tui.screens.extension import (
    ExtensionSelectScreen as ExtensionSelectScreen,
)
from baldric.runtime.frontends.tui.screens.extensions import ExtensionsScreen
from baldric.runtime.frontends.tui.screens.login import (
    CustomProviderLoginResult,
    CustomProviderLoginScreen,
    _LoginFlowAction,
)
from baldric.runtime.frontends.tui.screens.login import (
    LoginMethodPickerScreen as LoginMethodPickerScreen,
)
from baldric.runtime.frontends.tui.screens.login import (
    LoginProviderPickerScreen as LoginProviderPickerScreen,
)
from baldric.runtime.frontends.tui.screens.login import (
    LoginScreen as LoginScreen,
)
from baldric.runtime.frontends.tui.screens.login import (
    OAuthLoginScreen as OAuthLoginScreen,
)
from baldric.runtime.frontends.tui.screens.model_picker import ModelPickerScreen
from baldric.runtime.frontends.tui.screens.prompt_templates import (
    PromptTemplateEditorScreen,
    PromptTemplatePickerResult,
    PromptTemplatePickerScreen,
)
from baldric.runtime.frontends.tui.screens.session_picker import SessionPickerScreen
from baldric.runtime.frontends.tui.screens.sidebar import (
    SidebarFileEditor as SidebarFileEditor,
)
from baldric.runtime.frontends.tui.screens.sidebar import (
    _atomic_write_sidebar_file as _atomic_write_sidebar_file,
)
from baldric.runtime.frontends.tui.screens.sidebar import (
    _read_sidebar_file as _read_sidebar_file,
)
from baldric.runtime.frontends.tui.screens.sidebar import (
    _SidebarFileSnapshot as _SidebarFileSnapshot,
)
from baldric.runtime.frontends.tui.screens.sidebar import (
    _write_staged_utf8 as _write_staged_utf8,
)
from baldric.runtime.frontends.tui.screens.skill_picker import (
    SkillPickerScreen as SkillPickerScreen,
)
from baldric.runtime.frontends.tui.screens.support import (
    CursorListScreen as CursorListScreen,
)
from baldric.runtime.frontends.tui.screens.support import (
    SelectableListScreen as SelectableListScreen,
)
from baldric.runtime.frontends.tui.screens.support import (
    SessionCompletionRecord as SessionCompletionRecord,
)
from baldric.runtime.frontends.tui.screens.support import (
    _active_tree_choice_index as _active_tree_choice_index,
)
from baldric.runtime.frontends.tui.screens.support import (
    _filter_login_providers as _filter_login_providers,
)
from baldric.runtime.frontends.tui.screens.support import (
    _filter_model_choices as _filter_model_choices,
)
from baldric.runtime.frontends.tui.screens.support import (
    _filter_session_records as _filter_session_records,
)
from baldric.runtime.frontends.tui.screens.support import (
    _login_provider_label as _login_provider_label,
)
from baldric.runtime.frontends.tui.screens.support import (
    _model_picker_label as _model_picker_label,
)
from baldric.runtime.frontends.tui.screens.support import (
    _named_session_title as _named_session_title,
)
from baldric.runtime.frontends.tui.screens.support import (
    _session_picker_label as _session_picker_label,
)
from baldric.runtime.frontends.tui.screens.support import (
    _session_updated_at_label as _session_updated_at_label,
)
from baldric.runtime.frontends.tui.screens.support import (
    _theme_picker_label as _theme_picker_label,
)
from baldric.runtime.frontends.tui.screens.support import (
    _tree_choice_index as _tree_choice_index,
)
from baldric.runtime.frontends.tui.screens.support import (
    _tree_picker_label as _tree_picker_label,
)
from baldric.runtime.frontends.tui.screens.theme import (
    ThemePickerScreen as ThemePickerScreen,
)
from baldric.runtime.frontends.tui.screens.tools_reference import ToolsReferenceScreen
from baldric.runtime.frontends.tui.screens.tree_picker import (
    TreePickerScreen as TreePickerScreen,
)
from baldric.runtime.frontends.tui.session_records import (
    session_options,
    session_records,
    short_path,
)
from baldric.runtime.frontends.tui.state import (
    TuiState,
    assistant_visible_blocks,
    format_terminal_command_result_block,
)
from baldric.runtime.frontends.tui.terminal_notification import TerminalNotificationController
from baldric.runtime.frontends.tui.terminal_title import TerminalTitleController
from baldric.runtime.frontends.tui.text_utils import text_end_location
from baldric.runtime.frontends.tui.trust import ProjectTrustScreen, prompt_project_trust
from baldric.runtime.frontends.tui.widgets import (
    CompactSessionInfo,
    SessionSidebar,
    SidebarFileItem,
    TranscriptView,
    render_completion_suggestions,
)
from baldric.runtime.frontends.tui.widgets.prompt_input import (
    PASTE_DISPLAY_THRESHOLD as PASTE_DISPLAY_THRESHOLD,
)
from baldric.runtime.frontends.tui.widgets.prompt_input import (
    CompletionActionTarget as CompletionActionTarget,
)
from baldric.runtime.frontends.tui.widgets.prompt_input import (
    PromptInput as PromptInput,
)
from baldric.runtime.frontends.tui.widgets.prompt_input import (
    _hidden_prompt_bindings as _hidden_prompt_bindings,
)
from baldric.runtime.frontends.tui.widgets.prompt_input import (
    _is_thinking_cycle_key as _is_thinking_cycle_key,
)
from baldric.runtime.frontends.tui.widgets.prompt_input import (
    _key_hint as _key_hint,
)
from baldric.runtime.frontends.tui.widgets.prompt_input import (
    _prompt_bindings as _prompt_bindings,
)
from baldric.runtime.frontends.tui.widgets.prompt_input import (
    _terminal_command_prefix_span as _terminal_command_prefix_span,
)
from baldric.runtime.observability.watchdog import LoopWatchdog
from baldric.runtime.platform.api import (
    KeyInterceptor,
)
from baldric.runtime.providers.auth.credentials import FileCredentialStore, OAuthCredential

# Re-exported on purpose: ``tui/screens/login.py`` resolves the OAuth provider via
# ``_app_module().get_oauth_provider(name)`` so tests (and the app) can patch it
# here. Removing this import breaks the OAuth login flow at runtime.
from baldric.runtime.providers.auth.registry import get_oauth_provider as get_oauth_provider
from baldric.runtime.providers.catalog import (
    ProviderCatalogEntry,
    builtin_provider_entry,
)
from baldric.runtime.providers.config import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDER_NAME,
    OpenAICompatibleProviderConfig,
    ProviderConfig,
    ProviderConfigError,
    ProviderSelection,
    load_provider_settings,
    provider_config_from_catalog_entry,
    provider_has_usable_credentials,
    resolve_provider_selection,
    resolve_startup_thinking_level,
    save_provider_settings,
    upsert_openai_compatible_provider,
    upsert_saved_provider,
)
from baldric.runtime.providers.loader import save_user_catalog_entries
from baldric.runtime.providers.runtime import (
    ClosableModelProvider,
    create_model_provider,
)
from baldric.runtime.rendering import activity
from baldric.runtime.rendering.themes import (
    available_tui_theme_names,
    load_custom_tui_themes,
    set_custom_tui_themes,
    textual_theme_for_tui_theme,
    theme_css_variables,
)
from baldric.runtime.session.manager import CodingSessionRecord, SessionManager
from baldric.runtime.session.prepare import prepare_coding_session
from baldric.runtime.session.session import (
    TREE_RUNNING_MESSAGE,
    CodingSession,
    CodingSessionConfig,
    ModelChoice,
    SessionTreeBranchResult,
    jsonl_session_storage,
    parse_terminal_command,
)
from baldric.runtime.trust.approvals import (
    MUTATING_TOOL_NAMES,
    ApprovalPolicy,
    ApprovalRequest,
    approval_target,
    build_approval_preview,
)
from baldric.runtime.trust.policy import ProjectTrustRequest, TrustChoice, TrustOverride

_textual_theme_for_baldric_theme = textual_theme_for_tui_theme
_theme_css_variables = theme_css_variables

# Re-exported for backwards compatibility: these were importable from this module
# before the picker/extension extraction. Moving the code changed their home, not
# their callers, so the old private names stay importable here.
_session_records = session_records
_short_path = short_path

# Activity spinner chrome moved to rendering/activity.py; the old module-level
# names stay importable for callers and tests.
ACTIVITY_TICK_SECONDS = activity.ACTIVITY_TICK_SECONDS
ACTIVITY_COLOR_FADE_STEPS = activity.ACTIVITY_COLOR_FADE_STEPS
ACTIVITY_SPINNER_FRAMES = activity.ACTIVITY_SPINNER_FRAMES
ACTIVITY_SPINNER_MAX_FADE = activity.ACTIVITY_SPINNER_MAX_FADE
_render_activity_indicator = activity.render_activity_indicator

type BindingEntry = Binding | tuple[str, str] | tuple[str, str, str]
COMPLETION_MAX_VISIBLE_LINES = 16
COMPLETION_INITIAL_TERMINAL_FRACTION = 3
COMPLETION_MIN_TRANSCRIPT_LINES = 4
COMPLETION_WIDGET_CHROME_LINES = 3

#: Session event type -> DOM handler method on ``BaldricTuiApp``. This table is
#: the only place that decides which event updates the mounted transcript; the
#: dispatcher's fallback refreshes chrome for anything absent (see
#: ``TuiEventAdapter.INTENTIONAL_NOOP`` for the events that use it by design).
DOM_EVENT_HANDLERS: dict[type[object], str] = {
    AgentStartEvent: "_dom_agent_start",
    AgentEndEvent: "_dom_agent_end",
    MessageStartEvent: "_dom_message_start",
    MessageUpdateEvent: "_dom_message_update",
    MessageEndEvent: "_dom_message_end",
    ToolExecutionStartEvent: "_dom_tool_execution_start",
    ToolExecutionUpdateEvent: "_dom_tool_execution_update",
    ToolExecutionEndEvent: "_dom_tool_execution_end",
    SessionAgentEndEvent: "_dom_refresh_chrome",
    AgentSettledEvent: "_dom_refresh_chrome",
    QueueUpdateEvent: "_dom_refresh_chrome",
    CompactionStartEvent: "_dom_compaction_start",
    CompactionEndEvent: "_dom_compaction_end",
    AutoRetryStartEvent: "_dom_auto_retry_start",
    AutoRetryEndEvent: "_dom_auto_retry_end",
    SessionInfoChangedEvent: "_dom_session_info_changed",
    ThinkingLevelChangedEvent: "_dom_thinking_level_changed",
    ModelSelectEvent: "_dom_model_selected",
}


def _configure_herdr_textual_mouse() -> None:
    """Keep Textual on cell mouse coordinates inside affected Herdr versions."""
    if os.environ.get("HERDR_ENV") != "1" or "TEXTUAL_SMOOTH_SCROLL" in os.environ:
        return
    os.environ["TEXTUAL_SMOOTH_SCROLL"] = "0"
    # Textual reads this environment variable while importing constants, before
    # Baldric reaches the TUI runner. Update the loaded value for this process too.
    textual_constants.SMOOTH_SCROLL = False  # type: ignore[misc]


class LoginRequiredProvider:
    """Placeholder provider used so the TUI can open before login."""

    def __init__(self, message: str) -> None:
        self.message = message

    async def aclose(self) -> None:
        """Close provider resources."""

    def stream_response(
        self,
        *,
        model: str,
        system: str,
        messages: list[AgentMessage],
        tools: list[AgentTool],
        signal: CancellationToken | None = None,
        session_id: str | None = None,
        hooks: RequestHooks | None = None,
    ) -> AsyncIterator[AssistantMessageEvent]:
        """Surface a login-needed provider error."""
        del system, messages, tools, signal, session_id, hooks

        async def iterator() -> AsyncIterator[AssistantMessageEvent]:
            error = AssistantMessage(
                model=model,
                stop_reason="error",
                error_message=self.message,
            )
            yield AssistantErrorEvent(reason="error", error=error)

        return iterator()


#: Keys an extension key interceptor is never consulted for. These flow
#: straight to normal dispatch so a buggy interceptor (one that returns True
#: too broadly) cannot swallow the session's hard interrupt/exit reflexes and
#: brick the TUI. Deliberately minimal — only the always-available escape
#: hatches: ``ctrl+d`` (the ``quit`` action, exits the app) and ``ctrl+c``
#: (Baldric binds it to ``clear_prompt``, but it is the terminal-standard
#: SIGINT/interrupt reflex users hit to bail). NOT reserved: escape/enter/
#: arrows/tab/left/right — those are load-bearing for the baldric-subagents
#: extension and must stay interceptable. This is Baldric's counterpart to Pi's
#: ``RESERVED_KEYBINDINGS_FOR_EXTENSION_CONFLICTS`` (runner.ts:69), applied
#: here to the pre-dispatch interceptor rather than a registerShortcut API.
RESERVED_EXTENSION_INTERCEPTOR_KEYS: frozenset[str] = frozenset({"ctrl+c", "ctrl+d"})


def _collect_garbage_while_idle() -> None:
    """Run a full collection and freeze the survivors.

    Keeps automatic gen-2 passes (100-400ms in a long session) out of streaming.
    Unfreezing first means cycles among older objects are still collected.
    """
    gc.unfreeze()
    gc.collect()
    gc.freeze()


class BaldricTuiApp(PickerMixin, ExtensionComponentsMixin, App[None]):
    """Interactive Textual frontend for a ``CodingSession``."""

    # Textual registers @on(...) handlers from the concrete class __dict__ only,
    # so this decorated handler must live on the app itself, not in a mixin.

    @on(SidebarFileItem.OpenRequested)
    def on_sidebar_file_open_requested(self: Any, event: SidebarFileItem.OpenRequested) -> None:
        """Open a sidebar resource file in the main-area editor."""
        event.stop()
        item = event.item
        current = self._extension_main_view
        if current is not None and isinstance(current.widget, SidebarFileEditor) and current.widget.is_dirty:
            message = "Save or close the current file before opening another."
            self._notify(message, severity="warning")
            current.widget.query_one("#sidebar-file-editor-status", Static).update(message)
            current.widget.query_one("#sidebar-file-editor-input", TextArea).focus()
            return
        try:
            source, snapshot = _read_sidebar_file(item.path)
        except (OSError, UnicodeDecodeError) as exc:
            self._notify(f"Could not read {item.path}: {exc}", severity="error")
            return
        self._open_extension_main_view(
            lambda handle, theme: SidebarFileEditor(
                handle=handle,
                path=item.path,
                label=item.file_label,
                kind=item.kind,
                source=source,
                snapshot=snapshot,
            )
        )

    TITLE = "Baldric"
    CSS = """
    Screen {
        layout: vertical;
        background: $baldric-screen-background;
        color: $baldric-screen-text;
    }

    Toast {
        background: $baldric-chrome-background;
        color: $baldric-chrome-text;
    }

    Toast .toast--title {
        color: $baldric-accent;
    }

    #workspace {
        height: 1fr;
    }

    #sidebar {
        width: 40;
        min-width: 36;
        height: 1fr;
        padding: 1 1 1 2;
        background: $baldric-prompt-background;
        border: none;
    }

    #sidebar-scroll {
        height: 1fr;
        scrollbar-size-vertical: 1;
    }

    #sidebar-content {
        height: auto;
    }

    #sidebar .sidebar-separator {
        height: auto;
    }

    #sidebar .sidebar-resource-section {
        width: 1fr;
        height: auto;
        padding: 0;
        background: transparent;
        border: none;
    }

    #sidebar .sidebar-resource-section:focus-within {
        background-tint: transparent;
    }

    #sidebar .sidebar-resource-section CollapsibleTitle {
        width: 1fr;
        padding: 0 0 0 1;
        color: $baldric-prompt-text;
        text-style: none;
        background: transparent;
    }

    #sidebar .sidebar-resource-section CollapsibleTitle:hover,
    #sidebar .sidebar-resource-section CollapsibleTitle:focus {
        color: $baldric-prompt-text;
        text-style: none;
        background: transparent;
    }

    #sidebar .sidebar-resource-section Contents {
        padding: 1 0 0 1;
    }

    #sidebar .sidebar-section-title {
        height: 1;
        padding: 0 0 0 1;
        color: $baldric-prompt-text;
        text-style: bold;
    }

    #sidebar .sidebar-file-list {
        width: 1fr;
        height: auto;
    }

    #sidebar .sidebar-resource-origin,
    #sidebar .sidebar-file-empty,
    #sidebar .sidebar-file-overflow {
        width: 1fr;
        height: auto;
        color: $baldric-muted-text;
    }

    #sidebar .sidebar-file-item {
        width: 1fr;
        height: auto;
        color: $baldric-muted-text;
        background: transparent;
    }

    #sidebar .sidebar-file-item:hover,
    #sidebar .sidebar-file-item:focus {
        color: $baldric-highlight-text;
        background: $baldric-highlight-background;
        text-style: underline;
    }

    #sidebar-extension-sections,
    #sidebar .extension-sidebar-section,
    #sidebar .extension-sidebar-body {
        width: 1fr;
        height: auto;
    }

    #sidebar .extension-sidebar-title {
        height: auto;
        padding: 0 0 0 1;
    }

    #sidebar .extension-sidebar-body {
        padding: 1 0 0 1;
    }

    #sidebar-brand {
        height: auto;
        color: $baldric-prompt-text;
    }

    BaldricTuiApp.-hide-sidebar #sidebar {
        display: none;
    }

    BaldricTuiApp.-hide-sidebar #main-pane {
        padding-left: 1;
    }

    BaldricTuiApp.-sidebar-right #sidebar {
        dock: right;
    }

    #main-pane {
        width: 1fr;
        padding: 1 1 0 1;
    }

    #transcript {
        height: 1fr;
        border: none;
        background: $baldric-transcript-background;
        padding: 0 0 0 2;
        overflow-x: auto;
        scrollbar-size-vertical: 1;
        scrollbar-size-horizontal: 1;
        scrollbar-color: $baldric-scrollbar;
        scrollbar-color-hover: $baldric-scrollbar-hover;
    }

    /* Component seam: generic extension mount points. */
    #main-slot {
        display: none;
        height: 1fr;
        border: none;
        background: $baldric-transcript-background;
        padding: 0 0 0 2;
        overflow-x: auto;
        scrollbar-size-vertical: 0;
        scrollbar-size-horizontal: 1;
    }

    #sidebar-file-editor {
        width: 1fr;
        height: 1fr;
        padding: 0 1;
    }

    #sidebar-file-editor-title {
        height: 1;
        color: $baldric-accent;
        text-style: bold;
    }

    #sidebar-file-editor-path,
    #sidebar-file-editor-help,
    #sidebar-file-editor-status {
        height: 1;
        color: $baldric-muted-text;
    }

    #sidebar-file-editor-path {
        margin-bottom: 1;
    }

    #sidebar-file-editor-input {
        height: 1fr;
        background: $baldric-prompt-background;
        color: $baldric-prompt-text;
        border: tall $baldric-prompt-border;
    }

    #above-prompt-slot {
        height: auto;
        max-height: 8;
        margin: 0 1 0 1;
        padding: 0;
        background: $baldric-screen-background;
    }

    #below-prompt-slot {
        height: auto;
        max-height: 8;
        margin: 0 1 0 1;
        padding: 0;
        background: $baldric-screen-background;
    }

    #queued-messages {
        height: auto;
        max-height: 8;
        margin: 0 1 1 1;
        padding: 0 1;
        background: $baldric-screen-background;
        color: $baldric-muted-text;
    }

    #prompt-row {
        height: auto;
        margin: 0 1 0 1;
    }

    #prompt-prefix {
        width: 2;
        height: 3;
        padding: 0 0 0 0;
        margin: 0;
        content-align: center middle;
        color: $baldric-accent;
        text-style: bold;
    }

    #prompt {
        width: 1fr;
        height: auto;
        background: $baldric-screen-background;
        color: $baldric-prompt-text;
        border: none;
        border-top: solid $baldric-prompt-border;
        border-bottom: solid $baldric-prompt-border;
        margin: 0;
        padding: 0 1;
        max-height: 8;
    }

    #prompt.-shell-mode {
        border-top: solid $baldric-tool-running;
        border-bottom: solid $baldric-tool-running;
    }

    #compact-session-info {
        height: auto;
        max-height: 3;
        margin: 0 1 0 1;
        padding: 0 1;
        color: $baldric-muted-text;
    }

    #autocomplete {
        height: auto;
        max-height: 18;
        margin: 0 1 1 1;
        padding: 0 1;
        background: $baldric-autocomplete-background;
        color: $baldric-screen-text;
        border: tall $baldric-border;
        overflow-y: auto;
    }

    SessionPickerScreen,
    PromptTemplatePickerScreen,
    PromptTemplateEditorScreen,
    SkillPickerScreen,
    TreePickerScreen,
    ToolsReferenceScreen,
    CommandOutputScreen,
    ExtensionsScreen {
        align: center middle;
    }

    #session-picker,
    #prompt-template-picker,
    #prompt-template-editor,
    #skill-picker,
    #tree-picker,
    #tools-reference,
    #extensions-screen {
        width: 76;
        max-width: 90%;
        height: auto;
        max-height: 70%;
        padding: 1 2;
        background: $baldric-chrome-background;
        border: tall $baldric-border;
    }

    #session-picker-title,
    #prompt-template-picker-title,
    #prompt-template-editor-title,
    #skill-picker-title,
    #tree-picker-title,
    #tools-reference-title,
    #extensions-title {
        height: 1;
        color: $baldric-chrome-text;
        text-style: bold;
        margin-bottom: 1;
    }

    #extensions-search,
    #session-picker-search,
    #prompt-template-picker-search,
    #skill-picker-search,
    #tools-reference-search {
        height: 3;
        margin-bottom: 1;
        background: $baldric-prompt-background;
        color: $baldric-prompt-text;
        border: tall $baldric-prompt-border;
    }

    #tools-reference-header {
        height: 1;
        color: $baldric-muted-text;
        text-style: bold;
    }

    #prompt-template-editor {
        height: 80%;
    }

    #prompt-template-editor-path {
        height: 1;
        margin-bottom: 1;
        color: $baldric-muted-text;
    }

    #prompt-template-editor-input {
        height: 1fr;
        background: $baldric-prompt-background;
        color: $baldric-prompt-text;
        border: tall $baldric-prompt-border;
    }

    #extensions-list,
    #session-picker-list,
    #prompt-template-picker-list,
    #skill-picker-list,
    #tree-picker-list,
    #tools-reference-list {
        height: auto;
        max-height: 16;
        background: $baldric-transcript-background;
        border: tall $baldric-border;
    }

    ListView,
    OptionList {
        scrollbar-background: $baldric-transcript-background;
        scrollbar-color: $baldric-border;
        scrollbar-color-hover: $baldric-highlight-background;
        scrollbar-background-hover: $baldric-transcript-background;
        scrollbar-color-active: $baldric-accent;
        scrollbar-background-active: $baldric-transcript-background;
        scrollbar-size-vertical: 2;
    }

    ListView > ListItem.-highlight {
        background: $baldric-highlight-background;
        color: $baldric-highlight-text;
    }

    ListView > ListItem.-highlight Label {
        background: $baldric-highlight-background;
        color: $baldric-highlight-text;
    }

    /* Mouse hover mirrors the sidebar's row hover and the keyboard selection
       palette, so every interactive row answers the pointer the same way. */
    ListView > ListItem:hover,
    ListView > ListItem:hover Label {
        background: $baldric-highlight-background;
        color: $baldric-highlight-text;
    }

    OptionList > .option-list--option-highlighted {
        background: $baldric-highlight-background;
        color: $baldric-highlight-text;
    }

    #skill-picker-list .skill-picker-row {
        height: 1;
    }

    #skill-picker-list .skill-picker-name {
        width: 35%;
        text-style: bold;
    }

    #skill-picker-list .skill-picker-description {
        width: 65%;
        color: $baldric-muted-text;
    }

    #skill-picker-list ListItem.-highlight .skill-picker-description {
        color: $baldric-highlight-text;
    }

    #extensions-help,
    #session-picker-help,
    #prompt-template-picker-help,
    #prompt-template-editor-help,
    #skill-picker-help,
    #tree-picker-help,
    #tools-reference-help {
        height: 1;
        margin-top: 1;
        color: $baldric-muted-text;
    }

    #tree-picker-help {
        height: auto;
    }

    ExtensionSelectScreen,
    ExtensionConfirmScreen,
    ExtensionInputScreen,
    LocalBackendPickerScreen,
    LocalBackendScreen,
    LocalChoiceConfirmScreen,
    LocalConfigureScreen,
    LocalConfirmScreen,
    LocalModelActionScreen,
    LocalSearchResultsScreen,
    ProjectTrustScreen {
        align: center middle;
    }

    ProjectTrustScreen {
        background: $baldric-screen-background 60%;
    }

    #extension-select,
    #extension-confirm,
    #extension-input {
        width: 76;
        max-width: 90%;
        height: auto;
        max-height: 70%;
        padding: 1 2;
        background: $baldric-chrome-background;
        border: tall $baldric-border;
    }

    #extension-select-title,
    #extension-confirm-title,
    #extension-input-title {
        height: auto;
        color: $baldric-chrome-text;
        text-style: bold;
        margin-bottom: 1;
    }

    #extension-confirm-message {
        height: auto;
        color: $baldric-chrome-text;
        margin-bottom: 1;
    }

    #extension-select-list,
    #extension-confirm-list {
        height: auto;
        max-height: 16;
        background: $baldric-transcript-background;
        border: tall $baldric-border;
    }

    #extension-input-field {
        background: $baldric-transcript-background;
        border: tall $baldric-border;
    }

    #extension-select-help,
    #extension-confirm-help,
    #extension-input-help {
        height: 1;
        margin-top: 1;
        color: $baldric-muted-text;
    }

    #local-backend-picker,
    #local-backend-screen,
    #local-configure-screen,
    #local-confirm-screen,
    #local-model-action-screen,
    #local-search-results-screen {
        width: 82;
        max-width: 92%;
        height: auto;
        max-height: 82%;
        padding: 1 2;
        background: $baldric-chrome-background;
        border: tall $baldric-border;
    }

    #local-backend-picker-title,
    #local-backend-title,
    #local-configure-title,
    #local-confirm-title,
    #local-model-action-title,
    #local-search-results-title {
        height: auto;
        color: $baldric-chrome-text;
        text-style: bold;
        margin-bottom: 1;
    }

    #local-backend-picker-help,
    #local-backend-help,
    #local-configure-screen Label,
    #local-confirm-message,
    #local-search-results-help {
        color: $baldric-muted-text;
    }

    #local-backend-list,
    #local-backend-status,
    #local-backend-progress,
    #local-model-list,
    #local-action-menu,
    #local-confirm-list,
    #local-choice-list,
    #local-search-results-list,
    #local-configure-screen Input,
    #local-configure-screen Select,
    #local-model-action-input {
        background: $baldric-transcript-background;
        border: tall $baldric-border;
        margin-top: 1;
    }

    #local-backend-list,
    #local-model-list,
    #local-action-menu,
    #local-confirm-list,
    #local-choice-list,
    #local-search-results-list {
        height: auto;
        max-height: 16;
    }

    #local-model-list,
    #local-action-menu {
        max-height: 10;
    }

    #local-model-list:focus,
    #local-action-menu:focus {
        border: tall $baldric-accent;
    }

    #local-model-list.local-section-inactive > ListItem.-highlight,
    #local-action-menu.local-section-inactive > ListItem.-highlight,
    #local-model-list.local-section-inactive > ListItem.-highlight Label,
    #local-action-menu.local-section-inactive > ListItem.-highlight Label {
        background: $baldric-transcript-background;
        color: $baldric-chrome-text;
    }

    #local-model-section-title,
    #local-action-section-title {
        height: 1;
        margin-top: 1;
        color: $baldric-chrome-text;
        text-style: bold;
    }

    #local-backend-progress-bar {
        width: 100%;
        margin-top: 1;
    }

    #local-backend-progress-bar Bar {
        width: 1fr;
    }

    #local-backend-progress-bar Bar > .bar--bar,
    #local-backend-progress-bar Bar > .bar--complete,
    #local-backend-progress-bar Bar > .bar--indeterminate {
        color: $baldric-accent;
        background: $baldric-border;
    }

    #local-backend-picker-footer,
    #local-backend-footer,
    #local-configure-footer,
    #local-confirm-footer,
    #local-model-action-footer,
    #local-search-results-footer {
        height: 1;
        margin-top: 1;
        color: $baldric-muted-text;
    }

    #local-backend-progress {
        min-height: 1;
        color: $baldric-muted-text;
    }

    #project-trust-dialog {
        width: 76;
        max-width: 92%;
        height: auto;
        max-height: 90%;
        padding: 1 2;
        background: $baldric-chrome-background;
        color: $baldric-chrome-text;
        border: tall $baldric-border;
    }

    #project-trust-title {
        color: $baldric-chrome-text;
    }

    #project-trust-path-label,
    #project-trust-summary-label,
    #project-trust-boundary,
    #project-trust-help {
        color: $baldric-muted-text;
    }

    #project-trust-list {
        background: $baldric-transcript-background;
        color: $baldric-screen-text;
        border: tall $baldric-border;
    }

    #project-trust-list ListItem.-highlight,
    #project-trust-list ListItem.-highlight Label {
        background: $baldric-highlight-background;
        color: $baldric-highlight-text;
    }

    #command-output {
        width: 76;
        max-width: 90%;
        height: auto;
        max-height: 70%;
        padding: 1 2;
        background: $baldric-chrome-background;
        color: $baldric-chrome-text;
        border: tall $baldric-border;
    }

    #command-output-title {
        height: 1;
        color: $baldric-chrome-text;
        text-style: bold;
        margin-bottom: 1;
    }

    #command-output-scroll {
        height: auto;
        max-height: 18;
        background: $baldric-transcript-background;
        border: tall $baldric-border;
    }

    #command-output-body {
        color: $baldric-screen-text;
        padding: 1;
    }

    #command-output-help {
        height: 1;
        margin-top: 1;
        color: $baldric-muted-text;
    }

    LoginMethodPickerScreen,
    LoginProviderPickerScreen,
    ThemePickerScreen,
    ModelPickerScreen {
        align: center middle;
    }

    #login-method-picker,
    #login-provider-picker,
    #theme-picker,
    #model-picker {
        width: 76;
        max-width: 90%;
        height: auto;
        max-height: 70%;
        padding: 1 2;
        background: $baldric-chrome-background;
        color: $baldric-chrome-text;
        border: tall $baldric-border;
    }

    #login-method-title,
    #login-provider-title,
    #theme-picker-title,
    #model-picker-title {
        height: 1;
        color: $baldric-chrome-text;
        text-style: bold;
        margin-bottom: 1;
    }

    #model-picker-tabs {
        height: 1;
        color: $baldric-muted-text;
        margin-bottom: 1;
    }

    #login-method-list,
    #login-provider-list,
    #theme-picker-list,
    #model-picker-list {
        height: auto;
        max-height: 12;
        background: $baldric-transcript-background;
        color: $baldric-screen-text;
        border: tall $baldric-border;
    }

    #login-method-list ListItem Label,
    #login-provider-list ListItem Label,
    #theme-picker-list ListItem Label,
    #model-picker-list {
        color: $baldric-screen-text;
    }

    #login-method-list ListItem.-highlight Label,
    #login-provider-list ListItem.-highlight Label,
    #theme-picker-list ListItem.-highlight Label {
        background: $baldric-highlight-background;
        color: $baldric-highlight-text;
    }

    #model-picker-list > .option-list--option-highlighted {
        background: $baldric-highlight-background;
        color: $baldric-highlight-text;
    }

    #login-method-intro {
        height: 1;
        color: $baldric-muted-text;
        margin-bottom: 1;
    }

    #login-method-list {
        height: auto;
        max-height: 10;
    }

    #login-provider-search,
    #model-picker-search {
        height: 3;
        margin-bottom: 1;
        background: $baldric-prompt-background;
        color: $baldric-prompt-text;
        border: tall $baldric-prompt-border;
    }

    #login-method-help,
    #login-provider-help,
    #theme-picker-help,
    #model-picker-help {
        height: 1;
        margin-top: 1;
        color: $baldric-muted-text;
    }

    CustomProviderLoginScreen,
    LoginScreen,
    OAuthLoginScreen {
        align: center middle;
    }

    #login-screen {
        width: 72;
        max-width: 92%;
        height: auto;
        /* A wrapped authorization URL makes this dialog taller than a short
           terminal. Cap it at the screen and scroll instead of overflowing:
           overflowing centers the excess, which pushes the paste field and
           the footer off the bottom and the title off the top. */
        max-height: 100%;
        overflow-y: auto;
        padding: 1 2;
        background: $baldric-chrome-background;
        border: tall $baldric-border;
    }

    #login-title {
        height: 1;
        color: $baldric-chrome-text;
        text-style: bold;
        margin-bottom: 1;
    }

    #login-help,
    #custom-provider-help {
        height: 1;
        color: $baldric-muted-text;
        margin-bottom: 1;
    }

    #login-api-key,
    #login-oauth-code,
    #custom-provider-name,
    #custom-provider-display-name,
    #custom-provider-base-url,
    #custom-provider-api-key-env,
    #custom-provider-models,
    #custom-provider-default-model,
    #custom-provider-api-key {
        background: $baldric-prompt-background;
        color: $baldric-prompt-text;
        border: tall $baldric-prompt-border;
        margin-bottom: 1;
    }

    #login-oauth-url {
        /* Authorization URLs run ~470 chars (Anthropic); clipping them means a
           user copying the URL out of the TUI loses the trailing query
           parameters and the provider rejects the request. Keep every line. */
        min-height: 1;
        height: auto;
        color: $baldric-chrome-text;
        margin-bottom: 1;
    }

    #login-footer {
        height: 1;
        color: $baldric-muted-text;
    }
    """
    BINDINGS: ClassVar[list[BindingEntry]] = []

    def __init__(
        self,
        session: CodingSession,
        *,
        tui_settings: TuiSettings | None = None,
        startup_message: str | None = None,
        startup_notice: str | None = None,
        startup_update_notice: str | None = None,
        deferred_update_notice: Callable[[], str | None] | None = None,
        startup_alerts: Sequence[str] = (),
        startup_notices: Sequence[str] = (),
        initial_prompt: str | None = None,
        show_full_output: bool = False,
    ) -> None:
        self.tui_settings = tui_settings or TuiSettings()
        self.startup_message = startup_message
        self._deferred_update_notice = deferred_update_notice
        legacy_notices = (startup_notice,) if startup_notice else ()
        self.startup_notices = tuple((*startup_notices, *legacy_notices))
        self.initial_prompt = initial_prompt
        # This override is deliberately separate from durable settings. It is
        # reset with every app instance and never participates in tui.json.
        self._sidebar_visibility_override: bool | None = None
        super().__init__()
        self._register_baldric_textual_themes()
        # Assign the resolved theme's name: it is always registered, while the
        # raw settings value may name a custom theme that failed to load. The
        # guard keeps the watcher from persisting the fallback over the user's
        # configured theme.
        self._applying_settings_theme = True
        self.theme = self.tui_settings.resolved_theme.name
        self._applying_settings_theme = False
        self._bindings = BindingsMap(_app_bindings(self.tui_settings.keybindings))
        self.session = session
        self.state = TuiState(skills=session.skills, cwd=session.cwd)
        # A deliberate per-invocation opt-in (like the sidebar override below):
        # startup state rather than a durable preference, so it never reaches
        # tui.json.
        self.state.set_full_output(show_full_output)
        if startup_update_notice is not None:
            self.state.add_item("status", startup_update_notice, highlight="update")
        for alert in startup_alerts:
            self.state.add_item("status", alert, highlight="alert")
        for notice in self.startup_notices:
            self.state.add_item("status", notice)
        if self.tui_settings.theme != self.tui_settings.resolved_theme.name:
            self.state.add_item(
                "status",
                f"Theme '{self.tui_settings.theme}' was not found; "
                f"using {self.tui_settings.resolved_theme.name}.",
            )
        self._prompt_history: tuple[str, ...] = ()
        self._load_session_messages_from_session()
        self._wire_event_consumers(session)
        # Component seam: host-owned tracking of extension
        # widgets so a reload/rebind can force-clear them and a crash can
        # quarantine them. Must exist before _connect_extension_runtime, which
        # clears them on every bind.
        # `_extension_slot_widgets` holds the *intended* widget per key (the swap
        # target, set synchronously); `_extension_slot_mounted` tracks what is
        # actually mounted. A deferred remove() must fully drain before the next
        # mount of the same-id widget, so slot/main-view swaps run on a serialized
        # async continuation (see `_reconcile_slot`/`_reconcile_main_view`).
        self._extension_slot_widgets: dict[str, Widget] = {}
        self._extension_slot_mounted: dict[str, Widget] = {}
        self._extension_slot_slot_ids: dict[str, str] = {}
        self._extension_slot_locks: dict[str, asyncio.Lock] = {}
        self._extension_key_interceptors: list[KeyInterceptor] = []
        self._extension_sidebar_contributions: dict[tuple[str, str], _SidebarContribution] = {}
        self._extension_sidebar_widgets: dict[tuple[str, str], Widget] = {}
        self._extension_sidebar_mounted: dict[tuple[str, str], Widget] = {}
        self._extension_sidebar_lock = asyncio.Lock()
        self._extension_sidebar_theme: TuiTheme | None = None
        self._extension_main_view: _MainViewHandle | None = None
        self._extension_main_view_mounted: Widget | None = None
        self._extension_main_view_lock = asyncio.Lock()
        self._extension_swap_tasks: set[asyncio.Task[None]] = set()
        self._extension_component_failures_reported: set[str] = set()
        self._connect_extension_runtime(session)
        self._prompt_worker: Worker[None] | None = None
        # A submitted prompt is "pending" from its submit call until its worker
        # receives the session's first event (or is cancelled). Submissions
        # arriving in that window must queue instead of replacing the reserved
        # exclusive worker, which would cancel the prompt before it ever runs.
        self._pending_prompt_run_id: int | None = None
        self._pending_prompt_started = asyncio.Event()
        self._compaction_worker: Worker[None] | None = None
        self._compacting = False
        self._compaction_run_id = 0
        # Watchdog heartbeat: refreshed by a timer on the UI loop (see
        # on_mount); a stalled loop stops advancing it.
        self._ui_heartbeat = time.monotonic()
        # Opt-in approval mode (tui_settings.approval_mode == "ask") pauses
        # mutating tool calls on this policy's session-scoped Always rules.
        self.approval_policy = ApprovalPolicy()
        self._prompt_run_id = 0
        self._optimistic_user_messages: list[tuple[int, str]] = []
        self._completion_state = CompletionState()
        self._completion_visible_line_budget: int | None = None
        self._activity_frame = 0
        self._activity_timer: Timer | None = None
        self._last_tool_timer_refresh_at = 0.0
        self._last_activity_indicator_key: tuple[object, ...] | None = None
        self._last_queue_render_key: tuple[object, ...] | None = None
        self._terminal_title = TerminalTitleController()
        self._terminal_notification = TerminalNotificationController(self.tui_settings.turn_notification)
        self._app_has_focus = True
        self._active_notification_keys: set[tuple[str, str]] = set()
        self._supports_pyperclip: bool | None = None
        self._terminal_session_title: str | None = None
        self._sync_session_title()

    def _wire_event_consumers(self, session: CodingSession) -> None:
        """Build the projection and mounted-widget event dispatchers for this run."""
        self.adapter = TuiEventAdapter(self.state, session=session)
        # Incremental transcript updates use the same dispatcher type as the
        # state projection; the fallback refreshes chrome for event types that
        # have no dedicated DOM handler.
        self._dom_dispatcher = EventDispatcher(on_unhandled=lambda _: self._refresh_chrome())
        for event_type, handler_name in DOM_EVENT_HANDLERS.items():
            self._dom_dispatcher.register(event_type, getattr(self, handler_name))

    def _beat_ui_heartbeat(self) -> None:
        """Refresh the watchdog heartbeat from the UI loop.

        Textual timers fire on the event loop, so a blocked loop stops
        advancing ``_ui_heartbeat`` and the watchdog thread reports a stall.
        """
        self._ui_heartbeat = time.monotonic()

    async def approval_gate(self, tool_call: ToolCall) -> tuple[bool, str | None]:
        """Harness before_tool_call hook for the opt-in approval mode.

        Runs only when the user turned approval on and the call is mutating
        (edit/write/bash) without a matching session-scoped Always rule. The
        card previews the would-be diff or command; a rejection's reason is
        returned as the tool error so the model can adapt.
        """
        if self.tui_settings.approval_mode != "ask":
            return False, None
        if tool_call.name not in MUTATING_TOOL_NAMES:
            return False, None
        target = approval_target(tool_call.name, tool_call.arguments)
        if self.approval_policy.decide(tool_call.name, target) is not None:
            return False, None
        try:
            preview = await asyncio.to_thread(
                build_approval_preview,
                tool_call.name,
                tool_call.arguments,
                cwd=self.session.cwd,
            )
            decision = await self.push_screen_wait(
                ApprovalScreen(
                    ApprovalRequest(
                        tool_name=tool_call.name,
                        target=target,
                        preview=preview,
                    ),
                    theme=self.tui_settings.resolved_theme,
                    always_rule=self.approval_policy.preview_rule(tool_call.name, target),
                )
            )
        except Exception as exc:
            # The approval gate is a safety boundary: if the card cannot be
            # shown, fail closed and give the model a reason instead of
            # crashing the turn.
            return (
                True,
                f"Approval UI failed ({type(exc).__name__}: {exc}); call blocked.",
            )
        if decision is None:
            return True, "Rejected by user"
        if decision.remember:
            self.approval_policy.remember(tool_call.name, target)
        if not decision.approved:
            return True, decision.reason or "Rejected by user"
        return False, None

    async def prompt_project_trust(self, request: ProjectTrustRequest) -> TrustChoice | None:
        """Resolve a trust request through the active Textual modal stack."""
        return await self.push_screen_wait(ProjectTrustScreen(request))

    def _sync_session_title(self) -> None:
        """Reflect the active session name in the terminal tab title."""
        self._terminal_session_title = getattr(self.session, "session_title", None)
        self._sync_terminal_title()

    def _is_working(self) -> bool:
        """Return whether the app should show working affordances (agent turn or compaction)."""
        return self.state.running or self._is_compaction_active()

    def _sync_terminal_title(self) -> None:
        """Reflect the active session name and running state in the terminal tab title."""
        # Spinner ticks call this several times per second; the session title
        # is re-read only by `_sync_session_title`, which hits the index.
        self._terminal_title.update(
            self._terminal_session_title,
            running=self._is_working(),
            frame=self._activity_frame,
        )

    def _sync_text_selection_state(self) -> None:
        """Disable native text selection while the transcript is mutating."""
        type(self).ALLOW_SELECT = not self.state.running
        if self.state.running and self.screen_stack:
            with suppress(Exception):
                self.screen.clear_selection()

    def copy_to_clipboard(self, text: str) -> None:
        """Copy text using pyperclip when available, then Textual's fallback."""
        if self._supports_pyperclip is None:
            try:
                import pyperclip  # type: ignore[import-untyped]
            except ImportError:
                self._supports_pyperclip = False
            else:
                self._supports_pyperclip = True
        if self._supports_pyperclip:
            import pyperclip

            with suppress(Exception):
                pyperclip.copy(text)
        super().copy_to_clipboard(text)

    def _register_baldric_textual_themes(self) -> None:
        """Register Baldric themes with Textual's theme system.

        Textual exposes its own theme menu and command palette entries. Registering
        Baldric's built-in themes there makes those controls update the same theme as
        `/theme` instead of changing only Textual's chrome.
        """
        self._registered_themes.clear()
        for theme_name in available_tui_theme_names():
            self.register_theme(_textual_theme_for_baldric_theme(theme_name))

    def _reload_session_themes(self) -> None:
        """Rebind custom themes to the active session's accepted trust snapshot."""
        theme_dirs = getattr(self.session, "theme_dirs", None)
        if theme_dirs is None:
            trust_resolution = getattr(self.session, "project_trust_resolution", None)
            trusted = trust_resolution is None or trust_resolution.trusted
            theme_dirs = BaldricResourcePaths(
                cwd=self.session.cwd,
                project_resources_enabled=trusted,
            ).themes_dirs
        try:
            custom_themes, diagnostics = load_custom_tui_themes(theme_dirs)
        except (OSError, RuntimeError) as exc:
            # Theme discovery must fail closed after a trust/cwd transition:
            # never retain themes from the previous project snapshot.
            custom_themes = {}
            diagnostics = []
            self._notify(f"Could not reload custom themes: {exc}", severity="error")

        set_custom_tui_themes(custom_themes)
        self._register_baldric_textual_themes()
        resolved_theme = self.tui_settings.resolved_theme.name
        self._applying_settings_theme = True
        try:
            if self.theme == resolved_theme:
                # Re-apply CSS when a same-named custom theme changed in place.
                self._watch_theme(resolved_theme)
            else:
                self.theme = resolved_theme
        finally:
            self._applying_settings_theme = False
        for diagnostic in diagnostics:
            severity: Literal["information", "warning", "error"] = (
                "error"
                if diagnostic.severity == "error"
                else "warning"
                if diagnostic.severity == "warning"
                else "information"
            )
            self._notify(diagnostic.format(), severity=severity)

    def _watch_theme(self, theme_name: str) -> None:
        """Keep Textual theme changes synchronized with Baldric's durable TUI theme."""
        super()._watch_theme(theme_name)
        if theme_name not in available_tui_theme_names():
            return
        if getattr(self, "_applying_settings_theme", False):
            return
        baldric_theme: TuiThemeName = theme_name
        if self.tui_settings.theme != baldric_theme:
            self._replace_tui_settings(theme=baldric_theme)
            save_tui_settings(self.tui_settings)
        # Re-render theme-baked chrome so a Textual-side theme switch updates
        # the sidebar even when Baldric's durable settings already match.
        self._refresh_chrome_if_mounted()

    def get_theme_variable_defaults(self) -> dict[str, str]:
        """Return Baldric-specific CSS variables for the selected TUI theme."""
        variables = super().get_theme_variable_defaults()
        return {**variables, **_theme_css_variables(self.tui_settings.resolved_theme)}

    def compose(self) -> ComposeResult:
        """Compose the TUI widgets."""
        with Horizontal(id="workspace"):
            yield SessionSidebar(id="sidebar")
            with Vertical(id="main-pane"):
                yield TranscriptView(
                    id="transcript",
                    min_width=1,
                    wrap=True,
                    highlight=True,
                    markup=False,
                )
                # Component seam: host-managed mount points for
                # extension widgets. Empty until an extension mounts into them.
                yield Container(id="main-slot")
                yield Container(id="above-prompt-slot")
                yield Static("", id="queued-messages")
                with Horizontal(id="prompt-row"):
                    yield Static("τ", id="prompt-prefix")
                    yield PromptInput(
                        placeholder=(
                            "Ask Baldric…  Enter submits, "
                            f"{_key_hint(self.tui_settings.keybindings.insert_newline)} "
                            "inserts a newline"
                        ),
                        id="prompt",
                        tui_keybindings=self.tui_settings.keybindings,
                    )
                yield CompactSessionInfo(id="compact-session-info")
                yield Static("", id="autocomplete")
                yield Container(id="below-prompt-slot")

    async def on_mount(self) -> None:
        """Focus the prompt when the app starts."""
        prompt = self.query_one(PromptInput)
        prompt.shell_mode_style = self.tui_settings.resolved_theme.role_styles["tool"].border
        self._sync_prompt_shell_mode(prompt.text)
        prompt.focus()
        self.set_interval(1.0, self._beat_ui_heartbeat, name="ui-heartbeat")
        self._update_responsive_layout(self.size.width, self.size.height)
        self._apply_sidebar_position()
        self._refresh()
        self._sync_text_selection_state()
        self._refresh_completions()
        if self.startup_message:
            self._notify(self.startup_message, severity="warning")
        if self._deferred_update_notice is not None:
            self.run_worker(self._show_deferred_update_notice(), group="update-check")
        # UI is live and the bridge is installed (__init__) — release the
        # deferred session_start so handlers can notify / open dialogs.
        await self.session.emit_pending_session_start()
        if self.initial_prompt and self.initial_prompt.strip():
            await self._submit_prompt(self.initial_prompt.strip())
        else:
            # Freeze import-time objects; an initial prompt collects when it settles.
            self.call_after_refresh(_collect_garbage_while_idle)

    async def _show_deferred_update_notice(self) -> None:
        """Run a due PyPI update check off the event loop and show any notice."""
        check = self._deferred_update_notice
        self._deferred_update_notice = None
        if check is None:
            return
        message = await _run_in_daemon_thread(check)
        if message is None or not self.screen_stack:
            return
        if self._is_working():
            # Appending a transcript row would cut into the streaming reply.
            self._notify(message)
            return
        self.state.add_item("status", message, highlight="update")
        try:
            transcript = self.query_one("#transcript", TranscriptView)
        except NoMatches:
            return
        await transcript.append_item(
            self.state.items[-1],
            theme=self.tui_settings.resolved_theme,
            show_tool_results=self.state.show_tool_results,
        )

    async def on_event(self, event: events.Event) -> None:
        """Consult extension key interceptors before Textual's dispatch.

        Ports Pi's ``onTerminalInput``: a registered interceptor sees a key at
        the earliest point in key processing — before baldric's app-level priority
        bindings (``down``/``up``/``tab``/``alt+enter`` in ``_app_bindings``)
        and before the focused widget. Textual's ``App.on_event`` runs
        ``_check_bindings(key, priority=True)`` ahead of forwarding a key to the
        focused widget, so a focused extension widget would otherwise never
        receive those keys; this pre-dispatch hook is the only place an
        extension can own them.

        Interceptors are consulted only on the main screen (never while a modal
        dialog/picker sits on the screen stack) and only when at least one is
        registered, so the default path is untouched. Interceptors therefore
        see EVERY main-screen key regardless of focus and must self-gate.

        The hard interrupt/exit keys in
        :data:`RESERVED_EXTENSION_INTERCEPTOR_KEYS` are skipped entirely, so
        they always reach normal dispatch even behind a misbehaving interceptor.
        """
        if (
            isinstance(event, events.Key)
            and not event.is_forwarded
            and event.key not in RESERVED_EXTENSION_INTERCEPTOR_KEYS
            and self._extension_key_interceptors
            and len(self.screen_stack) <= 1
            and self._run_extension_key_interceptors(event, self._current_prompt_text())
        ):
            event.stop()
            event.prevent_default()
            return
        await super().on_event(event)

    def on_unmount(self) -> None:
        """Stop activity animations and drop extension widgets on teardown."""
        if self._activity_timer is not None:
            self._activity_timer.stop()
            self._activity_timer = None
        self._terminal_title.restore()
        self._clear_extension_components()
        gc.unfreeze()

    def on_app_blur(self) -> None:
        """Remember that terminal attention should be requested when the run settles."""
        self._app_has_focus = False

    def on_app_focus(self) -> None:
        """Suppress turn notifications while the Baldric terminal surface is active."""
        self._app_has_focus = True

    def on_paste(self, event: events.Paste) -> None:
        """Route pastes that arrive while no widget holds keyboard focus.

        Textual clears widget focus whenever the terminal reports lost focus
        (``CSI ? 1004 h``), and pastes are dropped when nothing is focused. OS
        drag-and-drop from sources that never hand focus back to the terminal --
        notably the macOS Dock -- delivers the dropped paths in exactly that
        state, so the paste bubbles up here instead of reaching the prompt.
        Clipboard pastes always require terminal focus, so this only reroutes
        drops that would otherwise be silently discarded.
        """
        if self.focused is not None:
            return
        try:
            prompt = self.screen.query_one("#prompt", PromptInput)
        except NoMatches:
            # A modal screen owns the input; leave its own handling alone.
            return
        event.stop()
        prompt.insert_pasted_text(event.text)

    def on_resize(self, event: Resize) -> None:
        """Update responsive chrome when the terminal changes size."""
        self._completion_visible_line_budget = None
        self._update_responsive_layout(event.size.width, event.size.height)

    def on_click(self, event: events.Click) -> None:
        """Return keyboard focus to the prompt after clicks in the main TUI."""
        if event.button != 1:
            return
        if self._extension_main_view is not None:
            # An extension main view (e.g. a subagent conversation viewer) owns
            # the main area and its keyboard; yanking focus back to the prompt
            # would silently reroute every key — esc, toggles, typed text — to
            # the main chat. Clicking the prompt itself still focuses it via
            # Textual's native mouse-down focus.
            return
        with suppress(NoMatches):
            self.screen.query_one("#prompt", PromptInput).focus()

    @on(events.TextSelected)
    async def on_text_selected(self) -> None:
        """Optionally copy selected text automatically."""
        active_screen = self.screen
        if not (
            self.tui_settings.auto_copy_selection or getattr(active_screen, "auto_copy_selection", False)
        ):
            return
        selection = active_screen.get_selected_text()
        if selection:
            self.copy_to_clipboard(selection)
            self._notify("Copied selection to clipboard.")

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Update prompt autocomplete when the prompt text changes."""
        if event.text_area.id != "prompt":
            return
        prompt = self.query_one("#prompt", PromptInput)
        prompt.sync_pending_paste()
        # Read text and cursor from the widget so both come from one snapshot.
        text = prompt.text
        self._sync_prompt_shell_mode(text)
        self._completion_state = self._build_completion_state(text, cursor=prompt.cursor_position)
        self._refresh_completions()

    def on_text_area_selection_changed(self, event: TextArea.SelectionChanged) -> None:
        """Close prompt autocomplete when the caret leaves the completed token."""
        if event.text_area.id != "prompt":
            return
        # Edits post SelectionChanged before Changed; check after Changed has rebuilt.
        self.call_later(self._close_completions_if_caret_left_token)

    def _close_completions_if_caret_left_token(self) -> None:
        if not self._completion_state.items:
            return
        item = self._completion_state.items[0]
        cursor = self.query_one("#prompt", PromptInput).cursor_position
        if item.start < cursor <= item.end:
            return
        self._completion_state = CompletionState()
        self._refresh_completions()

    async def action_submit_prompt(self) -> None:
        """Accept a changing non-file completion, or submit the current prompt text."""
        selected = self._completion_state.selected
        if selected is not None and selected.kind is not CompletionKind.FILE_REFERENCE:
            prompt = self.query_one("#prompt", PromptInput)
            text_before_completion = prompt.text
            self.action_accept_completion()
            if prompt.text != text_before_completion:
                return
        await self._submit_prompt_from_editor(streaming_behavior="steer")

    async def action_submit_follow_up(self) -> None:
        """Submit the current prompt as a queued follow-up while running."""
        await self._submit_prompt_from_editor(streaming_behavior="follow_up")

    async def _submit_prompt_from_editor(
        self,
        *,
        streaming_behavior: Literal["steer", "follow_up"],
    ) -> None:
        prompt = self.query_one("#prompt", PromptInput)
        raw_text = prompt.text_for_submission()

        text = raw_text.strip()
        if not text:
            prompt.text = ""
            prompt._clear_pending_paste()
            self._completion_state = CompletionState()
            self._refresh_completions()
            return

        if self._is_compaction_active():
            if text.startswith("/compact"):
                self._notify("A compaction is already running.", severity="warning")
            else:
                prompt.text = raw_text
                prompt.move_cursor(text_end_location(raw_text))
                self._notify(
                    "Compaction is still running. You can keep editing, but wait to submit.",
                    severity="warning",
                )
            return

        prompt.text = ""
        prompt._clear_pending_paste()
        self._completion_state = CompletionState()
        self._refresh_completions()

        terminal_command = parse_terminal_command(text)
        if terminal_command is not None:
            self.run_worker(
                self._run_terminal_command(
                    terminal_command.command,
                    add_to_context=terminal_command.add_to_context,
                ),
                group="terminal-command",
                exclusive=True,
            )
            return

        command = self.session.handle_command(text)
        if command.handled:
            await self._dispatch_command_outcome(text, command.outcome, prompt=prompt, raw_text=raw_text)
            return

        if self._pending_prompt_run_id is not None:
            # A submitted prompt is waiting for its first frame; hold this
            # submission so it cannot replace the reserved exclusive worker
            # before the session run starts.
            started = self._pending_prompt_started
            await started.wait()
            if self.state.running or bool(getattr(self.session, "is_running", False)):
                # The reserved run is live; queue as during any running turn.
                self._remember_prompt(text)
                await self._queue_prompt(text, streaming_behavior=streaming_behavior)
                return
            # The reserved run resolved without starting; submit fresh below.
        if self.state.running:
            self._remember_prompt(text)
            await self._queue_prompt(text, streaming_behavior=streaming_behavior)
            return

        self._remember_prompt(text)
        await self._submit_prompt(text)

    async def _dispatch_command_outcome(
        self,
        text: str,
        outcome: CommandOutcome,
        *,
        prompt: PromptInput,
        raw_text: str,
    ) -> None:
        """Interpret one command outcome: run its effect, then show its message."""
        if outcome.kind is CommandKind.OPEN_PICKER:
            proceed = await self._open_command_picker(outcome, prompt=prompt, raw_text=raw_text)
            if not proceed:
                return
        elif outcome.kind is CommandKind.RELOAD:
            try:
                summary = await self.session.reload()
            except ValueError as exc:
                self._notify(f"Could not reload: {exc}", severity="error")
                self._refresh()
                return
            self._reload_session_themes()
            outcome = replace(
                outcome,
                message=format_reload_summary(summary),
                display=MessageDisplay.TRANSCRIPT,
            )
        elif outcome.kind is CommandKind.NEW_SESSION:
            await self._new_session()
        elif outcome.kind is CommandKind.COMPACT:
            if not await self._run_compact_outcome(outcome, prompt=prompt, raw_text=raw_text):
                return
        elif outcome.kind is CommandKind.EXPORT:
            destination = Path(outcome.text) if outcome.text else None
            try:
                exported_path = await self.session.export(
                    destination,
                    format=outcome.format,
                )
                self._append_command_message(text, f"Exported session to {exported_path}")
            except Exception as exc:  # surface command failures in the TUI
                self._notify(f"Could not export session: {exc}", severity="error")
                return
        elif outcome.kind is CommandKind.MODEL_SELECTED:
            self.run_worker(
                self._switch_model(
                    ModelChoice(
                        provider_name=outcome.provider or self.session.provider_name,
                        model=outcome.text or "",
                    )
                ),
                exclusive=False,
            )
        elif outcome.kind is CommandKind.THINKING_SET:
            await self._set_thinking_level(outcome.text or "")
        elif outcome.kind is CommandKind.THEME_SET:
            self._set_tui_theme(outcome.text or "")
        elif outcome.kind is CommandKind.TOGGLE_APPROVALS:
            new_mode: Literal["auto", "ask"] = "auto" if self.tui_settings.approval_mode == "ask" else "ask"
            # TuiSettings is a frozen dataclass, so a toggle replaces the value
            # instead of mutating it in place.
            self.tui_settings = replace(self.tui_settings, approval_mode=new_mode)
            save_tui_settings(self.tui_settings)
            self._notify(f"Approval prompts: {new_mode}")
        elif outcome.kind is CommandKind.TOGGLE_SIDEBAR:
            self._toggle_sidebar_visibility()
        elif outcome.kind is CommandKind.SESSION_NAMED:
            try:
                await self.session.set_session_name(outcome.text or "")
            except ValueError as exc:
                self._notify(f"Could not rename session: {exc}", severity="error")
                self._refresh()
                return
            self._sync_session_title()

        self.state.set_skills(self.session.skills)
        self._show_command_message_by_display(text, outcome)
        self._refresh()
        if outcome.kind is CommandKind.EXIT:
            self.exit()

    async def _open_command_picker(
        self,
        outcome: CommandOutcome,
        *,
        prompt: PromptInput,
        raw_text: str,
    ) -> bool:
        """Open the picker an outcome requests; False stops later display steps."""
        picker = outcome.picker
        if picker is PickerKind.MODEL:
            self._open_model_picker()
        elif picker is PickerKind.SCOPED_MODELS:
            self._open_scoped_models_picker()
        elif picker is PickerKind.LOCAL_BACKEND:
            self._open_local_backend_picker()
        elif picker is PickerKind.THEME:
            self._open_theme_picker()
        elif picker is PickerKind.SESSION_RESUME:
            if outcome.session_id:
                await self._resume_session(outcome.session_id)
            else:
                self.action_open_session_picker()
        elif picker is PickerKind.PROMPTS:
            self._open_prompt_template_picker()
        elif picker is PickerKind.TREE:
            if self._is_agent_or_queue_active():
                prompt.text = raw_text
                prompt.move_cursor(text_end_location(raw_text))
                self._notify(TREE_RUNNING_MESSAGE, severity="warning")
                return False
            await self._open_tree_picker()
        elif picker is PickerKind.LOGIN_METHOD:
            self._open_login_picker()
        elif picker is PickerKind.CUSTOM_PROVIDER_LOGIN:
            self._open_custom_provider_login()
        elif picker is PickerKind.LOGIN_PROVIDER:
            self._open_login(outcome.provider or "", method=outcome.method)
        elif picker is PickerKind.LOGOUT_PROVIDER:
            if outcome.provider:
                self._logout(outcome.provider)
            else:
                self._open_logout_picker()
        elif picker is PickerKind.SKILLS:
            self._open_skills_picker()
        elif picker is PickerKind.TOOLS:
            self._open_tools_reference()
        elif picker is PickerKind.EXTENSIONS:
            self.push_screen(
                ExtensionsScreen(
                    self.session.extension_runtime,
                    theme=self.tui_settings.resolved_theme,
                )
            )
        return True

    async def _run_compact_outcome(
        self,
        outcome: CommandOutcome,
        *,
        prompt: PromptInput,
        raw_text: str,
    ) -> bool:
        """Start compaction; False stops later display steps (matches old guards)."""
        if self._is_compaction_active():
            self._notify("A compaction is already running.", severity="warning")
            return True
        if self._is_agent_or_queue_active():
            prompt.text = raw_text
            prompt.move_cursor(text_end_location(raw_text))
            self._notify(
                "Wait for the current agent turn and queued messages to finish before compacting.",
                severity="warning",
            )
            return False
        self._compaction_worker = self.run_worker(
            self._run_compaction(outcome.text or ""),
            exclusive=False,
        )
        return True

    def _show_command_message_by_display(self, text: str, outcome: CommandOutcome) -> None:
        if not outcome.message:
            return
        if outcome.display is MessageDisplay.NOTIFICATION:
            self._notify(outcome.message)
        elif outcome.display is MessageDisplay.TRANSCRIPT:
            self._append_command_message(
                text,
                outcome.message,
                system_prompt_inspection=outcome.system_prompt_inspection,
            )
        else:
            self._show_command_message(text, outcome.message)

    def _remember_prompt(self, text: str) -> None:
        """Remember a submitted user prompt for lightweight input recall."""
        if not text.strip():
            return
        self._prompt_history = (*self._prompt_history, text)

    def _load_session_messages_from_session(self) -> None:
        """Load visible session messages and reseed prompt history from them."""
        self.state.load_messages(self.session.messages)
        # Custom entries (append_entry) render as their own transcript rows via
        # registered entry renderers; a namespace with no renderer falls back
        # to generic JSON text so persisted data is never invisible.
        for entry in self.session.state.custom_entries:
            self.state.add_item(
                "custom",
                f"custom entry `{entry.namespace}`",
                custom_type=entry.namespace,
                details=dict(entry.data),
                entry_namespace=entry.namespace,
            )
        self._prompt_history = tuple(
            message.text
            for message in self.session.messages
            if isinstance(message, UserMessage) and message.text.strip()
        )

    def _is_compaction_active(self) -> bool:
        """Return whether a compaction (manual worker or automatic) is still running.

        Automatic compaction is tracked by the adapter as ``state.compacting``;
        only consulting the manual worker here let submissions and session
        mutations race an in-flight threshold compaction.
        """
        if self.state.compacting or self._compacting:
            return True
        worker = self._compaction_worker
        return worker is not None and not worker.is_finished and not worker.is_cancelled

    def _is_agent_or_queue_active(self) -> bool:
        """Return whether a session mutation would race agent, queued, or compaction work."""
        self._sync_queue_state()
        worker = self._prompt_worker
        is_worker_active = worker is not None and not worker.is_finished and not worker.is_cancelled
        is_session_running = bool(getattr(self.session, "is_running", False))
        return (
            self.state.running
            or is_session_running
            or is_worker_active
            or self.state.queued_message_count > 0
            or self._is_compaction_active()
        )

    async def _run_compaction(self, summary: str) -> None:
        """Run manual compaction without disabling prompt editing."""
        self._compaction_run_id += 1
        run_id = self._compaction_run_id
        self._compacting = True
        try:
            self.state.clear()
            self.state.add_item("status", "Compacting session…")
            self._refresh()
            compact_message = await self.session.compact(summary)
        except asyncio.CancelledError:
            return
        except Exception as exc:  # surface command failures in the TUI
            self._notify(f"Error: {exc}", severity="error")
            return
        finally:
            # A cancelled run can tear down after a newer compaction started, so only
            # clear working state this run still owns.
            if self._compaction_run_id == run_id:
                self._compacting = False
                self._compaction_worker = None
                self._refresh_chrome_if_mounted()
        self.state.clear()
        self.state.set_skills(self.session.skills)
        self._load_session_messages_from_session()
        self._notify(compact_message)
        self._refresh()
        if not self._app_has_focus:
            self._terminal_notification.notify_turn_finished()

    async def _submit_prompt(
        self,
        text: str,
        *,
        source: Literal["interactive", "extension"] = "interactive",
        custom_type: str | None = None,
        details: dict[str, JSONValue] | None = None,
    ) -> None:
        """Add a prompt to the transcript and start the agent worker."""
        self._prompt_run_id += 1
        run_id = self._prompt_run_id
        # Reserve the run before any await: a submission arriving while this
        # one renders its optimistic row or waits for its first frame must
        # queue instead of replacing the reserved exclusive worker, which
        # would cancel the prompt before it ever reaches the session.
        started = asyncio.Event()
        self._pending_prompt_run_id = run_id
        self._pending_prompt_started = started
        try:
            # Custom messages are never rendered optimistically: the optimistic
            # dedupe matches on exact content equality with the post-expansion
            # event (see _consume_optimistic_user_event), and a mismatch would
            # double-render. They render once, from the confirmed user event,
            # which carries their custom_type/details.
            if custom_type is None and _should_optimistically_render_prompt(text):
                self._optimistic_user_messages.append((run_id, text))
                await self._append_optimistic_user_message(text)
            self._prompt_worker = self.run_worker(
                self._run_prompt_after_refresh(
                    text,
                    run_id,
                    started=started,
                    source=source,
                    custom_type=custom_type,
                    details=details,
                ),
                exclusive=True,
            )
        except BaseException:
            # The run never started, so its optimistic row has no confirming
            # event coming; release submitters and drop the reservation.
            if self._pending_prompt_run_id == run_id:
                self._pending_prompt_run_id = None
            started.set()
            self._clear_optimistic_user_messages(run_id=run_id)
            raise

    async def _run_prompt_after_refresh(
        self,
        text: str,
        run_id: int,
        *,
        started: asyncio.Event,
        source: Literal["interactive", "extension"],
        custom_type: str | None,
        details: dict[str, JSONValue] | None,
    ) -> None:
        """Start a prompt run once the optimistic prompt has been painted."""
        # Textual starts workers eagerly, so without this wait the session's
        # synchronous setup (input hooks, persistence) runs inside the submit
        # handler and delays the frame that shows the submitted prompt.
        # (`App.wait_for_refresh` cannot be used: it requires `App._task`,
        # which only `run_test` sets.)
        try:
            refreshed = asyncio.Event()
            if self.call_after_refresh(refreshed.set):
                await refreshed.wait()
        except asyncio.CancelledError:
            # The run never started, so its optimistic row has no confirming
            # event coming; release submitters and drop the reservation.
            if self._pending_prompt_run_id == run_id:
                self._pending_prompt_run_id = None
            started.set()
            self._clear_optimistic_user_messages(run_id=run_id)
            raise
        await self._run_prompt(
            text,
            run_id,
            source=source,
            custom_type=custom_type,
            details=details,
            on_started=started,
        )

    async def _append_optimistic_user_message(
        self,
        text: str,
        *,
        custom_type: str | None = None,
        details: dict[str, JSONValue] | None = None,
    ) -> None:
        """Render a submitted user message immediately without rebuilding the transcript."""
        start_index = len(self.state.items)
        self.state.add_user_message(text, custom_type=custom_type, details=details)
        self._follow_transcript_output()
        if not self.screen_stack:
            self._refresh()
            return
        theme = self.tui_settings.resolved_theme
        try:
            transcript = self.query_one("#transcript", TranscriptView)
        except NoMatches:
            self._refresh()
            return
        for item in self.state.items[start_index:]:
            await transcript.append_item(
                item,
                theme=theme,
                show_tool_results=self.state.show_tool_results,
                scroll_end=True,
                custom_markup=self.state.resolve_custom_markup(item, expanded=self.state.show_tool_results),
            )
        self._refresh_chrome(theme=theme)

    def _consume_optimistic_user_event(self, event: CodingSessionEvent, *, run_id: int) -> bool:
        """Return whether a user event confirms an already-rendered optimistic message."""
        if not isinstance(event, MessageEndEvent) or not isinstance(event.message, UserMessage):
            return False
        for index, (pending_run_id, pending_text) in enumerate(self._optimistic_user_messages):
            if pending_run_id == run_id and pending_text == event.message.content:
                del self._optimistic_user_messages[index]
                return True
        return False

    def _replace_transformed_optimistic_user_message(self, event: CodingSessionEvent, *, run_id: int) -> bool:
        """Reconcile a transformed prompt with its optimistic render.

        An extension `input` hook may transform the submitted text inside
        session.prompt, so the confirmed UserMessage no longer matches the
        optimistically rendered original (the exact-equality path above).
        Rewrite the optimistic item in place and redraw, instead of letting
        the confirmed event append a second user item alongside the stale
        original. Runs after _consume_optimistic_user_event, so it only fires
        when this run's pending optimistic text mismatches — the run's own
        prompt confirmation is the first user event of the run, so a queued
        steering/follow-up user message can never be mistaken for it.
        """
        if not isinstance(event, MessageEndEvent) or not isinstance(event.message, UserMessage):
            return False
        for index, (pending_run_id, pending_text) in enumerate(self._optimistic_user_messages):
            if pending_run_id != run_id:
                continue
            del self._optimistic_user_messages[index]
            for item in reversed(self.state.items):
                if item.role == "user" and item.text == pending_text:
                    item.text = event.message.text
                    break
            self._refresh()
            self._sync_session_title()
            return True
        return False

    def _clear_optimistic_user_messages(self, *, run_id: int) -> None:
        """Drop unconfirmed optimistic messages once their run is no longer active."""
        self._optimistic_user_messages = [
            pending for pending in self._optimistic_user_messages if pending[0] != run_id
        ]

    async def _append_confirmed_user_message(self, message: AgentMessage) -> None:
        """Render a non-optimistic user/custom event incrementally when possible."""
        if isinstance(message, UserMessage):
            await self._append_optimistic_user_message(message.text)
            return
        if isinstance(message, CustomMessage):
            if message.display:
                await self._append_optimistic_user_message(
                    message.text,
                    custom_type=message.custom_type,
                    details=message.details if isinstance(message.details, dict) else None,
                )
            return
        self._refresh()

    # -- component seam ------------------------------------------------------

    def _current_prompt_text(self) -> str:
        """Return the prompt-editor text, or "" before the prompt exists."""
        try:
            return self.query_one("#prompt", PromptInput).text
        except NoMatches:
            return ""

    def _release_main_view_handle(self, handle: _MainViewHandle | None) -> None:
        """Mark a host-torn-down handle closed and resolve its ``wait()`` with None.

        Used by the teardown paths the host drives itself (supersede, session
        rebind, mount failure, quarantine) — as opposed to an explicit
        ``handle.close(result)`` from the extension — so a pending ``wait()``
        never leaks unresolved and ``is_open`` reports False.
        """
        if handle is None:
            return
        handle._open = False
        handle._resolve(None)

    def _restore_main_transcript(self) -> None:
        """Hide the main slot and bring the main transcript back into focus."""
        if not self.screen_stack:
            return
        with suppress(NoMatches):
            self.query_one("#main-slot", Container).display = False
        with suppress(NoMatches):
            pane = self.query_one("#transcript", TranscriptView)
            pane.display = True
            # Re-anchor the restored main transcript so returning to a live
            # conversation lands at the bottom (mirrors _follow_transcript_output).
            pane.follow_output()
        with suppress(NoMatches):
            self.query_one("#prompt", PromptInput).focus()

    def _handle_exception(self, error: Exception) -> None:
        """Quarantine a crashing extension widget instead of tearing down.

        Overrides Textual's private ``App._handle_exception`` (there is no
        public error hook — ``hasattr(App, "on_exception")`` is False on the
        pinned Textual). If the traceback touches a tracked extension widget we
        remove it and keep running; otherwise we defer to Textual's default so
        core's own bugs still surface. This private-API coupling is a contract
        cost the component-seam experiment deliberately accepts.
        """
        if self._quarantine_extension_widget(error):
            return
        super()._handle_exception(error)

    def _follow_transcript_output(self) -> None:
        """Put the transcript back in follow mode for explicit user actions."""
        if not self.screen_stack:
            return
        with suppress(NoMatches):
            self.query_one("#transcript", TranscriptView).follow_output()

    async def _run_terminal_command(self, command: str, *, add_to_context: bool) -> None:
        run_terminal_command = getattr(self.session, "run_terminal_command", None)
        if not callable(run_terminal_command):
            self._notify("Terminal commands are not available.", severity="error")
            return

        item_index = len(self.state.items)
        self.state.add_item(
            "tool",
            f"$ {command.strip()}",
            always_show_tool_result=True,
        )
        item = self.state.items[item_index]
        self._follow_transcript_output()
        transcript = self.query_one("#transcript", TranscriptView)
        await transcript.append_item(
            item,
            theme=self.tui_settings.resolved_theme,
            show_tool_results=True,
            scroll_end=True,
        )
        self._refresh_chrome()

        try:
            result = await run_terminal_command(command, add_to_context=add_to_context)
        except Exception as exc:  # surface command execution failures in the TUI
            if item_index < len(self.state.items):
                item = self.state.items[item_index]
                item.tool_result_text = format_terminal_command_result_block(
                    ok=False,
                    added_to_context=add_to_context,
                    output=str(exc),
                )
            self._notify(f"Could not run command: {exc}", severity="error")
            await transcript.update_item(
                item,
                theme=self.tui_settings.resolved_theme,
                show_tool_results=True,
            )
            self._refresh_chrome()
            return

        if item_index >= len(self.state.items):
            return
        item = self.state.items[item_index]
        item.text = f"$ {result.command}"
        item.tool_result_text = format_terminal_command_result_block(
            ok=result.ok,
            added_to_context=result.added_to_context,
            output=result.output,
        )
        # Keep the untruncated output when the preview hid some of it, so
        # `--show-full-output` (and the tool-results toggle) can reveal it
        # without re-running the command.
        full_output_text = format_terminal_command_result_block(
            ok=result.ok,
            added_to_context=result.added_to_context,
            output=result.output,
            full=True,
        )
        item.tool_result_full_text = None if full_output_text == item.tool_result_text else full_output_text
        item.full_output = self.state.show_full_output
        self._follow_transcript_output()
        await transcript.update_item(
            item,
            theme=self.tui_settings.resolved_theme,
            show_tool_results=True,
        )
        self._refresh_chrome()

    def _replace_tui_settings(self, *, theme: TuiThemeName) -> None:
        """Replace the current immutable TUI settings with a new theme.

        Uses dataclasses.replace so unrelated settings (approval_mode,
        editor_command, ...) survive a theme change; rebuilding by hand here
        silently reset them to defaults and persisted that.
        """
        self.tui_settings = replace(self.tui_settings, theme=theme)

    def _set_tui_theme(self, theme: TuiThemeName) -> None:
        if theme not in available_tui_theme_names():
            self._notify(f"Unknown theme: {theme}", severity="error")
            return
        self._replace_tui_settings(theme=theme)
        save_tui_settings(self.tui_settings)
        self.theme = theme
        self._refresh()

    async def _queue_prompt(
        self,
        text: str,
        *,
        streaming_behavior: Literal["steer", "follow_up"],
    ) -> None:
        """Queue a prompt for the active agent worker."""
        try:
            async for event in self.session.prompt(text, streaming_behavior=streaming_behavior):
                self.adapter.apply(event)
        except Exception as exc:  # surface queueing failures in the TUI
            self._notify(f"Could not queue message: {exc}", severity="error")
            return
        self._refresh_chrome()

    async def _run_prompt(
        self,
        text: str,
        run_id: int | None = None,
        *,
        source: Literal["interactive", "extension"] = "interactive",
        custom_type: str | None = None,
        details: dict[str, JSONValue] | None = None,
        on_started: asyncio.Event | None = None,
    ) -> None:
        """Run one prompt and stream session events into the TUI state."""
        active_run_id = self._prompt_run_id if run_id is None else run_id
        run_started = False
        try:
            async for event in self.session.prompt(
                text, source=source, custom_type=custom_type, details=details
            ):
                if not run_started:
                    # The session is running from the first event on; release
                    # submitters waiting for the reserved prompt to start.
                    run_started = True
                    if on_started is not None:
                        on_started.set()
                if active_run_id != self._prompt_run_id:
                    return
                if self._consume_optimistic_user_event(event, run_id=active_run_id):
                    self._sync_text_selection_state()
                    self._refresh_chrome()
                    continue
                if self._replace_transformed_optimistic_user_message(event, run_id=active_run_id):
                    self._sync_text_selection_state()
                    continue
                if not (_is_user_message_end_event(event) and self.screen_stack):
                    self.adapter.apply(event)
                self._sync_text_selection_state()
                await self._apply_streaming_transcript_event(event)
                if isinstance(event, AgentSettledEvent):
                    self.call_after_refresh(_collect_garbage_while_idle)
                    if not self._app_has_focus:
                        self._terminal_notification.notify_turn_finished()
        except Exception as exc:  # surface unexpected worker errors in the TUI
            if active_run_id != self._prompt_run_id:
                return
            if getattr(self.session, "has_pending_selection", False):
                prompt = self.query_one("#prompt", PromptInput)
                if not prompt.text:
                    prompt.text = text
                    prompt.move_cursor(text_end_location(text))
                    prompt.focus()
            message = _format_prompt_error(exc, self.session)
            self.state.error = message
            self.state.add_item("error", message)
            self.state.running = False
            self.state.compacting = False
            self._sync_text_selection_state()
            self._refresh()
        finally:
            self._clear_optimistic_user_messages(run_id=active_run_id)
            if self._pending_prompt_run_id == active_run_id:
                self._pending_prompt_run_id = None
            if on_started is not None:
                # Runs without events (for example an input hook that handled
                # the prompt) must still release submitters.
                on_started.set()
            if active_run_id == self._prompt_run_id:
                self._prompt_worker = None

    async def _apply_streaming_transcript_event(self, event: CodingSessionEvent) -> None:
        """Apply an agent event to mounted transcript widgets without full redraws."""
        if not self.screen_stack:
            self._refresh()
            return
        try:
            self.query_one("#transcript", TranscriptView)
        except NoMatches:
            self._refresh()
            return
        for result in self._dom_dispatcher.dispatch(event):
            if isawaitable(result):
                await result

    def _dom_transcript(self) -> TranscriptView:
        """Return the mounted transcript view; the caller has checked it exists."""
        return self.query_one("#transcript", TranscriptView)

    async def _dom_agent_start(self, event: AgentStartEvent) -> None:
        self._refresh_chrome()

    async def _dom_agent_end(self, event: AgentEndEvent) -> None:
        await self._dom_transcript().finish_assistant_message()
        self._refresh_chrome()

    async def _dom_message_start(self, event: MessageStartEvent) -> None:
        """Streaming deltas mount their widgets on their first update."""

    async def _dom_message_update(self, event: MessageUpdateEvent) -> None:
        theme = self.tui_settings.resolved_theme
        transcript = self._dom_transcript()
        nested = event.assistant_message_event
        if isinstance(nested, TextDeltaEvent):
            await transcript.append_assistant_delta(nested.delta, theme=theme)
        elif isinstance(nested, ThinkingEndEvent):
            await transcript.finish_thinking_message()
        elif isinstance(nested, ThinkingDeltaEvent):
            await transcript.append_thinking_delta(
                nested.delta,
                theme=theme,
                show_thinking=self.state.show_thinking,
            )

    async def _dom_message_end(self, event: MessageEndEvent) -> None:
        message = event.message
        if isinstance(message, (UserMessage, CustomMessage)):
            await self._append_confirmed_user_message(message)
            self._sync_session_title()
            return
        if not isinstance(message, AssistantMessage):
            return
        if message.stop_reason in {"error", "aborted"}:
            # The adapter projected any partial response plus the error into
            # canonical display state. Rebuild once at this terminal boundary so
            # the mounted transcript cannot drop the error.
            self._refresh()
            return
        await self._finish_assistant_message(message)
        self._refresh_chrome()

    async def _finish_assistant_message(self, message: AssistantMessage) -> None:
        theme = self.tui_settings.resolved_theme
        transcript = self._dom_transcript()
        # The canonical-item slice below uses the same visibility filter as
        # ``TuiState.add_assistant_message``; a disagreement misaligns the slice.
        visible_blocks = assistant_visible_blocks(message)
        canonical_items = self.state.items[-len(visible_blocks) :] if visible_blocks else []
        if not visible_blocks:
            # Tool-only message: it streamed a blank buffer (providers emit
            # "\n\n" next to calls), so drop its provisional widgets without
            # remounting the window, which would yank a user who scrolled back.
            await transcript.discard_provisional_assistant_message()
        elif any(isinstance(block, ThinkingContent) for block in message.content) or len(visible_blocks) > 1:
            # Replace only this message's provisional streaming widgets,
            # including thinking filtered out as whitespace-only; unrelated
            # history remains mounted and selectable.
            await transcript.finish_structured_assistant_message(
                canonical_items,
                theme=theme,
                show_thinking=self.state.show_thinking,
            )
        else:
            canonical_item = canonical_items[-1] if canonical_items else None
            await transcript.finish_assistant_message(message.text, item=canonical_item)

    async def _dom_tool_execution_start(self, event: ToolExecutionStartEvent) -> None:
        await self._dom_transcript().finish_assistant_message()
        await self._refresh_tool_widget(event.tool_call_id, append=True)
        self._refresh_chrome()

    async def _dom_tool_execution_update(self, event: ToolExecutionUpdateEvent) -> None:
        await self._dom_transcript().finish_assistant_message()
        await self._refresh_tool_widget(event.tool_call_id)
        self._refresh_chrome()

    async def _dom_tool_execution_end(self, event: ToolExecutionEndEvent) -> None:
        await self._refresh_tool_widget(event.tool_call_id)
        self._refresh_chrome()

    async def _refresh_tool_widget(self, tool_call_id: str, *, append: bool = False) -> None:
        """Update a mounted tool row in place, appending it when it is new."""
        item = self.state.find_tool_item(tool_call_id)
        if item is None:
            return
        theme = self.tui_settings.resolved_theme
        expanded = self.state.show_tool_results or item.always_show_tool_result
        transcript = self._dom_transcript()
        updated = await transcript.update_item(
            item,
            theme=theme,
            show_tool_results=expanded,
            invocation=self.state.resolve_tool_invocation(item, expanded=expanded),
            result_markup=self.state.resolve_tool_result(item, expanded=expanded),
        )
        if append and not updated:
            await transcript.append_item(
                item,
                theme=theme,
                show_tool_results=expanded,
                invocation=self.state.resolve_tool_invocation(item, expanded=expanded),
            )

    async def _dom_compaction_start(self, event: CompactionStartEvent) -> None:
        await self._dom_transcript().finish_assistant_message()
        if event.reason in {"overflow", "threshold"}:
            await self._dom_append_latest_item()
        self._refresh_chrome()

    async def _dom_auto_retry_start(self, event: AutoRetryStartEvent) -> None:
        await self._dom_transcript().finish_assistant_message()
        await self._dom_append_latest_item()
        self._refresh_chrome()

    async def _dom_append_latest_item(self) -> None:
        """Mount the adapter's newest status row when there is one."""
        if self.state.items:
            await self._dom_transcript().append_item(
                self.state.items[-1],
                theme=self.tui_settings.resolved_theme,
                show_tool_results=self.state.show_tool_results,
            )

    async def _dom_compaction_end(self, event: CompactionEndEvent) -> None:
        if event.reason == "threshold" or (
            event.reason == "overflow" and (event.aborted or event.error_message)
        ):
            self._refresh()
        else:
            self._refresh_chrome()

    async def _dom_auto_retry_end(self, event: AutoRetryEndEvent) -> None:
        # The adapter settles the transient retry row; remount so it disappears.
        self._refresh()

    async def _dom_session_info_changed(self, event: SessionInfoChangedEvent) -> None:
        """A session rename has no transcript event; refresh the title-bearing chrome."""
        self._refresh_chrome()

    async def _dom_thinking_level_changed(self, event: ThinkingLevelChangedEvent) -> None:
        """A thinking-level change updates the sidebar/model chrome, not the transcript."""
        self._refresh_chrome()

    async def _dom_model_selected(self, event: ModelSelectEvent) -> None:
        """A model change updates the sidebar/model chrome, not the transcript."""
        self._refresh_chrome()

    async def _dom_refresh_chrome(self, event: CodingSessionEvent) -> None:
        self._refresh_chrome()

    def action_cancel(self) -> None:
        """Cancel the active compaction or agent turn."""
        if self._cancel_active_compaction(notify=True):
            return
        self._cancel_active_prompt(notify=True)

    def _cancel_active_compaction(self, *, notify: bool) -> bool:
        """Cancel the active manual compaction worker and restore visible session state."""
        worker = self._compaction_worker
        if worker is None or worker.is_finished or worker.is_cancelled:
            return False

        worker.cancel()
        self._compaction_run_id += 1
        self._compaction_worker = None
        self._compacting = False
        self.state.clear()
        self.state.set_skills(self.session.skills)
        self._load_session_messages_from_session()
        self._refresh()
        if notify:
            self._notify("Cancelled compaction.")
        return True

    def _cancel_active_prompt(self, *, notify: bool, interrupt: bool = False) -> None:
        """Cancel the active prompt worker and ignore any late events from it."""
        del interrupt
        worker = self._prompt_worker
        is_worker_active = worker is not None and not worker.is_cancelled
        is_session_running = bool(getattr(self.session, "is_running", False))
        if not (self.state.running or is_session_running or is_worker_active):
            return

        self._prompt_run_id += 1
        cancel = getattr(self.session, "cancel", None)
        if callable(cancel):
            cancel()
        if worker is not None and not worker.is_cancelled:
            worker.cancel()
        self._prompt_worker = None
        self.state.running = False
        self.state.compacting = False
        self.state.assistant_buffer = ""
        self._sync_text_selection_state()
        self._refresh()
        if notify:
            self._notify("Interrupted current operation.")

    def action_accept_completion(self) -> None:
        """Accept the currently selected prompt completion."""
        if isinstance(self.screen, ModelPickerScreen):
            self.screen.action_toggle_mode()
            return
        if isinstance(self.screen, ToolsReferenceScreen):
            self.screen.action_open_selected()
            return
        if isinstance(self.screen, SelectableListScreen):
            self.screen.action_select_cursor()
            return
        prompt = self.query_one("#prompt", PromptInput)
        item = self._completion_state.selected
        applied = self._apply_selected_completion(prompt.text)
        if applied is None or item is None:
            return
        cursor = item.cursor_after_apply()
        if item.kind is CompletionKind.FILE_REFERENCE and item.replacement.endswith("/"):
            # Commit a directory reference instead of drilling into it: leave
            # the @ token by moving past (or inserting) a separating space, so
            # accepting a directory does not immediately reopen the picker on
            # the directory's children.
            if cursor < len(applied) and applied[cursor].isspace():
                cursor += 1
            else:
                applied = f"{applied[:cursor]} {applied[cursor:]}"
                cursor += 1
        prompt.text = applied
        prompt.cursor_position = cursor
        self._completion_state = self._build_completion_state(prompt.text, cursor=cursor)
        self._refresh_completions()

    def action_completion_next(self) -> None:
        """Select the next prompt completion or move down in the active editor."""
        if isinstance(self.focused, TextArea) and self.focused.id == "sidebar-file-editor-input":
            self.focused.action_cursor_down()
            return
        if isinstance(self.screen, PromptTemplateEditorScreen):
            self.screen.query_one("#prompt-template-editor-input", TextArea).action_cursor_down()
            return
        if isinstance(self.screen, CommandOutputScreen):
            self.screen.action_scroll_down()
            return
        if isinstance(self.screen, CursorListScreen):
            self.screen.action_cursor_down()
            return
        if not self._completion_state.items:
            self.query_one("#prompt", PromptInput).action_cursor_down()
            return
        self._completion_state = self._completion_state.select_next()
        self._refresh_completions()

    def action_completion_previous(self) -> None:
        """Select the previous prompt completion or move up in the active editor."""
        if isinstance(self.focused, TextArea) and self.focused.id == "sidebar-file-editor-input":
            self.focused.action_cursor_up()
            return
        if isinstance(self.screen, PromptTemplateEditorScreen):
            self.screen.query_one("#prompt-template-editor-input", TextArea).action_cursor_up()
            return
        if isinstance(self.screen, CommandOutputScreen):
            self.screen.action_scroll_up()
            return
        if isinstance(self.screen, CursorListScreen):
            self.screen.action_cursor_up()
            return
        if not self._completion_state.items:
            if self.action_edit_queued_message():
                return
            if self.action_recall_previous_prompt():
                return
            self.query_one("#prompt", PromptInput).action_cursor_up()
            return
        self._completion_state = self._completion_state.select_previous()
        self._refresh_completions()

    def action_recall_previous_prompt(self) -> bool:
        """Recall the most recent submitted prompt into an empty prompt input."""
        prompt = self.query_one("#prompt", PromptInput)
        # Only recall into an empty input so an accidental Up press does not
        # erase a prompt the user is still writing.
        if prompt.text.strip() or not self._prompt_history:
            return False
        previous_prompt = self._prompt_history[-1]
        prompt.text = previous_prompt
        prompt.move_cursor(text_end_location(previous_prompt))
        self._completion_state = self._build_completion_state(prompt.text)
        self._refresh_completions()
        return True

    def action_edit_queued_message(self) -> bool:
        """Move the latest queued message back into the prompt for editing."""
        if not self.state.running:
            return False
        prompt = self.query_one("#prompt", PromptInput)
        if prompt.text.strip():
            return False

        message = self._pop_latest_queued_message()
        if not message:
            return False
        prompt.text = message
        prompt.move_cursor(text_end_location(message))
        self._sync_queue_state()
        self._completion_state = self._build_completion_state(prompt.text)
        self._refresh()
        return True

    def action_edit_queued_follow_up(self) -> bool:
        """Move the latest queued message back into the prompt for editing."""
        return self.action_edit_queued_message()

    def _pop_latest_queued_message(self) -> str | None:
        """Pop the latest queued follow-up or steering message from the session."""
        pop_follow_up = getattr(self.session, "pop_latest_follow_up_message", None)
        if callable(pop_follow_up):
            message = pop_follow_up()
            if isinstance(message, str) and message:
                return message

        pop_steering = getattr(self.session, "pop_latest_steering_message", None)
        if callable(pop_steering):
            message = pop_steering()
            if isinstance(message, str) and message:
                return message

        return None

    def action_open_command_palette(self) -> None:
        """Open the slash-command palette in the prompt."""
        prompt = self.query_one("#prompt", PromptInput)
        prompt.focus()
        prompt.text = "/"
        prompt.move_cursor((0, 1))
        self._completion_state = self._build_completion_state(prompt.text)
        self._refresh_completions()

    async def action_open_external_editor(self) -> None:
        """Edit the current prompt text in the user's external editor.

        Suspends the Textual app so the editor gets the real terminal, then
        writes the saved text back into the prompt on a clean exit. Leaves
        the prompt untouched on cancellation or failure.
        """
        if self._is_agent_or_queue_active():
            self._notify("Baldric is already working. Press Escape to cancel.")
            return
        prompt = self.query_one("#prompt", PromptInput)
        original_text = prompt.text
        was_read_only = prompt.read_only
        prompt.read_only = True
        try:
            result = await run_external_editor(
                self,
                original_text,
                settings_command=self.tui_settings.editor_command,
            )
        except EditorError as exc:
            self._notify(str(exc), severity="error")
            return
        finally:
            prompt.read_only = was_read_only
        if result.changed:
            prompt.load_text(result.text)
            end_location = text_end_location(result.text)
            prompt.cursor_position = end_location[1] if end_location else len(result.text)
            self._notify("Prompt updated in external editor")
        prompt.focus()

    def action_suspend_process(self) -> None:
        """Suspend Baldric with SIGTSTP (POSIX ``Ctrl+Z``)."""
        if sys.platform == "win32":
            return
        os.killpg(os.getpgrp(), signal.SIGTSTP)

    def _open_prompt_template_picker(self) -> None:
        self.push_screen(
            PromptTemplatePickerScreen(self.session.prompt_templates),
            callback=self._handle_prompt_template_picker_result,
        )

    def _handle_prompt_template_picker_result(self, result: PromptTemplatePickerResult | None) -> None:
        prompt = self.query_one("#prompt", PromptInput)
        prompt.focus()
        if result is None:
            return
        if result.action == "edit":
            try:
                source = result.template.path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                self._notify(f"Could not read /{result.template.name}: {exc}", severity="error")
                self._open_prompt_template_picker()
                return
            self.push_screen(
                PromptTemplateEditorScreen(result.template, source),
                callback=lambda edited: self._handle_prompt_template_edit(result.template, edited),
            )
            return
        invocation = f"/{result.template.name}"
        prompt.text = invocation
        prompt.move_cursor(text_end_location(invocation))
        self._completion_state = self._build_completion_state(invocation)
        self._refresh_completions()

    def _handle_prompt_template_edit(self, template: PromptTemplate, source: str | None) -> None:
        if source is None:
            self._open_prompt_template_picker()
            return
        self.run_worker(self._save_prompt_template_edit(template, source), exclusive=False)

    async def _save_prompt_template_edit(self, template: PromptTemplate, source: str) -> None:
        try:
            template.path.write_text(source, encoding="utf-8")
        except OSError as exc:
            self._notify(f"Could not save /{template.name}: {exc}", severity="error")
            self._open_prompt_template_picker()
            return

        try:
            reload_result = self.session.reload()
            if isawaitable(reload_result):
                await reload_result
        except Exception as exc:  # saved file remains valid; surface reload errors
            self._notify(
                f"Saved /{template.name}, but could not reload resources: {exc}",
                severity="error",
            )
        else:
            self.state.set_skills(self.session.skills)
            self._completion_state = self._build_completion_state("")
            self._refresh()
            self._notify(f"Saved /{template.name} and reloaded resources.")
        self._open_prompt_template_picker()

    def action_cycle_thinking(self) -> None:
        """Cycle the active thinking mode."""
        preview = getattr(self.session, "preview_cycle_thinking_level", None)
        if preview is not None:
            try:
                preview()
            except Exception as exc:  # report invalid selections
                self._notify(f"Could not change thinking mode: {exc}", severity="error")
                return
            self._refresh_chrome()
            return
        self.run_worker(self._cycle_thinking_level(), exclusive=False)

    def action_cycle_model(self) -> None:
        """Cycle forward through scoped models."""
        self._cycle_model(reverse=False)

    def action_cycle_model_reverse(self) -> None:
        """Cycle backward through scoped models."""
        self._cycle_model(reverse=True)

    def _cycle_model(self, *, reverse: bool) -> None:
        if self.state.running:
            self._notify("Baldric is already working. Press Escape to cancel.")
            return
        preview = getattr(self.session, "preview_cycle_scoped_model", None)
        if preview is not None:
            try:
                preview(reverse=reverse)
            except Exception as exc:  # report invalid selections
                self._notify(f"Could not switch scoped model: {exc}", severity="error")
                return
            self._refresh_chrome()
            return
        self.run_worker(self._cycle_scoped_model(reverse=reverse), exclusive=False)

    def action_toggle_tool_results(self) -> None:
        """Toggle inline tool result details without rebuilding unrelated history."""
        self.state.toggle_tool_results()
        self.run_worker(self._update_tool_results_visibility(), exclusive=False)

    async def _update_tool_results_visibility(self) -> None:
        transcript = self.query_one("#transcript", TranscriptView)
        await transcript.update_tool_results_visibility(
            self.state,
            theme=self.tui_settings.resolved_theme,
        )

    def action_toggle_thinking(self) -> None:
        """Toggle thinking-token display in the transcript."""
        self.state.toggle_thinking()
        transcript = self.query_one("#transcript", TranscriptView)
        transcript.update_thinking_visibility(
            self.state,
            theme=self.tui_settings.resolved_theme,
        )

    def action_toggle_sidebar(self) -> None:
        """Show or hide the sidebar for this session (D6: collapsed by default)."""
        self._toggle_sidebar_visibility()

    async def _archive_session_record(
        self, record: SessionCompletionRecord, picker: SessionPickerScreen
    ) -> None:
        """Persist a session archive and update the open picker."""
        manager = self.session.session_manager
        archive = getattr(manager, "archive_session", None)
        if not callable(archive):
            self._notify("This session manager does not support archiving.", severity="warning")
            return
        try:
            archived = await asyncio.to_thread(archive, record.id)
        except Exception as exc:  # surface filesystem failures in the TUI
            self._notify(f"Could not archive session: {exc}", severity="error")
            return
        if archived:
            await picker._remove_records(record.cwd, record.id)
            self._notify(f"Archived session: {record.id}")

    async def _archive_session_project(self, cwd: Path, picker: SessionPickerScreen) -> None:
        """Persist a project archive and update the open picker."""
        manager = self.session.session_manager
        archive = getattr(manager, "archive_project", None)
        if not callable(archive):
            self._notify("This session manager does not support archiving.", severity="warning")
            return
        try:
            archived = await asyncio.to_thread(archive, cwd)
        except Exception as exc:  # surface filesystem failures in the TUI
            self._notify(f"Could not archive project: {exc}", severity="error")
            return
        if archived:
            await picker._remove_records(cwd)
            self._notify(f"Archived project: {short_path(Path(cwd))}")

    async def _unarchive_session_record(
        self, record: SessionCompletionRecord, picker: SessionPickerScreen
    ) -> None:
        """Persist a session restore and update the open picker."""
        manager = self.session.session_manager
        unarchive = getattr(manager, "unarchive_session", None)
        if not callable(unarchive):
            self._notify("This session manager does not support restoring.", severity="warning")
            return
        try:
            restored = await asyncio.to_thread(unarchive, record.id)
        except Exception as exc:  # surface filesystem failures in the TUI
            self._notify(f"Could not restore session: {exc}", severity="error")
            return
        if restored:
            await picker._restore_records(record.cwd, record.id)
            self._notify(f"Restored session: {record.id}")

    async def _unarchive_session_project(self, cwd: Path, picker: SessionPickerScreen) -> None:
        """Persist a project restore and update the open picker."""
        manager = self.session.session_manager
        unarchive = getattr(manager, "unarchive_project", None)
        if not callable(unarchive):
            self._notify("This session manager does not support restoring.", severity="warning")
            return
        try:
            restored = await asyncio.to_thread(unarchive, cwd)
        except Exception as exc:  # surface filesystem failures in the TUI
            self._notify(f"Could not restore project: {exc}", severity="error")
            return
        if restored:
            await picker._restore_records(cwd)
            self._notify(f"Restored project: {short_path(Path(cwd))}")

    async def _resume_session(self, session_id: str) -> None:
        try:
            previous_cwd = Path(self.session.cwd).resolve()
            resume_message = await self.session.resume(session_id)
            self._reload_session_themes()
            self.state.clear()
            self.state.set_skills(self.session.skills)
            self._load_session_messages_from_session()
            current_cwd = Path(self.session.cwd).resolve()
            if current_cwd != previous_cwd:
                resume_message = f"{resume_message} ({short_path(current_cwd)})"
            self._notify(resume_message)
        except Exception as exc:  # surface command failures in the TUI
            self._notify(f"Error: {exc}", severity="error")
        self._refresh()

    async def _set_tree_label(self, entry_id: str, label: str | None) -> float:
        set_label = getattr(self.session, "set_label", None)
        if set_label is None:
            raise RuntimeError("Session labels are not available.")
        entry = set_label(entry_id, label)
        if isawaitable(entry):
            entry = await entry
        self._notify("Label cleared." if label is None else f"Label set to [{label}].")
        return float(entry.timestamp)

    async def _branch_to_tree_entry(
        self,
        entry_id: str,
        *,
        summarize: bool,
        custom_instructions: str | None = None,
    ) -> None:
        if self._is_agent_or_queue_active():
            self._notify(TREE_RUNNING_MESSAGE, severity="warning")
            return
        branch_to_entry = getattr(self.session, "branch_to_entry", None)
        if branch_to_entry is None:
            self._notify("Session tree is not available.", severity="warning")
            return
        try:
            if summarize:
                self.state.clear()
                self.state.add_item("status", "Summarizing branch…")
                self._refresh()

            result = branch_to_entry(
                entry_id,
                summarize=summarize,
                custom_instructions=custom_instructions,
            )
            if isawaitable(result):
                result = await result
            self.state.clear()
            self.state.set_skills(self.session.skills)
            self._load_session_messages_from_session()
            if isinstance(result, SessionTreeBranchResult):
                if result.input_prefill is not None:
                    prompt = self.query_one("#prompt", PromptInput)
                    prompt.value = result.input_prefill
                    prompt.move_cursor(text_end_location(result.input_prefill))
                    prompt.focus()
                self._notify(result.message)
            elif isinstance(result, str):
                self._notify(result)
        except Exception as exc:  # surface command failures in the TUI
            self._notify(f"Error: {exc}", severity="error")
        self._refresh()

    async def _new_session(self) -> None:
        self._cancel_active_prompt(notify=False, interrupt=True)
        new_session = getattr(self.session, "new_session", None)
        if new_session is None:
            self._notify("Session manager is not available.")
            return
        try:
            await new_session()
            self._reload_session_themes()
            self.state.clear()
            self.state.set_skills(self.session.skills)
            self._load_session_messages_from_session()
        except Exception as exc:  # surface command failures in the TUI
            self._notify(f"Error: {exc}", severity="error")
        self._refresh()

    def _apply_selected_completion(self, value: str) -> str | None:
        item = self._completion_state.selected
        if item is None:
            return None
        return item.apply(value)

    def _append_command_message(
        self,
        command_text: str,
        message: str,
        *,
        system_prompt_inspection: SystemPromptInspection | None = None,
    ) -> None:
        """Append non-persistent command output to the visible transcript."""
        is_system_prompt = command_text.split(maxsplit=1)[0].casefold() == "/system"
        separator = "\n\n" if is_system_prompt else "\n"
        title = _command_output_title(command_text)
        if is_system_prompt:
            title = f"### {title}"
        self.state.add_item(
            "status",
            f"{title}{separator}{message}",
            system_prompt=is_system_prompt,
            system_prompt_sources=(
                system_prompt_inspection.sources if system_prompt_inspection is not None else None
            ),
        )

    def _show_command_message(self, command_text: str, message: str) -> None:
        self.push_screen(
            CommandOutputScreen(
                _command_output_title(command_text),
                message,
                theme=self.tui_settings.resolved_theme,
                auto_copy_selection=command_text.strip().split(maxsplit=1)[0] == "/session",
            )
        )

    def _open_custom_provider_login(self) -> None:
        self.push_screen(
            CustomProviderLoginScreen(theme=self.tui_settings.resolved_theme),
            callback=self._handle_custom_provider_login_result,
        )

    def _handle_custom_provider_login_result(
        self,
        result: CustomProviderLoginResult | _LoginFlowAction | None,
    ) -> None:
        if result is _LoginFlowAction.BACK:
            self._open_login_picker()
            return
        if result is None:
            return
        provider = OpenAICompatibleProviderConfig(
            name=result.provider_name,
            base_url=result.base_url.rstrip("/"),
            api_key_env=result.api_key_env,
            credential_name=result.provider_name,
            models=result.models,
            default_model=result.default_model,
        )
        catalog_entry = ProviderCatalogEntry(
            name=provider.name,
            display_name=result.display_name,
            kind="openai-compatible",
            base_url=provider.base_url,
            api_key_env=provider.api_key_env,
            credential_name=provider.credential_name,
            models=provider.models,
            default_model=provider.default_model,
            docs_url=provider.base_url,
        )
        try:
            save_user_catalog_entries((catalog_entry,))
            FileCredentialStore().set(provider.credential_name or provider.name, result.api_key)
            settings = load_provider_settings()
            updated = upsert_openai_compatible_provider(settings, provider, set_default=False)
            save_provider_settings(updated)
            self.session.reload_provider_settings()
            try:
                self.session.set_provider(provider.name, persist_default=False)
            except TypeError:
                self.session.set_provider(provider.name)
        except Exception as exc:  # surface login failures in the TUI
            self._notify(f"Could not save custom provider: {exc}", severity="error")
            return
        self._notify(f"Saved custom provider {result.display_name}.")
        self._refresh()

    def _handle_api_key_login_navigation_result(
        self,
        entry: ProviderCatalogEntry,
        result: str | _LoginFlowAction | None,
    ) -> None:
        if result is _LoginFlowAction.BACK:
            self._open_login_picker()
        else:
            self._handle_login_result(entry, result)

    def _handle_oauth_login_navigation_result(
        self,
        entry: ProviderCatalogEntry,
        result: OAuthCredential | _LoginFlowAction | None,
    ) -> None:
        if result is _LoginFlowAction.BACK:
            self._open_login_picker()
        else:
            self._handle_oauth_login_result(entry, result)

    def _handle_oauth_login_result(
        self,
        entry: ProviderCatalogEntry,
        credential: OAuthCredential | None,
    ) -> None:
        if credential is None:
            return
        if entry.credential_name is None:
            self._notify(
                f"Provider {entry.name} does not support saved credentials.",
                severity="error",
            )
            return
        try:
            FileCredentialStore().set_oauth(entry.credential_name, credential)
            provider = provider_config_from_catalog_entry(entry.name)
            upsert_saved_provider(provider, set_default=False)
            self.session.reload_provider_settings()
            try:
                self.session.set_provider(entry.name, persist_default=False)
            except TypeError:
                self.session.set_provider(entry.name)
        except Exception as exc:  # surface login failures in the TUI
            self._notify(f"Could not save login: {exc}", severity="error")
            return
        self._notify(f"Saved login for {entry.display_name}.")
        self._refresh()

    def _logout(self, provider_name: str) -> None:
        entry = builtin_provider_entry(provider_name)
        if entry is None:
            self._notify(f"Unknown provider: {provider_name}", severity="error")
            return

        if entry.credential_name is None:
            self._notify(NO_STORED_CREDENTIALS_MESSAGE, severity="warning")
            return
        credential_store = FileCredentialStore()
        if not credential_store_has_entry(credential_store, entry.credential_name):
            self._notify(NO_STORED_CREDENTIALS_MESSAGE, severity="warning")
            return

        try:
            credential_store.delete(entry.credential_name)
            self.session.reload_provider_settings()
        except Exception as exc:  # surface logout failures in the TUI
            self._notify(f"Could not log out: {exc}", severity="error")
            return

        if entry.kind == "openai-codex":
            self._notify(f"Logged out of {entry.display_name}.")
        else:
            self._notify(
                f"Removed stored API key for {entry.display_name}. "
                "Environment variables and providers.json config are unchanged."
            )
        self._refresh()

    def _available_model_choices(self) -> tuple[ModelChoice, ...]:
        fallback_choices = (
            ModelChoice(provider_name=self.session.provider_name, model=model)
            for model in self.session.available_models
        )
        return tuple(
            getattr(
                self.session,
                "available_model_choices",
                fallback_choices,
            )
        )

    def _open_local_backend_picker(self) -> None:
        """Open the generic local-backend chooser and require confirmation."""
        runtime = getattr(self.session, "extension_runtime", None)
        registry = getattr(runtime, "local_backend_registry", None)
        if registry is None:
            self._notify("Local backend controls are unavailable.", severity="warning")
            return
        self.push_screen(
            LocalBackendPickerScreen(registry, theme=self.tui_settings.resolved_theme),
            callback=self._handle_local_backend_picker_result,
        )

    def _handle_local_backend_picker_result(self, backend_id: str | None) -> None:
        # Screen.dismiss() invokes its result callback before popping the screen.
        # Defer the transition so the picker cannot pop the backend screen that
        # this callback opens.
        self.call_later(self._finish_local_backend_picker, backend_id)

    def _finish_local_backend_picker(self, backend_id: str | None) -> None:
        self._restore_prompt_focus()
        if backend_id is None:
            return
        runtime = getattr(self.session, "extension_runtime", None)
        registry = getattr(runtime, "local_backend_registry", None)
        if registry is None or registry.effective(backend_id) is None:
            self._notify("The selected local backend is no longer available.", severity="warning")
            return
        self.push_screen(
            LocalBackendScreen(
                registry,
                backend_id,
                theme=self.tui_settings.resolved_theme,
                on_use=self._use_local_model,
                notify_callback=self._notify_local_backend,
                is_idle=lambda: not self._is_agent_or_queue_active(),
            )
        )

    def _restore_prompt_focus(self) -> None:
        with suppress(NoMatches):
            self.query_one("#prompt", PromptInput).focus()

    def _notify_local_backend(self, message: str, level: str) -> None:
        severity: Literal["information", "warning", "error"] = {
            "info": "information",
            "warning": "warning",
            "error": "error",
        }.get(level, "information")  # type: ignore[assignment]
        self._notify(message, severity=severity)

    async def _use_local_model(self, provider_id: str, model_id: str) -> None:
        if self._is_agent_or_queue_active():
            self._notify(
                "Baldric is still working. Press Escape to interrupt before switching models.",
                severity="warning",
            )
            return
        await self._switch_model(ModelChoice(provider_name=provider_id, model=model_id))

    def _open_tools_reference(self) -> None:
        """Open a read-only view of tools from the active session."""
        self.push_screen(
            ToolsReferenceScreen(
                self.session.tools,
                extension_sources=self.session.extension_tool_sources,
                theme=self.tui_settings.resolved_theme,
            )
        )

    def _toggle_scoped_model(self, choice: ModelChoice) -> Sequence[ModelChoice]:
        toggle_scoped_model = getattr(self.session, "toggle_scoped_model", None)
        if toggle_scoped_model is None:
            self._notify("Scoped model controls are not available.", severity="warning")
            return tuple(getattr(self.session, "scoped_model_choices", ()))
        try:
            return tuple(toggle_scoped_model(choice))
        except Exception as exc:  # surface session state failures in the TUI
            self._notify(f"Could not update scoped models: {exc}", severity="error")
            return tuple(getattr(self.session, "scoped_model_choices", ()))

    def _start_selected_model_switch(self, choice: ModelChoice) -> None:
        self.run_worker(self._switch_model(choice), exclusive=False)

    async def _switch_model(self, choice: ModelChoice) -> None:
        try:
            select = getattr(self.session, "preview_model_choice", None)
            if select is None:
                select = getattr(self.session, "select_provider_model", None)
            if select is not None:
                result = select(choice)
                if isawaitable(result):
                    await result
            else:
                set_model_choice = getattr(self.session, "set_model_choice", None)
                if set_model_choice is None:
                    if choice.provider_name != self.session.provider_name:
                        self.session.set_provider(choice.provider_name)
                    self.session.set_model(choice.model)
                else:
                    set_model_choice(choice)
        except Exception as exc:  # surface model switch failures in the TUI
            self._notify(f"Could not switch model: {exc}", severity="error")
            return
        self._refresh_chrome()

    async def _set_thinking_level(self, level: str) -> None:
        setter = getattr(self.session, "preview_thinking_level", None)
        if setter is None:
            setter = getattr(self.session, "set_thinking_level", None)
        if setter is None:
            self._notify("Thinking controls are not available.", severity="warning")
            return
        try:
            result = setter(level)
            if isawaitable(result):
                await result
        except Exception as exc:  # surface session state failures in the TUI
            self._notify(f"Could not change thinking mode: {exc}", severity="error")
            return
        self._refresh_chrome()

    async def _cycle_thinking_level(self) -> None:
        cycler = getattr(self.session, "cycle_thinking_level", None)
        if cycler is None:
            self._notify("Thinking controls are not available.", severity="warning")
            return
        try:
            result = cycler()
            if isawaitable(result):
                await result
        except Exception as exc:  # surface session state failures in the TUI
            self._notify(f"Could not change thinking mode: {exc}", severity="error")
            return
        self._refresh_chrome()

    async def _cycle_scoped_model(self, *, reverse: bool = False) -> None:
        cycler = getattr(self.session, "cycle_scoped_model", None)
        if cycler is None:
            self._notify("Scoped model controls are not available.", severity="warning")
            return
        try:
            result = cycler(reverse=reverse)
            if isawaitable(result):
                result = await result
        except Exception as exc:  # surface session state failures in the TUI
            self._notify(f"Could not switch scoped model: {exc}", severity="error")
            return
        self._refresh_chrome()

    def _notify(
        self,
        message: str,
        *,
        severity: Literal["information", "warning", "error"] = "information",
    ) -> None:
        key = (message, severity)
        if key in self._active_notification_keys:
            return
        self._active_notification_keys.add(key)
        self.set_timer(
            self.NOTIFICATION_TIMEOUT,
            lambda: self._active_notification_keys.discard(key),
            name=f"notification-dedupe-{hash(key)}",
        )
        self.notify(message, severity=severity, markup=False)

    def _refresh(self) -> None:
        theme = self.tui_settings.resolved_theme
        self._refresh_chrome(theme=theme)
        transcript = self.query_one("#transcript", TranscriptView)
        transcript.update_from_state(self.state, theme=theme)

    def _refresh_chrome(self, *, theme: TuiTheme | None = None) -> None:
        """Refresh non-transcript chrome without remounting transcript blocks."""
        theme = theme or self.tui_settings.resolved_theme
        self._sync_session_title()
        self._sync_text_selection_state()
        self._sync_queue_state()
        sidebar = self.query_one("#sidebar", SessionSidebar)
        sidebar.update_from_session(self.session, theme=theme)
        if self._extension_sidebar_theme != theme:
            self._rebuild_extension_sidebar_sections(theme=theme)
        compact_info = self.query_one("#compact-session-info", CompactSessionInfo)
        compact_info.update_from_session(self.session, theme=theme)
        queued_messages = self.query_one("#queued-messages", Static)
        queue_render_key = (
            self.state.queued_steering,
            self.state.queued_follow_up,
            theme.name,
            theme.muted_text,
        )
        if queue_render_key != self._last_queue_render_key:
            self._last_queue_render_key = queue_render_key
            queued_messages.display = self.state.queued_message_count > 0
            queued_messages.update(_render_queued_messages(self.state, theme=theme))
        self._sync_activity_indicator()
        self._refresh_footer_bindings()

    def _sync_queue_state(self) -> None:
        queue_event = getattr(self.session, "queue_update_event", None)
        if not callable(queue_event):
            return
        self.adapter.apply(queue_event())

    def _refresh_chrome_if_mounted(self) -> None:
        """Refresh chrome when the app is mounted, ignoring teardown races."""
        if not self.screen_stack:
            return
        with suppress(NoMatches):
            self._refresh_chrome()

    def _sync_activity_indicator(self) -> None:
        self._sync_terminal_title()
        if self._is_working():
            if self._activity_timer is None:
                self._activity_timer = self.set_interval(
                    activity.ACTIVITY_TICK_SECONDS,
                    self._tick_activity,
                    name="activity-indicator",
                )
            else:
                self._activity_timer.resume()
            self._apply_activity_indicator()
            return
        self._activity_frame = 0
        if self._activity_timer is not None:
            self._activity_timer.pause()
        self._apply_activity_indicator()

    def _tick_activity(self) -> None:
        if not self._is_working():
            return
        self._activity_frame += 1
        self._apply_activity_indicator()
        self._sync_terminal_title()
        now = asyncio.get_running_loop().time()
        if now - self._last_tool_timer_refresh_at >= 1.0:
            self._last_tool_timer_refresh_at = now
            self.call_later(self._refresh_pending_tool_timer)

    async def _refresh_pending_tool_timer(self) -> None:
        """Refresh elapsed time on the tool row that is currently executing."""
        if not self.state.running:
            return
        item = next(
            (
                candidate
                for candidate in reversed(self.state.items)
                if candidate.role == "tool" and candidate.tool_result_text is None
            ),
            None,
        )
        if item is None:
            return
        try:
            transcript = self.query_one("#transcript", TranscriptView)
        except NoMatches:
            return
        expanded = self.state.show_tool_results or item.always_show_tool_result
        await transcript.update_item(
            item,
            theme=self.tui_settings.resolved_theme,
            show_tool_results=expanded,
            invocation=self.state.resolve_tool_invocation(item, expanded=expanded),
            result_markup=self.state.resolve_tool_result(item, expanded=expanded),
        )

    def _apply_activity_indicator(self) -> None:
        theme = self.tui_settings.resolved_theme
        try:
            prompt = self.query_one("#prompt", PromptInput)
            prompt_prefix = self.query_one("#prompt-prefix", Static)
        except NoMatches:
            return
        shell_mode = _is_terminal_command_prompt(prompt.text)
        border_color = _activity_prompt_border_color(
            theme,
            frame=self._activity_frame,
            running=self._is_working(),
            shell_mode=shell_mode,
            thinking_level=getattr(self.session, "thinking_level", None),
        )
        render_key = (
            theme.name,
            theme.accent,
            theme.screen_background,
            border_color,
            self._activity_frame,
            self._is_working(),
            shell_mode,
        )
        if render_key == self._last_activity_indicator_key:
            return
        self._last_activity_indicator_key = render_key
        prompt.styles.border_top = ("solid", border_color)
        prompt.styles.border_bottom = ("solid", border_color)
        prompt_prefix.update(
            _render_activity_indicator(
                theme,
                frame=self._activity_frame,
                running=self._is_working(),
                shell_mode=shell_mode,
            ),
            layout=False,
        )

    def _refresh_completions(self) -> None:
        suggestions = self.query_one("#autocomplete", Static)
        suggestions.display = bool(self._completion_state.items)
        if not self._completion_state.items:
            self._completion_visible_line_budget = None
            suggestions.update(
                render_completion_suggestions(
                    CompletionState(),
                    theme=self.tui_settings.resolved_theme,
                )
            )
            self._refresh_footer_bindings()
            return
        max_lines = self._completion_window_line_budget(suggestions)
        suggestions.update(
            render_completion_suggestions(
                _visible_completion_state(
                    self._completion_state,
                    max_lines=max_lines,
                    width=max(suggestions.content_size.width or suggestions.size.width, 1),
                ),
                theme=self.tui_settings.resolved_theme,
            )
        )
        self._refresh_footer_bindings()

    def _completion_window_line_budget(self, suggestions: Static) -> int:
        """Return a stable completion window size for the current suggestion box.

        The autocomplete widget has ``height: auto``. If we used its current
        rendered height as the next render limit unconditionally, selecting an
        item could render fewer rows, which would shrink the widget, which would
        then make the next render limit smaller again. Keep the largest measured
        height for the current completion session so navigation does not feed
        back into progressively smaller boxes.
        """
        measured_limit = _completion_visible_line_limit(suggestions)
        if suggestions.size.height <= 0:
            if self._completion_visible_line_budget is None:
                self._completion_visible_line_budget = self._initial_completion_line_budget()
            return self._completion_visible_line_budget
        self._completion_visible_line_budget = max(
            self._completion_visible_line_budget or measured_limit,
            measured_limit,
        )
        return self._completion_visible_line_budget

    def _initial_completion_line_budget(self) -> int:
        """Estimate the first completion window size before Textual lays it out."""
        terminal_height = self.size.height
        if terminal_height <= 0:
            return COMPLETION_MAX_VISIBLE_LINES

        reserved_rows = COMPLETION_MIN_TRANSCRIPT_LINES + COMPLETION_WIDGET_CHROME_LINES
        for selector in ("#prompt-row", "#compact-session-info", "#queued-messages"):
            with suppress(NoMatches):
                widget = self.query_one(selector)
                if widget.display:
                    reserved_rows += widget.outer_size.height

        available_rows = terminal_height - reserved_rows
        terminal_fraction_rows = max(1, terminal_height // COMPLETION_INITIAL_TERMINAL_FRACTION)
        return max(
            1,
            min(COMPLETION_MAX_VISIBLE_LINES, available_rows, terminal_fraction_rows),
        )

    def _update_responsive_layout(self, width: int, height: int) -> None:
        # D6: the sidebar starts collapsed on every window size; Ctrl+B or
        # /sidebar shows it for this session only (spec 2026-11-08 §5.5).
        show_sidebar = self._sidebar_visibility_override is True
        self.set_class(not show_sidebar, "-hide-sidebar")

    def _build_completion_state(self, text: str, *, cursor: int | None = None) -> CompletionState:
        registry = _session_command_registry(self.session)
        return build_completion_state(
            text,
            cursor=cursor,
            command_registry=registry,
            skills=self.session.skills,
            prompt_templates=self.session.prompt_templates,
            model_names=self.session.available_models,
            provider_names=(
                *self.session.available_providers,
                *LOGIN_PROVIDER_ALIASES,
            ),
            thinking_levels=getattr(self.session, "available_thinking_levels", ()),
            theme_names=available_tui_theme_names(),
            session_options=(session_options(self.session) if text.startswith("/resume ") else ()),
            cwd=self.session.cwd,
        )

    def _refresh_footer_bindings(self) -> None:
        prompt = self.query_one("#prompt", PromptInput)
        prompt.set_footer_mode(_prompt_footer_mode(self._completion_state, working=self._is_working()))

    def _sync_prompt_shell_mode(self, text: str) -> None:
        prompt = self.query_one("#prompt", PromptInput)
        prompt.shell_mode_style = self.tui_settings.resolved_theme.role_styles["tool"].border
        prompt.set_class(_is_terminal_command_prompt(text), "-shell-mode")
        prompt.refresh()
        self._apply_activity_indicator()


def _activity_prompt_border_color(
    theme: TuiTheme,
    *,
    frame: int,
    running: bool,
    shell_mode: bool,
    thinking_level: str | None = None,
) -> str:
    """Return the prompt border color for the current activity animation frame."""
    del frame, running
    return activity.thinking_prompt_border_color(theme, thinking_level, shell_mode=shell_mode)


def _is_terminal_command_prompt(text: str) -> bool:
    """Return whether the prompt is currently in terminal-command mode."""
    return _terminal_command_prefix_span(text) is not None


def _should_optimistically_render_prompt(text: str) -> bool:
    """Return whether submitted text can be safely shown before session expansion."""
    stripped = text.strip()
    return bool(stripped) and not stripped.startswith("/")


def _is_user_message_end_event(event: CodingSessionEvent) -> bool:
    """Return whether an agent event closes a user-context message."""
    return isinstance(event, MessageEndEvent) and isinstance(event.message, (UserMessage, CustomMessage))


def _completion_visible_line_limit(suggestions: Static) -> int:
    """Return the number of completion render lines that fit in the widget body."""
    if suggestions.size.height > 0:
        return max(min(COMPLETION_MAX_VISIBLE_LINES, suggestions.size.height), 1)
    return COMPLETION_MAX_VISIBLE_LINES


def _visible_completion_state(
    state: CompletionState,
    *,
    max_lines: int,
    width: int | None = None,
) -> CompletionState:
    """Return a completion-state window with the selected item visible."""
    if not state.items or max_lines <= 0:
        return CompletionState()

    selected_line_limit = max(max_lines - 1, 1)
    start = 0
    while start < state.selected_index:
        candidate = CompletionState(
            items=state.items[start:],
            selected_index=state.selected_index - start,
        )
        if _completion_selected_render_line(candidate, width=width) < selected_line_limit:
            break
        start += 1

    end = len(state.items)
    while end > state.selected_index + 1:
        candidate = CompletionState(
            items=state.items[start:end],
            selected_index=state.selected_index - start,
        )
        if _completion_render_line_count(candidate, width=width) <= max_lines:
            break
        end -= 1

    while start < state.selected_index:
        candidate = CompletionState(
            items=state.items[start:end],
            selected_index=state.selected_index - start,
        )
        if _completion_render_line_count(candidate, width=width) <= max_lines:
            break
        start += 1

    return CompletionState(
        items=state.items[start:end],
        selected_index=state.selected_index - start,
    )


def _completion_selected_render_line(state: CompletionState, *, width: int | None = None) -> int:
    """Return the rendered line number for the selected completion item."""
    line = 0
    has_rendered_text = False
    previous_category: str | None = None
    for index, item in enumerate(state.items):
        if item.category != previous_category:
            if has_rendered_text:
                line += 1
            if item.category:
                line += 1
                has_rendered_text = True
            previous_category = item.category
        elif has_rendered_text:
            line += 1
        if index == state.selected_index:
            return line
        line += _completion_item_extra_wrapped_lines(item, width=width)
        has_rendered_text = True
    return line


def _completion_render_line_count(state: CompletionState, *, width: int | None = None) -> int:
    """Return how many lines the completion state renders into."""
    if not state.items:
        return 0
    line_count = 0
    previous_category: str | None = None
    for index, item in enumerate(state.items):
        if item.category != previous_category:
            if index:
                line_count += 1
            if item.category:
                line_count += 1
            previous_category = item.category
        line_count += 1 + _completion_item_extra_wrapped_lines(item, width=width)
    return line_count


def _completion_item_extra_wrapped_lines(
    item: CompletionItem,
    *,
    width: int | None,
) -> int:
    """Return extra rendered lines used when a completion description wraps."""
    if width is None or width <= 0 or not item.description:
        return 0
    output = StringIO()
    console = Console(
        file=output,
        width=width,
        force_terminal=False,
        color_system=None,
        legacy_windows=False,
    )
    console.print(
        render_completion_suggestions(
            CompletionState(items=(item,), selected_index=0),
            theme=BALDRIC_DARK_THEME,
        ),
        end="",
    )
    line_count = len(output.getvalue().splitlines())
    return max(line_count - 1, 0)


def _session_command_registry(session: CodingSession) -> CommandRegistry:
    registry = getattr(session, "command_registry", None)
    if isinstance(registry, CommandRegistry):
        return registry
    return create_default_command_registry()


async def _run_in_daemon_thread[T](function: Callable[[], T]) -> T:
    """Run blocking work in a daemon thread so quitting never waits for it.

    `asyncio.to_thread` would make interpreter shutdown join the worker,
    holding an early quit until a slow network request times out.
    """
    loop = asyncio.get_running_loop()
    future: asyncio.Future[T] = loop.create_future()

    def resolve(result: T | None, error: BaseException | None) -> None:
        if future.done():
            return
        if error is not None:
            future.set_exception(error)
        else:
            future.set_result(cast(T, result))

    def run() -> None:
        result: T | None = None
        error: BaseException | None = None
        try:
            result = function()
        except BaseException as exc:  # re-raised in the awaiting task
            error = exc
        with suppress(RuntimeError):  # the event loop closed while this ran
            loop.call_soon_threadsafe(resolve, result, error)

    threading.Thread(target=run, name="baldric-background-check", daemon=True).start()
    return await future


def _command_output_title(command_text: str) -> str:
    command_name = command_text.split(maxsplit=1)[0].removeprefix("/")
    return f"/{command_name or 'help'}"


def _render_queued_messages(state: TuiState, *, theme: TuiTheme) -> Group:
    """Render queued prompts stacked above the prompt input."""
    rows: list[Text] = []
    for message in state.queued_steering:
        row = Text("↪ steering · queued: ", style=theme.muted_text)
        row.append(_queued_message_preview(message), style=theme.prompt_text)
        rows.append(row)
    for message in state.queued_follow_up:
        row = Text("↳ follow-up · queued: ", style=theme.muted_text)
        row.append(_queued_message_preview(message), style=theme.prompt_text)
        rows.append(row)
    return Group(*rows)


def _queued_message_preview(message: str) -> str:
    """Return the single-line preview shown above the prompt."""
    lines = message.splitlines()
    return lines[0] if lines else ""


def _prompt_footer_mode(
    completion_state: CompletionState,
    *,
    working: bool,
) -> Literal["normal", "completion", "file_completion", "running"]:
    selected = completion_state.selected
    if selected is not None:
        if selected.kind is CompletionKind.FILE_REFERENCE:
            return "file_completion"
        return "completion"
    if working:
        return "running"
    return "normal"


def _app_bindings(keybindings: TuiKeybindings) -> list[Binding]:
    return [
        Binding(keybindings.cancel, "cancel", "Cancel"),
        Binding(keybindings.command_palette, "open_command_palette", "Commands"),
        Binding(keybindings.session_picker, "open_session_picker", "Sessions"),
        Binding(keybindings.thinking_cycle, "cycle_thinking", "Thinking"),
        Binding(keybindings.model_cycle, "cycle_model", "Model"),
        Binding(
            keybindings.model_cycle_reverse,
            "cycle_model_reverse",
            "Previous model",
            show=False,
        ),
        Binding(
            keybindings.accept_completion,
            "accept_completion",
            "Complete",
            priority=True,
        ),
        Binding(
            keybindings.queue_follow_up,
            "submit_follow_up",
            "Follow-up",
            priority=True,
        ),
        Binding(
            keybindings.completion_next,
            "completion_next",
            "Next completion",
            priority=True,
        ),
        Binding(
            keybindings.completion_previous,
            "completion_previous",
            "Previous completion",
            priority=True,
        ),
        Binding(keybindings.toggle_tool_results, "toggle_tool_results", "Tool results"),
        Binding(keybindings.toggle_thinking, "toggle_thinking", "Thinking tokens"),
        Binding(keybindings.toggle_sidebar, "toggle_sidebar", "Sidebar"),
        Binding(keybindings.copy_message, "clear_prompt", "Copy/Clear"),
        Binding(keybindings.quit, "quit", "Quit"),
    ]


def _format_prompt_error(exc: BaseException, session: CodingSession) -> str:
    detail = str(exc) or type(exc).__name__
    message = f"Error: {detail}"
    log_path = getattr(session, "last_diagnostic_log_path", None)
    if isinstance(log_path, Path):
        return f"{message}\nLog: {log_path}"
    return message


def _explicit_resume_record(
    manager: SessionManager,
    *,
    session_id: str | None,
) -> CodingSessionRecord | None:
    if session_id is None:
        return None
    record = manager.get_session(session_id)
    if record is None:
        raise RuntimeError(f"Unknown session: {session_id}")
    return record


def _create_startup_session_record(
    manager: SessionManager,
    *,
    cwd: Path,
    selection: ProviderSelection,
    inference_provider: str | None = None,
) -> CodingSessionRecord:
    if inference_provider is None:
        return manager.prepare_session(
            cwd=cwd,
            model=selection.model,
            provider_name=selection.provider.name,
        )
    try:
        return manager.prepare_session(
            cwd=cwd,
            model=selection.model,
            provider_name=selection.provider.name,
            inference_provider=inference_provider,
            inference_provider_mode="fixed",
        )
    except TypeError:
        try:
            return manager.prepare_session(
                cwd=cwd,
                model=selection.model,
                provider_name=selection.provider.name,
                inference_provider=inference_provider,
            )
        except TypeError:
            return manager.prepare_session(
                cwd=cwd,
                model=selection.model,
                provider_name=selection.provider.name,
            )


def _resolve_tui_startup_selection(
    settings: Any,
    *,
    record: Any | None,
    provider_name: str | None,
    model: str | None,
    explicit_resume: bool,
) -> ProviderSelection:
    if provider_name is not None or model is not None:
        return resolve_provider_selection(settings, provider_name=provider_name, model=model)

    if explicit_resume:
        record_selection = _selection_from_session_record(settings, record)
        if record_selection is not None:
            return record_selection

    default_selection = resolve_provider_selection(settings)
    if provider_has_usable_credentials(
        default_selection.provider,
        credential_reader=FileCredentialStore(),
    ):
        return default_selection

    fallback_selection = _first_usable_startup_selection(settings)
    return fallback_selection or default_selection


def _first_usable_startup_selection(settings: Any) -> ProviderSelection | None:
    credential_store = FileCredentialStore()
    for provider in settings.providers:
        if provider_has_usable_credentials(provider, credential_reader=credential_store):
            return ProviderSelection(provider=provider, model=provider.default_model)
    return None


def _selection_from_session_record(settings: Any, record: Any | None) -> ProviderSelection | None:
    if record is None:
        return None
    record_model = getattr(record, "model", None)
    if not isinstance(record_model, str) or not record_model:
        return None

    record_provider = getattr(record, "provider_name", None)
    if isinstance(record_provider, str) and record_provider:
        try:
            return resolve_provider_selection(
                settings,
                provider_name=record_provider,
                model=record_model,
            )
        except Exception:
            return None

    for choice in _usable_scoped_startup_choices(settings):
        if choice.model == record_model:
            return resolve_provider_selection(
                settings,
                provider_name=choice.provider_name,
                model=choice.model,
            )

    credential_store = FileCredentialStore()
    for provider in settings.providers:
        if record_model not in provider.models:
            continue
        if not provider_has_usable_credentials(provider, credential_reader=credential_store):
            continue
        return ProviderSelection(provider=provider, model=record_model)
    return None


def _usable_scoped_startup_choices(settings: Any) -> tuple[ModelChoice, ...]:
    credential_store = FileCredentialStore()
    choices: list[ModelChoice] = []
    for item in settings.scoped_models:
        try:
            provider = settings.get_provider(item.provider)
        except Exception:
            continue
        if item.model not in provider.models:
            continue
        if not provider_has_usable_credentials(provider, credential_reader=credential_store):
            continue
        choices.append(ModelChoice(provider_name=item.provider, model=item.model))
    return tuple(choices)


def _resource_conflict_alert(
    diagnostics: Sequence[ResourceDiagnostic],
) -> str | None:
    """Format skill and prompt precedence conflicts as one startup alert."""
    prefix = "overrides lower-precedence resource at "
    conflicts = [
        diagnostic
        for diagnostic in diagnostics
        if diagnostic.kind in {"skill", "prompt"}
        and diagnostic.name is not None
        and diagnostic.path is not None
        and diagnostic.message.startswith(prefix)
    ]
    if not conflicts:
        return None

    lines = ["Conflicting skills/prompts detected:"]
    for diagnostic in conflicts:
        resource_kind = "skill" if diagnostic.kind == "skill" else "prompt template"
        shadowed_path = diagnostic.message.removeprefix(prefix)
        lines.append(f"- {resource_kind} '{diagnostic.name}': {diagnostic.path} overrides {shadowed_path}")
    lines.append("Rename or remove duplicate resources to clear this alert.")
    return "\n".join(lines)


def _startup_inference_provider(
    selection: ProviderSelection,
    record: CodingSessionRecord | None,
) -> str | None:
    provider = selection.provider
    if not isinstance(provider, OpenAICompatibleProviderConfig) or provider.name != "huggingface":
        return None
    if record is not None and record.model == selection.model:
        return record.inference_provider
    return provider.inference_providers.get(selection.model) or provider.default_inference_provider


def _startup_inference_provider_mode(
    selection: ProviderSelection,
    record: CodingSessionRecord | None,
) -> Literal["automatic", "fixed"]:
    if record is not None and record.model == selection.model:
        return record.inference_provider_mode
    return "fixed" if _startup_inference_provider(selection, None) is not None else "automatic"


async def run_tui_app(
    *,
    model: str | None,
    cwd: Path,
    session_id: str | None = None,
    new_session: bool = False,
    provider_name: str | None = None,
    auto_compact_token_threshold: int | None = None,
    initial_prompt: str | None = None,
    show_full_output: bool = False,
    session_manager: SessionManager | None = None,
    startup_notice: str | None = None,
    startup_update_notice: str | None = None,
    deferred_startup_update_notice: Callable[[], str | None] | None = None,
    startup_notices: Sequence[str] = (),
    extension_paths: tuple[Path, ...] = (),
    extensions_enabled: bool = True,
    project_extensions_enabled: bool = False,
    custom_system_prompt: str | None = None,
    append_system_prompt: str | None = None,
    trust_override: TrustOverride | None = None,
    thinking_level_override: ThinkingLevel | None = None,
) -> str | None:
    """Run the Textual app and return the active id when its session is persisted."""
    _configure_herdr_textual_mouse()
    if new_session and session_id is not None:
        raise RuntimeError("--session and --new-session cannot be used together")

    provider_settings = load_provider_settings()
    shell_settings = load_shell_settings()
    manager = session_manager or SessionManager()
    record = _explicit_resume_record(
        manager,
        session_id=session_id,
    )
    selection: ProviderSelection | None = None
    try:
        selection = _resolve_tui_startup_selection(
            provider_settings,
            record=record,
            provider_name=provider_name,
            model=model,
            explicit_resume=session_id is not None,
        )
    except ProviderConfigError:
        # A resumed record may point at a process-local provider that is not in
        # durable settings. Let the staged loader resolve it after trusted
        # built-in/project extensions are loaded.
        dynamic_resume = (
            session_id is not None
            and record is not None
            and record.provider_name is not None
            and provider_name is None
            and model is None
        )
        explicit_dynamic = provider_name is not None and model is not None
        if not dynamic_resume and not explicit_dynamic:
            raise
    startup_message: str | None = None
    startup_error_notice: str | None = None
    explicit_selection = provider_name is not None or model is not None
    selected_provider_name: str = (
        provider_name
        if provider_name is not None
        else (record.provider_name if record is not None else None)
        or (selection.provider.name if selection is not None else DEFAULT_PROVIDER_NAME)
    )
    selected_model = (
        model
        if explicit_selection and model is not None
        else (record.model if record is not None else None)
        or (selection.model if selection is not None else DEFAULT_MODEL)
    )
    # Keep static-provider construction compatible with embedded TUI callers,
    # while dynamic providers are deliberately left for CodingSession.load()
    # after trusted extension setup. The provider passed below is owned by the
    # prepared session when the real loader is used.
    initial_provider: ClosableModelProvider | None = None
    runtime_provider_config: ProviderConfig | None = selection.provider if selection else None
    inference_provider = _startup_inference_provider(selection, record) if selection else None
    inference_provider_mode: Literal["automatic", "fixed"] = (
        _startup_inference_provider_mode(selection, record) if selection else "automatic"
    )
    if selection is not None:
        try:
            initial_provider = create_model_provider(
                selection.provider,
                model=selection.model,
                inference_provider=inference_provider,
                thinking_level=resolve_startup_thinking_level(
                    selection.provider,
                    selection.model,
                    cli_override=thinking_level_override,
                ),
            )
        except RuntimeError as exc:
            login_required_message = (
                "Login required. Run /login to choose a provider, "
                f"or /login {selected_provider_name} to continue with the current provider."
            )
            startup_message = f"{login_required_message}\n\nStartup error: {exc}"
            startup_error_notice = (
                f"Startup provider creation failed for {selection.provider.name}:{selection.model}: {exc}"
            )
            initial_provider = LoginRequiredProvider(startup_message)
            runtime_provider_config = None
    elif not explicit_selection:
        startup_message = (
            "Login required. Run /login to choose a provider, "
            f"or /login {selected_provider_name} to continue with the current provider."
        )
        initial_provider = LoginRequiredProvider(startup_message)
    session: CodingSession | None = None
    try:
        index_on_first_persist = False
        if record is None:
            if selection is not None:
                record = _create_startup_session_record(
                    manager,
                    cwd=cwd,
                    selection=selection,
                    inference_provider=inference_provider,
                )
            else:
                if provider_name is None or model is None:
                    raise ProviderConfigError("An explicit provider and model are required for this startup.")
                record = manager.prepare_session(
                    cwd=cwd,
                    model=model,
                    provider_name=provider_name,
                )
            index_on_first_persist = manager.get_session(record.id) is None

        tui_settings = load_tui_settings()
        # The approval gate is wired before the session loads, but the UI it
        # needs only exists after the session adopts; the holder closes that
        # gap and fails closed if a mutating call ever races adoption.
        approval_app_ref: dict[str, BaldricTuiApp] = {}

        async def approval_gate(tool_call: ToolCall) -> tuple[bool, str | None]:
            app = approval_app_ref.get("app")
            if app is None:
                return True, "Approval UI is not ready; mutating call blocked."
            return await app.approval_gate(tool_call)

        prepared = await prepare_coding_session(
            CodingSessionConfig(
                provider=initial_provider,
                model=record.model or selected_model,
                cwd=record.cwd,
                storage=jsonl_session_storage(record.path),
                session_id=record.id,
                session_manager=manager,
                provider_name=selected_provider_name,
                inference_provider=inference_provider,
                inference_provider_mode=inference_provider_mode,
                requested_provider=provider_name if explicit_selection else None,
                requested_model=model if explicit_selection else None,
                session_provider_name=record.provider_name,
                provider_settings=provider_settings,
                runtime_provider_config=runtime_provider_config,
                auto_compact_token_threshold=auto_compact_token_threshold,
                index_on_first_persist=index_on_first_persist,
                shell_command_prefix=shell_settings.shell_command_prefix,
                shell=shell_settings.shell,
                extension_paths=extension_paths,
                extensions_enabled=extensions_enabled,
                project_extensions_enabled=project_extensions_enabled,
                custom_system_prompt=custom_system_prompt,
                append_system_prompt=append_system_prompt,
                thinking_level_override=thinking_level_override,
                trust_override=trust_override,
                trust_default=shell_settings.default_project_trust,
                trust_interactive=True,
                trust_prompt=prompt_project_trust,
                defer_authoritative_writes=True,
                owns_initial_provider=initial_provider is not None,
                before_tool_call=approval_gate,
            ),
            session_loader=CodingSession,
        )
        try:
            session = await prepared.adopt()
        except ValueError:
            candidate = prepared.session
            trust_resolution = getattr(candidate, "project_trust_resolution", None)
            if trust_resolution is None or not trust_resolution.cancelled:
                raise
            # The preparation object already closed the unpublished candidate.
            # Do not close that candidate again from the outer finally block.
            del candidate
            return None
        trust_resolution = getattr(session, "project_trust_resolution", None)
        if trust_resolution is not None and trust_resolution.cancelled:
            return None

        theme_dirs = getattr(session, "theme_dirs", None)
        if theme_dirs is None:
            trusted = trust_resolution is None or trust_resolution.trusted
            theme_dirs = BaldricResourcePaths(
                cwd=record.cwd,
                project_resources_enabled=trusted,
            ).themes_dirs
        custom_themes, theme_diagnostics = load_custom_tui_themes(theme_dirs)
        set_custom_tui_themes(custom_themes)
        legacy_notices = (startup_notice,) if startup_notice else ()
        error_notices = (startup_error_notice,) if startup_error_notice else ()
        theme_notices = tuple(diagnostic.format() for diagnostic in theme_diagnostics)
        all_startup_notices = tuple((*error_notices, *startup_notices, *legacy_notices, *theme_notices))
        resource_conflict_alert = _resource_conflict_alert(getattr(session, "resource_diagnostics", ()))
        startup_alerts = (resource_conflict_alert,) if resource_conflict_alert is not None else ()
        app = BaldricTuiApp(
            session,
            tui_settings=tui_settings,
            startup_message=startup_message,
            startup_update_notice=startup_update_notice,
            deferred_update_notice=deferred_startup_update_notice,
            startup_alerts=startup_alerts,
            startup_notices=all_startup_notices,
            initial_prompt=initial_prompt,
            show_full_output=show_full_output,
        )
        approval_app_ref["app"] = app
        set_trust_prompt = getattr(session, "set_project_trust_prompt", None)
        if set_trust_prompt is not None:
            prompt_trust = getattr(app, "prompt_project_trust", None)
            if prompt_trust is not None:
                set_trust_prompt(prompt_trust)
        watchdog = LoopWatchdog(lambda: app._ui_heartbeat)
        watchdog.start()
        try:
            await app.run_async()
        finally:
            watchdog.stop()
    finally:
        if session is not None:
            close_session = getattr(session, "aclose", None)
            if close_session is not None:
                await close_session()
        # Compatibility for lightweight test/embedded session loaders that do
        # not expose ownership. A real CodingSession owns the exact candidate,
        # so this branch does not double-close it.
        if initial_provider is not None and getattr(session, "provider", None) is not initial_provider:
            with suppress(Exception):
                await initial_provider.aclose()

    active_session_id: str | None = getattr(session, "session_id", None)
    if active_session_id is None or manager.get_session(active_session_id) is None:
        return None
    return active_session_id
