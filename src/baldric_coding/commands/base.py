"""Core slash-command types and registry primitives."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from baldric_agent.tools import AgentTool
from baldric_coding.context.prompts import PromptTemplate
from baldric_coding.context.resources import ResourceDiagnostic
from baldric_coding.context.skills.skills import Skill
from baldric_coding.context.system_prompt import ProjectContextFile, SystemPromptInspection
from baldric_coding.session.manager import SessionManager


class CommandSession(Protocol):
    """Session attributes available to slash-command handlers."""

    @property
    def cwd(self) -> Path: ...

    @property
    def model(self) -> str: ...

    @property
    def provider_name(self) -> str: ...

    @property
    def available_models(self) -> Sequence[str]: ...

    @property
    def available_providers(self) -> Sequence[str]: ...

    @property
    def tools(self) -> Sequence[AgentTool]: ...

    @property
    def skills(self) -> Sequence[Skill]: ...

    @property
    def prompt_templates(self) -> Sequence[PromptTemplate]: ...

    @property
    def context_files(self) -> Sequence[ProjectContextFile]: ...

    @property
    def context_token_estimate(self) -> int: ...

    @property
    def auto_compact_token_threshold(self) -> int | None: ...

    @property
    def context_window_tokens(self) -> int: ...

    @property
    def thinking_level(self) -> str: ...

    @property
    def available_thinking_levels(self) -> Sequence[str]: ...

    @property
    def resource_diagnostics(self) -> Sequence[ResourceDiagnostic]: ...

    @property
    def system_prompt(self) -> str: ...

    @property
    def system_prompt_inspection(self) -> SystemPromptInspection: ...

    @property
    def session_id(self) -> str | None: ...

    @property
    def session_title(self) -> str | None: ...

    @property
    def session_manager(self) -> SessionManager | None: ...

    def ensure_session_indexed(self) -> None: ...

    def set_model(self, model: str) -> None: ...


class PickerKind(StrEnum):
    """Interactive pickers a command can request; frontends map each to a screen."""

    MODEL = "model"
    SCOPED_MODELS = "scoped-models"
    SESSION_RESUME = "session-resume"
    PROMPTS = "prompts"
    TREE = "tree"
    SKILLS = "skills"
    TOOLS = "tools"
    THEME = "theme"
    EXTENSIONS = "extensions"
    LOGIN_METHOD = "login-method"
    LOGIN_PROVIDER = "login-provider"
    CUSTOM_PROVIDER_LOGIN = "custom-provider-login"
    LOGOUT_PROVIDER = "logout-provider"
    LOCAL_BACKEND = "local-backend"


class MessageDisplay(StrEnum):
    """How a command's message wants to be shown; the command declares it.

    This replaces the old text-prefix sniffing (``text == "/name"``) that
    coupled message presentation to the literal command the user typed.
    """

    POPUP = "popup"
    TRANSCRIPT = "transcript"
    NOTIFICATION = "notification"


class CommandKind(StrEnum):
    """Closed set of semantic command results; frontends dispatch on this."""

    NOT_HANDLED = "not_handled"
    MESSAGE = "message"
    EXIT = "exit"
    OPEN_PICKER = "open_picker"
    MODEL_SELECTED = "model_selected"
    THINKING_SET = "thinking_set"
    THEME_SET = "theme_set"
    SESSION_NAMED = "session_named"
    RELOAD = "reload"
    NEW_SESSION = "new_session"
    COMPACT = "compact"
    EXPORT = "export"
    TOGGLE_SIDEBAR = "toggle_sidebar"
    TOGGLE_APPROVALS = "toggle_approvals"


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    """The semantic result of one slash command.

    One command maps to exactly one outcome. ``message`` may accompany any
    kind (e.g. ``/name`` reports and renames). Frontends dispatch on ``kind``
    and render ``message`` according to ``display`` — neither interprets
    payload fields outside their kind's contract.
    """

    kind: CommandKind
    message: str | None = None
    display: MessageDisplay = MessageDisplay.POPUP
    picker: PickerKind | None = None
    provider: str | None = None
    method: str | None = None
    session_id: str | None = None
    text: str | None = None
    format: str | None = None
    system_prompt_inspection: SystemPromptInspection | None = None


def not_handled() -> CommandOutcome:
    """Return the canonical unhandled outcome."""
    return CommandOutcome(kind=CommandKind.NOT_HANDLED)


def message_outcome(
    message: str, *, display: MessageDisplay = MessageDisplay.POPUP
) -> CommandOutcome:
    """Return an informational outcome rendered per *display*."""
    return CommandOutcome(kind=CommandKind.MESSAGE, message=message, display=display)


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Result of handling a coding-session slash command."""

    outcome: CommandOutcome

    @property
    def handled(self) -> bool:
        return self.outcome.kind is not CommandKind.NOT_HANDLED


def handled_result(outcome: CommandOutcome) -> CommandResult:
    """Wrap a semantic outcome as a handled command result."""
    return CommandResult(outcome=outcome)


def unhandled_result() -> CommandResult:
    """Return the canonical result for text that is not a command."""
    return CommandResult(outcome=not_handled())


@dataclass(frozen=True, slots=True)
class CommandContext:
    """Runtime context passed to slash-command handlers."""

    session: CommandSession
    registry: CommandRegistry
    text: str
    name: str
    args: str


CommandHandler = Callable[[CommandContext], CommandResult]


@dataclass(frozen=True, slots=True)
class SlashCommand:
    """A registered slash command and its user-facing metadata."""

    name: str
    description: str
    usage: str
    handler: CommandHandler
    aliases: tuple[str, ...] = ()
    search_terms: tuple[str, ...] = ()


class CommandRegistry:
    """Parse, register, list, and execute slash commands."""

    def __init__(self) -> None:
        self._commands: dict[str, SlashCommand] = {}
        self._aliases: dict[str, str] = {}

    def register(self, command: SlashCommand) -> None:
        """Register a slash command and its aliases."""
        name = _normalize_name(command.name)
        if name in self._commands:
            raise ValueError(f"Duplicate slash command: /{name}")
        self._commands[name] = command
        for alias in command.aliases:
            normalized_alias = _normalize_name(alias)
            if normalized_alias in self._commands or normalized_alias in self._aliases:
                raise ValueError(f"Duplicate slash command alias: /{normalized_alias}")
            self._aliases[normalized_alias] = name

    def get(self, name: str) -> SlashCommand | None:
        """Return a command by name or alias."""
        normalized = _normalize_name(name)
        command_name = self._aliases.get(normalized, normalized)
        return self._commands.get(command_name)

    def list_commands(self) -> tuple[SlashCommand, ...]:
        """Return registered commands sorted by name."""
        return tuple(self._commands[name] for name in sorted(self._commands))

    def execute(self, session: CommandSession, text: str) -> CommandResult:
        """Execute a slash command, or return unhandled for ordinary prompts."""
        stripped = text.strip()
        if not stripped.startswith("/"):
            return unhandled_result()

        if stripped.startswith("/skill:"):
            return unhandled_result()

        name, args = _parse_command(stripped)
        if not name:
            return unhandled_result()

        command = self.get(name)
        if command is None and name == "scoped" and args.lower() == "models":
            command = self.get("scoped-models")
            name = "scoped-models"
            args = ""
        if command is None:
            return unhandled_result()

        return command.handler(
            CommandContext(session=session, registry=self, text=stripped, name=name, args=args)
        )


def _parse_command(text: str) -> tuple[str, str]:
    command, separator, args = text[1:].partition(" ")
    return _normalize_name(command), args.strip() if separator else ""


def _normalize_name(name: str) -> str:
    return name.strip().removeprefix("/").lower()


def _parse_export_args(args: str) -> tuple[str | None, Path | None]:
    parts = args.split()
    export_format: str | None = None
    destination: Path | None = None
    index = 0
    while index < len(parts):
        part = parts[index]
        if part == "--format":
            index += 1
            if index >= len(parts):
                raise ValueError("Usage: /export [--format html|jsonl] [destination]")
            export_format = parts[index]
        elif part.startswith("--format="):
            export_format = part.partition("=")[2]
        elif part.startswith("-"):
            raise ValueError(f"Unknown export option: {part}")
        elif destination is None:
            destination = Path(part).expanduser()
        else:
            raise ValueError("Usage: /export [--format html|jsonl] [destination]")
        index += 1
    return export_format, destination
