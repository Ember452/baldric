"""Core slash-command types and registry primitives."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Result of handling a coding-session slash command."""

    handled: bool
    exit_requested: bool = False
    clear_requested: bool = False
    reload_requested: bool = False
    new_session_requested: bool = False
    compact_summary: str | None = None
    export_requested: bool = False
    export_destination: Path | None = None
    export_format: str | None = None
    resume_session_id: str | None = None
    resume_picker_requested: bool = False
    prompts_picker_requested: bool = False
    tree_picker_requested: bool = False
    login_picker_requested: bool = False
    custom_provider_login_requested: bool = False
    local_requested: bool = False
    sidebar_toggle_requested: bool = False
    login_provider: str | None = None
    login_method: str | None = None
    logout_picker_requested: bool = False
    logout_provider: str | None = None
    model_picker_requested: bool = False
    model_selection_provider: str | None = None
    model_selection_model: str | None = None
    tools_picker_requested: bool = False
    scoped_models_picker_requested: bool = False
    skills_picker_requested: bool = False
    theme_picker_requested: bool = False
    extensions_picker_requested: bool = False
    thinking_level: str | None = None
    theme: str | None = None
    message: str | None = None
    system_prompt_inspection: SystemPromptInspection | None = None
    session_name: str | None = None


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
            return CommandResult(handled=False)

        if stripped.startswith("/skill:"):
            return CommandResult(handled=False)

        name, args = _parse_command(stripped)
        if not name:
            return CommandResult(handled=False)

        command = self.get(name)
        if command is None and name == "scoped" and args.lower() == "models":
            command = self.get("scoped-models")
            name = "scoped-models"
            args = ""
        if command is None:
            return CommandResult(handled=False)

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
