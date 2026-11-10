"""Shared test helpers for TUI tests.

These helpers are importable by any test file without creating a test-package
dependency on ``test_tui_app``. They do not run any tests themselves.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace

from baldric.agent import AgentEvent, UserMessage
from baldric.runtime.commands.base import (
    CommandKind,
    CommandOutcome,
    MessageDisplay,
    PickerKind,
    message_outcome,
    not_handled,
)
from baldric.runtime.commands.registry import CommandResult, format_resource_diagnostics
from baldric.runtime.context.skills.skills import Skill
from baldric.runtime.context.system_prompt import (
    ProjectContextFile,
    SystemPromptInspection,
    SystemPromptSource,
    format_system_prompt_inspection,
)
from baldric.runtime.events import QueueUpdateEvent
from baldric.runtime.session.manager import CodingSessionRecord
from baldric.runtime.session.session import (
    ModelChoice,
    SessionTreeChoice,
    TerminalCommandResult,
)
from baldric.runtime.session.stats import SessionStats
from baldric.runtime.tools.registry import create_coding_tools
from baldric.runtime.tui.app import BaldricTuiApp, _TuiExtensionUiBridge


class FakeSessionState:
    thinking_level = "medium"


class FakeSession:
    def __init__(self, messages=(), events=()) -> None:
        self.messages = tuple(messages)
        self.events = tuple(events)
        self.cwd = Path("/workspace/project")
        self.provider_name = "openai"
        self.model = "fake-model"
        self.available_models = ("fake-model", "other-model")
        self.available_model_choices = (
            ModelChoice(provider_name="openai", model="fake-model"),
            ModelChoice(provider_name="openai", model="other-model"),
            ModelChoice(provider_name="local", model="local-model"),
        )
        self.scoped_model_choices: tuple[ModelChoice, ...] = ()
        self.available_providers = ("openai",)
        self.tools = tuple(create_coding_tools(cwd=self.cwd))
        self.extension_tool_sources: dict[str, str] = {}
        self.skills = (
            Skill(
                name="review",
                path=self.cwd / ".baldric" / "skills" / "review" / "SKILL.md",
                content="Review code",
            ),
        )
        self.prompt_templates = ()
        self.context_files = (ProjectContextFile(path=str(self.cwd / "AGENTS.md"), content="Follow rules."),)
        self.system_prompt_files: tuple[Path, ...] = ()
        self.context_token_estimate = 12034
        self.has_provider_context_usage = True
        self.auto_compact_token_threshold = 200000
        self.context_window_tokens = 216384
        self.thinking_level = "medium"
        self.available_thinking_levels = (
            "off",
            "minimal",
            "low",
            "medium",
            "high",
            "xhigh",
        )
        self.state = FakeSessionState()
        self.resource_diagnostics = ()
        self.extension_names = ("permission-gate", "subagents")
        self.session_stats = SessionStats(
            turn_count=14,
            tool_call_count=23,
            input_tokens=1_200_000,
            output_tokens=48_000,
            cached_input_tokens=1_140_000,
            latest_prompt_tokens=1_200_000,
            latest_cached_input_tokens=1_188_000,
            timed_output_tokens=48_000,
            response_duration_ms=1_200_000,
            time_to_first_output_ms=18_000,
            timed_first_output_count=15,
            estimated_cost=1.24,
        )
        self.system_prompt = "You are Baldric."
        self.system_prompt_sources: tuple[SystemPromptSource, ...] | None = None
        self.shell = "auto"
        self.shell_command_prefix: str | None = None
        self.session_manager = None
        self._session_title: str | None = None
        self.compact_summaries: list[str] = []
        self.resumed_session_ids: list[str] = []
        self.tree_branch_requests: list[tuple[str, bool, str | None]] = []
        self.tree_label_requests: list[tuple[str, str | None]] = []
        self.tree_labels: dict[str, tuple[str, float]] = {}
        self.new_session_count = 0
        self.prompt_texts: list[str] = []
        self.prompt_sources: list[str] = []
        self.reload_count = 0
        self.provider_reload_count = 0
        self.model_catalog_refresh_count = 0
        self.queued_steering_messages: tuple[str, ...] = ()
        self.queued_follow_up_messages: tuple[str, ...] = ()
        self.streaming_behaviors: list[str | None] = []
        self.terminal_commands: list[tuple[str, bool]] = []
        self.cancel_count = 0
        self.export_calls: list[tuple[Path | None, str | None]] = []
        self.session_start_emissions = 0

    async def emit_pending_session_start(self) -> None:
        self.session_start_emissions += 1

    @property
    def session_title(self) -> str | None:
        return self._session_title

    def handle_command(self, text: str) -> CommandResult:
        if text == "/session":
            return CommandResult(outcome=message_outcome("Session info"))
        if text == "/reload":
            self.reload_count += 1
            self.skills = (
                Skill(
                    name="reloaded",
                    path=self.cwd / "reloaded.md",
                    content="Reloaded skill",
                ),
            )
            return CommandResult(
                outcome=CommandOutcome(
                    kind=CommandKind.MESSAGE,
                    message="Reloaded local coding resources and project context.",
                    display=MessageDisplay.TRANSCRIPT,
                )
            )
        if text == "/system":
            inspection = SystemPromptInspection(
                text=self.system_prompt,
                sources=self.system_prompt_sources
                or (
                    SystemPromptSource(
                        kind="runtime",
                        label="Effective system prompt",
                        source="active Baldric session",
                        content=self.system_prompt,
                    ),
                ),
            )
            return CommandResult(
                outcome=CommandOutcome(
                    kind=CommandKind.MESSAGE,
                    message=format_system_prompt_inspection(inspection),
                    display=MessageDisplay.TRANSCRIPT,
                    system_prompt_inspection=inspection,
                )
            )
        if text == "/diagnostics":
            return CommandResult(
                outcome=message_outcome(format_resource_diagnostics(self.resource_diagnostics))
            )
        if text == "/skills":
            return CommandResult(
                outcome=CommandOutcome(kind=CommandKind.OPEN_PICKER, picker=PickerKind.SKILLS)
            )
        if text == "/new":
            return CommandResult(outcome=CommandOutcome(kind=CommandKind.NEW_SESSION))
        if text == "/compact":
            return CommandResult(outcome=CommandOutcome(kind=CommandKind.COMPACT, text=""))
        if text.startswith("/compact "):
            return CommandResult(
                outcome=CommandOutcome(
                    kind=CommandKind.COMPACT,
                    text=text.removeprefix("/compact "),
                )
            )
        if text == "/export":
            return CommandResult(outcome=CommandOutcome(kind=CommandKind.EXPORT))
        if text.startswith("/export "):
            return CommandResult(
                outcome=CommandOutcome(
                    kind=CommandKind.EXPORT,
                    text="out.jsonl",
                    format="jsonl",
                )
            )
        if text.startswith("/resume "):
            return CommandResult(
                outcome=CommandOutcome(
                    kind=CommandKind.OPEN_PICKER,
                    picker=PickerKind.SESSION_RESUME,
                    session_id=text.removeprefix("/resume "),
                )
            )
        if text == "/resume":
            return CommandResult(
                outcome=CommandOutcome(
                    kind=CommandKind.OPEN_PICKER,
                    picker=PickerKind.SESSION_RESUME,
                )
            )
        if text == "/prompts":
            return CommandResult(
                outcome=CommandOutcome(kind=CommandKind.OPEN_PICKER, picker=PickerKind.PROMPTS)
            )
        if text == "/tree":
            return CommandResult(outcome=CommandOutcome(kind=CommandKind.OPEN_PICKER, picker=PickerKind.TREE))
        if text == "/login":
            return CommandResult(
                outcome=CommandOutcome(
                    kind=CommandKind.OPEN_PICKER,
                    picker=PickerKind.LOGIN_METHOD,
                )
            )
        if text in {"/login custom", "/login new", "/login add"}:
            return CommandResult(
                outcome=CommandOutcome(
                    kind=CommandKind.OPEN_PICKER,
                    picker=PickerKind.CUSTOM_PROVIDER_LOGIN,
                )
            )
        if text == "/login anthropic-api":
            return CommandResult(
                outcome=CommandOutcome(
                    kind=CommandKind.OPEN_PICKER,
                    picker=PickerKind.LOGIN_PROVIDER,
                    provider="anthropic",
                    method="api-key",
                )
            )
        if text == "/login anthropic-subscription":
            return CommandResult(
                outcome=CommandOutcome(
                    kind=CommandKind.OPEN_PICKER,
                    picker=PickerKind.LOGIN_PROVIDER,
                    provider="anthropic",
                    method="subscription",
                )
            )
        if text.startswith("/login "):
            return CommandResult(
                outcome=CommandOutcome(
                    kind=CommandKind.OPEN_PICKER,
                    picker=PickerKind.LOGIN_PROVIDER,
                    provider=text.removeprefix("/login "),
                )
            )
        if text == "/logout":
            return CommandResult(
                outcome=CommandOutcome(
                    kind=CommandKind.OPEN_PICKER,
                    picker=PickerKind.LOGOUT_PROVIDER,
                )
            )
        if text.startswith("/logout "):
            return CommandResult(
                outcome=CommandOutcome(
                    kind=CommandKind.OPEN_PICKER,
                    picker=PickerKind.LOGOUT_PROVIDER,
                    provider=text.removeprefix("/logout "),
                )
            )
        if text == "/model":
            return CommandResult(
                outcome=CommandOutcome(kind=CommandKind.OPEN_PICKER, picker=PickerKind.MODEL)
            )
        if text == "/tools":
            return CommandResult(
                outcome=CommandOutcome(kind=CommandKind.OPEN_PICKER, picker=PickerKind.TOOLS)
            )
        if text in {"/scoped-models", "/scoped models"}:
            return CommandResult(
                outcome=CommandOutcome(
                    kind=CommandKind.OPEN_PICKER,
                    picker=PickerKind.SCOPED_MODELS,
                )
            )
        if text.startswith("/thinking "):
            return CommandResult(
                outcome=CommandOutcome(
                    kind=CommandKind.THINKING_SET,
                    text=text.removeprefix("/thinking "),
                )
            )
        if text == "/theme":
            return CommandResult(
                outcome=CommandOutcome(kind=CommandKind.OPEN_PICKER, picker=PickerKind.THEME)
            )
        if text == "/sidebar":
            return CommandResult(outcome=CommandOutcome(kind=CommandKind.TOGGLE_SIDEBAR))
        if text.startswith("/theme "):
            return CommandResult(
                outcome=CommandOutcome(
                    kind=CommandKind.THEME_SET,
                    text=text.removeprefix("/theme "),
                )
            )
        if text.startswith("/name "):
            name = text.removeprefix("/name ")
            return CommandResult(
                outcome=CommandOutcome(
                    kind=CommandKind.SESSION_NAMED,
                    message=f"Session renamed: {name}",
                    display=MessageDisplay.NOTIFICATION,
                    text=name,
                )
            )
        return CommandResult(outcome=not_handled())

    def set_model(self, model: str) -> None:
        self.model = model

    def set_model_choice(self, choice: ModelChoice) -> None:
        self.set_provider(choice.provider_name)
        self.set_model(choice.model)

    def toggle_scoped_model(self, choice: ModelChoice) -> tuple[ModelChoice, ...]:
        scoped = list(self.scoped_model_choices)
        if choice in scoped:
            scoped.remove(choice)
        else:
            scoped.append(choice)
        self.scoped_model_choices = tuple(scoped)
        return self.scoped_model_choices

    def cycle_scoped_model(self, *, reverse: bool = False) -> ModelChoice:
        if not self.scoped_model_choices:
            raise ValueError("No scoped models configured.")
        current = ModelChoice(provider_name=self.provider_name, model=self.model)
        try:
            index = self.scoped_model_choices.index(current)
        except ValueError:
            index = -1 if not reverse else 0
        delta = -1 if reverse else 1
        choice = self.scoped_model_choices[(index + delta) % len(self.scoped_model_choices)]
        self.set_model_choice(choice)
        return choice

    def set_provider(self, provider_name: str) -> None:
        self.provider_name = provider_name
        if provider_name == "local":
            self.available_models = ("local-model",)

    def reload(self) -> None:
        self.reload_count += 1

    def reload_provider_settings(self) -> None:
        self.provider_reload_count += 1

    async def refresh_model_catalogs(self) -> None:
        self.model_catalog_refresh_count += 1

    async def set_session_name(self, name: str) -> str:
        self._session_title = name
        return name

    async def set_thinking_level(self, level: str) -> str:
        self.thinking_level = level
        self.state.thinking_level = level
        return f"Thinking mode: {level}"

    async def cycle_thinking_level(self) -> str:
        levels = self.available_thinking_levels
        current_index = levels.index(self.thinking_level)
        self.thinking_level = levels[(current_index + 1) % len(levels)]
        self.state.thinking_level = self.thinking_level
        return f"Thinking mode: {self.thinking_level}"

    async def compact(self, summary: str) -> str:
        self.compact_summaries.append(summary)
        self.messages = (UserMessage(content="Previous conversation summary:\nGenerated summary"),)
        self.context_token_estimate = 42
        return "Compacted 2 context entries."

    async def export(self, destination: Path | None = None, *, format: str | None = None) -> Path:
        self.export_calls.append((destination, format))
        return self.cwd / "session.html"

    async def resume(self, session_id: str) -> str:
        self.resumed_session_ids.append(session_id)
        self.messages = (UserMessage(content="Restored prompt"),)
        self.context_token_estimate = 456
        return f"Resumed session: {session_id}"

    async def tree_choices(self) -> tuple[SessionTreeChoice, ...]:
        return (
            SessionTreeChoice(entry_id="root", label="user: Root"),
            SessionTreeChoice(entry_id="tool", label="tool call: read", is_tool_call=True),
            SessionTreeChoice(
                entry_id="left",
                label="assistant: Left",
                bookmark_label=self.tree_labels.get("left", (None, None))[0],
                label_timestamp=self.tree_labels.get("left", (None, None))[1],
            ),
            SessionTreeChoice(entry_id="right", label="assistant: Right", active=True),
        )

    async def set_label(self, entry_id: str, label: str | None) -> SimpleNamespace:
        self.tree_label_requests.append((entry_id, label))
        timestamp = 1_700_000_000.0 + len(self.tree_label_requests)
        if label is None:
            self.tree_labels.pop(entry_id, None)
        else:
            self.tree_labels[entry_id] = (label, timestamp)
        return SimpleNamespace(timestamp=timestamp)

    async def branch_to_entry(
        self,
        entry_id: str,
        *,
        summarize: bool = False,
        custom_instructions: str | None = None,
    ) -> str:
        self.tree_branch_requests.append((entry_id, summarize, custom_instructions))
        self.messages = (UserMessage(content=f"Branched to {entry_id}"),)
        return f"Branched session at {entry_id}."

    async def new_session(self) -> str:
        self.new_session_count += 1
        self.messages = ()
        self.context_token_estimate = 0
        return "Started new session: new-session"

    def cancel(self) -> None:
        self.cancel_count += 1

    def queue_update_event(self) -> QueueUpdateEvent:
        return QueueUpdateEvent(
            steering=self.queued_steering_messages,
            follow_up=self.queued_follow_up_messages,
        )

    async def run_terminal_command(
        self,
        command: str,
        *,
        add_to_context: bool,
    ) -> TerminalCommandResult:
        self.terminal_commands.append((command, add_to_context))
        return TerminalCommandResult(
            command=command,
            output="command output",
            exit_code=0,
            ok=True,
            added_to_context=add_to_context,
        )

    def pop_latest_follow_up_message(self) -> str | None:
        if not self.queued_follow_up_messages:
            return None
        message = self.queued_follow_up_messages[-1]
        self.queued_follow_up_messages = self.queued_follow_up_messages[:-1]
        return message

    def pop_latest_steering_message(self) -> str | None:
        if not self.queued_steering_messages:
            return None
        message = self.queued_steering_messages[-1]
        self.queued_steering_messages = self.queued_steering_messages[:-1]
        return message

    async def prompt(
        self,
        text: str,
        *,
        streaming_behavior: str | None = None,
        source: str = "interactive",
        custom_type: str | None = None,
        details: dict[str, object] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        self.prompt_texts.append(text)
        self.prompt_sources.append(source)
        self.streaming_behaviors.append(streaming_behavior)
        if streaming_behavior == "steer":
            self.queued_steering_messages = (*self.queued_steering_messages, text)
            yield self.queue_update_event()
            return
        if streaming_behavior == "follow_up":
            self.queued_follow_up_messages = (*self.queued_follow_up_messages, text)
            yield self.queue_update_event()
            return
        for event in self.events:
            yield event


class _FakeSessionManager:
    def __init__(
        self,
        records: list[CodingSessionRecord],
        archived_records: list[CodingSessionRecord] | None = None,
    ) -> None:
        self._records = records
        self._archived_records = archived_records or []
        self.archived_session_ids: list[str] = []
        self.archived_project_cwds: list[Path] = []
        self.restored_session_ids: list[str] = []
        self.restored_project_cwds: list[Path] = []

    def list_sessions(self, cwd: Path | None = None) -> list[CodingSessionRecord]:
        del cwd
        return self._records

    def list_archived_sessions(self, cwd: Path | None = None) -> list[CodingSessionRecord]:
        del cwd
        return self._archived_records

    def archive_session(self, session_id: str) -> bool:
        self.archived_session_ids.append(session_id)
        moved = [record for record in self._records if record.id == session_id]
        self._records = [record for record in self._records if record.id != session_id]
        self._archived_records.extend(moved)
        return bool(moved)

    def archive_project(self, cwd: Path) -> bool:
        resolved = Path(cwd).resolve()
        self.archived_project_cwds.append(Path(cwd))
        before = len(self._records)
        moved = [record for record in self._records if Path(record.cwd).resolve() == resolved]
        self._records = [record for record in self._records if Path(record.cwd).resolve() != resolved]
        self._archived_records.extend(moved)
        return len(self._records) != before

    def unarchive_session(self, session_id: str) -> bool:
        self.restored_session_ids.append(session_id)
        moved = [record for record in self._archived_records if record.id == session_id]
        self._archived_records = [record for record in self._archived_records if record.id != session_id]
        self._records.extend(moved)
        return bool(moved)

    def unarchive_project(self, cwd: Path) -> bool:
        resolved = Path(cwd).resolve()
        self.restored_project_cwds.append(Path(cwd))
        moved = [record for record in self._archived_records if Path(record.cwd).resolve() == resolved]
        self._archived_records = [
            record for record in self._archived_records if Path(record.cwd).resolve() != resolved
        ]
        self._records.extend(moved)
        return bool(moved)


def _component_bridge(app: BaldricTuiApp) -> _TuiExtensionUiBridge:
    """Return a host component bridge bound to a running app."""
    return _TuiExtensionUiBridge(app)


class _RenderCallRuntime:
    """Minimal extension-runtime stub for ``_connect_extension_runtime``."""

    def set_ui_bridge(self, bridge) -> None:  # noqa: ANN001
        del bridge

    def set_turn_requested_callback(self, callback) -> None:  # noqa: ANN001
        del callback

    def render_custom_message(self, custom_type, content, details, expanded):  # noqa: ANN001
        return None

    def render_tool_call(self, name, arguments):  # noqa: ANN001
        if name == "agent":
            return f"▸ agent · {arguments.get('description')}"
        return None

    def render_tool_result(self, tool_name, result, expanded):  # noqa: ANN001
        if tool_name == "agent" and result.details:
            suffix = " · expanded" if expanded else ""
            return f"[green]✓[/green] {result.details.get('description')} completed{suffix}"
        return None


class _CustomMessageRuntime(_RenderCallRuntime):
    """Runtime stub whose custom renderer produces a card for notifications."""

    def render_custom_message(self, custom_type, content, details, expanded):  # noqa: ANN001
        del content, expanded
        if custom_type != "subagent-notification" or not details:
            return None
        return f"[green]✓[/green] {details.get('description')} completed"


def _strip_ansi(text: str) -> str:
    import re

    pattern = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
    return pattern.sub("", text)


def _style_color_escape(color: str) -> str:
    stripped = color.lstrip("#")
    red, green, blue = (int(stripped[index : index + 2], 16) for index in (0, 2, 4))
    return f"38;2;{red};{green};{blue}"


def _style_rgb(color: str) -> str:
    stripped = color.lstrip("#")
    red, green, blue = (int(stripped[index : index + 2], 16) for index in (0, 2, 4))
    return f"rgb({red},{green},{blue})"
